"""YOLOv8 推理引擎：模型加载、单帧推理、结果标注。

设计要点：
- 进程内单例，权重只加载一次；``threading.RLock`` 保证多线程（WebSocket + HTTP）安全。
- 绝不自动联网下载权重：加载前先校验文件是否存在，缺失时抛出可读的错误。
- 标注完全用 OpenCV 自己画，不依赖 ultralytics 的绘图（避免字体下载、也方便统一样式）。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2
import numpy as np

from .config import (
    MODEL_REGISTRY,
    WEIGHTS_DIR,
    discover_local_models,
    resolve_class,
    settings,
    weights_path,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- 数据结构
@dataclass
class Detection:
    """单个检测框。坐标 xyxy 为原图像素，xyxyn 为 0~1 归一化坐标。"""

    cls_id: int
    cls: str
    label: str
    color: str
    conf: float
    xyxy: tuple[float, float, float, float]
    xyxyn: tuple[float, float, float, float]
    area_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cls_id": self.cls_id,
            "cls": self.cls,
            "label": self.label,
            "color": self.color,
            "conf": round(self.conf, 4),
            "xyxy": [int(round(v)) for v in self.xyxy],
            "xyxyn": [round(v, 6) for v in self.xyxyn],
            "area_ratio": round(self.area_ratio, 6),
        }


@dataclass
class InferenceResult:
    """一次推理的完整结果。"""

    width: int
    height: int
    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0
    preprocess_ms: float = 0.0
    postprocess_ms: float = 0.0
    device: str = "cpu"

    @property
    def counts(self) -> dict[str, int]:
        fire = sum(1 for d in self.detections if d.cls in ("fire", "flame"))
        smoke = sum(1 for d in self.detections if d.cls == "smoke")
        return {"fire": fire, "smoke": smoke, "total": len(self.detections)}

    @property
    def max_conf(self) -> float:
        return max((d.conf for d in self.detections), default=0.0)


class ModelNotFoundError(RuntimeError):
    """权重文件不存在。"""


# ---------------------------------------------------------------- 推理引擎
class FireSmokeDetector:
    """进程内单例的 YOLOv8 火焰/烟雾检测器。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._model: Any = None
        self._name: str | None = None
        self._path: Path | None = None
        self._device: str = "cpu"
        self._device_name: str = ""
        self._imgsz: int = settings.imgsz
        self._loaded_at: float | None = None
        self._class_count: int = 0
        # 推理耗时统计（指数滑动平均），用于前端展示稳定数值
        self._ema_ms: float = 0.0
        self._frame_count: int = 0
        self._last_infer_ts: float | None = None

    # ------------------------------------------------------------ 属性
    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> str:
        return self._device

    @property
    def name(self) -> str | None:
        return self._name

    # ------------------------------------------------------------ 加载
    @staticmethod
    def resolve_device(device: str) -> str:
        """把 ``auto`` / ``0`` 之类的写法解析成 ultralytics 认得的设备字符串。"""
        import torch

        want = (device or "auto").strip().lower()
        if want in ("auto", ""):
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        if want in ("cpu", "mps"):
            return want
        if want in ("cuda", "gpu"):
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        if want.isdigit():
            return f"cuda:{want}" if torch.cuda.is_available() else "cpu"
        # cuda:0 这类写法直接透传；不可用时回退 CPU
        if want.startswith("cuda") and not torch.cuda.is_available():
            logger.warning("请求了 CUDA 但当前环境不可用，回退到 CPU")
            return "cpu"
        return want

    @staticmethod
    def _device_display_name(device: str) -> str:
        import torch

        if device.startswith("cuda"):
            try:
                index = int(device.split(":")[1]) if ":" in device else 0
                return torch.cuda.get_device_name(index)
            except Exception:
                return "CUDA 设备"
        return "CPU"

    def load(self, name: str, device: str = "auto", imgsz: int | None = None) -> None:
        """加载（或重新加载）权重。name 可以是注册名，也可以是 weights/ 下的文件名。"""
        with self._lock:
            path = self._locate_weights(name)
            new_device = self.resolve_device(device)
            new_imgsz = int(imgsz or self._imgsz or settings.imgsz)

            from ultralytics import YOLO

            logger.info("加载权重 %s（device=%s, imgsz=%d）", path, new_device, new_imgsz)
            t0 = time.perf_counter()
            model = YOLO(str(path))

            # 预热：跑一张空图，把 CUDA kernel 编译/显存分配的开销挪到加载阶段
            try:
                dummy = np.zeros((new_imgsz, new_imgsz, 3), dtype=np.uint8)
                model.predict(
                    dummy,
                    imgsz=new_imgsz,
                    conf=0.25,
                    iou=0.45,
                    device=new_device,
                    verbose=False,
                )
            except Exception as exc:
                logger.warning("模型预热失败（不影响使用）：%s", exc)

            self._model = model
            self._name = name
            self._path = path
            self._device = new_device
            self._device_name = self._device_display_name(new_device)
            self._imgsz = new_imgsz
            self._loaded_at = time.time()
            self._class_count = len(getattr(model, "names", {}) or {})
            self._ema_ms = 0.0
            self._frame_count = 0
            logger.info(
                "模型加载完成：%s，类别 %s，耗时 %.2fs",
                name,
                self.classes,
                time.perf_counter() - t0,
            )

    def _locate_weights(self, name: str) -> Path:
        """解析权重路径；支持注册名与本地文件名。"""
        if name in MODEL_REGISTRY:
            path = weights_path(name)
        else:
            candidate = WEIGHTS_DIR / name
            if candidate.suffix != ".pt":
                candidate = candidate.with_suffix(".pt")
            path = candidate

        if not path.exists():
            available = [m["value"] for m in discover_local_models()]
            raise ModelNotFoundError(
                f"权重文件不存在：{path}\n"
                f"请先执行 `python scripts/download_weights.py` 下载权重，"
                f"或把 .pt 文件放入 {WEIGHTS_DIR}。当前可用：{available}"
            )
        return path

    def ensure_loaded(self) -> None:
        """首次使用时懒加载，避免服务启动被权重问题阻塞。"""
        if self.is_loaded:
            return
        cfg = _runtime_config()
        self.load(cfg.model, cfg.device, cfg.imgsz)

    # ------------------------------------------------------------ 信息
    @property
    def classes(self) -> list[dict[str, Any]]:
        if not self.is_loaded:
            return []
        names: dict[int, str] = getattr(self._model, "names", {}) or {}
        out: list[dict[str, Any]] = []
        for idx, raw in names.items():
            key, label, color = resolve_class(raw)
            out.append({"id": int(idx), "name": key, "label": label, "color": color})
        return out

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "frames": self._frame_count,
            "avg_inference_ms": round(self._ema_ms, 2),
        }

    def info(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "weights_path": str(self._path) if self._path else None,
            "weights_size_mb": (
                round(self._path.stat().st_size / 1048576, 2) if self._path and self._path.exists() else None
            ),
            "imgsz": self._imgsz,
            "device": self._device,
            "device_name": self._device_name,
            "loaded_at": _iso(self._loaded_at) if self._loaded_at else None,
            "classes": self.classes,
            "num_classes": self._class_count,
            "available": discover_local_models(),
        }

    # ------------------------------------------------------------ 推理
    def infer(
        self,
        frame: np.ndarray,
        conf: float | None = None,
        iou: float | None = None,
        imgsz: int | None = None,
    ) -> InferenceResult:
        """对一张 BGR 图像做检测。frame 不会被修改。"""
        if frame is None or frame.size == 0:
            raise ValueError("输入图像为空")

        self.ensure_loaded()
        cfg = _runtime_config()
        conf = float(cfg.conf_thres if conf is None else conf)
        iou = float(cfg.iou_thres if iou is None else iou)
        size = int(imgsz or self._imgsz)

        h, w = frame.shape[:2]
        t_start = time.perf_counter()
        with self._lock:  # ultralytics 的 predictor 不是线程安全的
            results = self._model.predict(
                frame,
                imgsz=size,
                conf=conf,
                iou=iou,
                device=self._device,
                verbose=False,
                max_det=100,
            )
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        detections: list[Detection] = []
        if results:
            boxes = getattr(results[0], "boxes", None)
            names: dict[int, str] = getattr(self._model, "names", {}) or {}
            if boxes is not None and len(boxes) > 0:
                xyxy_all = boxes.xyxy.cpu().numpy()
                conf_all = boxes.conf.cpu().numpy()
                cls_all = boxes.cls.cpu().numpy().astype(int)
                for xyxy, c, cid in zip(xyxy_all, conf_all, cls_all):
                    x1, y1, x2, y2 = (float(v) for v in xyxy)
                    x1, y1 = max(0.0, x1), max(0.0, y1)
                    x2, y2 = min(float(w), x2), min(float(h), y2)
                    box_w, box_h = max(0.0, x2 - x1), max(0.0, y2 - y1)
                    key, label, color = resolve_class(names.get(int(cid), str(cid)))
                    detections.append(
                        Detection(
                            cls_id=int(cid),
                            cls=key,
                            label=label,
                            color=color,
                            conf=float(c),
                            xyxy=(x1, y1, x2, y2),
                            xyxyn=(x1 / w, y1 / h, x2 / w, y2 / h),
                            area_ratio=(box_w * box_h) / float(w * h),
                        )
                    )

        detections.sort(key=lambda d: d.conf, reverse=True)

        # 更新统计
        self._frame_count += 1
        self._ema_ms = elapsed_ms if self._ema_ms == 0 else self._ema_ms * 0.8 + elapsed_ms * 0.2
        self._last_infer_ts = time.time()

        return InferenceResult(
            width=w,
            height=h,
            detections=detections,
            inference_ms=round(elapsed_ms, 2),
            device=self._device,
        )


# ---------------------------------------------------------------- 标注绘制
_LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _hex_to_bgr(color: str) -> tuple[int, int, int]:
    color = (color or "#0ea5e9").lstrip("#")
    if len(color) != 6:
        color = "0ea5e9"
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


def annotate(frame: np.ndarray, result: InferenceResult, show_conf: bool = True) -> np.ndarray:
    """在图像上画出检测框，返回新图像（不修改入参）。"""
    canvas = frame.copy()
    h, w = canvas.shape[:2]
    # 线宽随分辨率缩放，小图不至于糊成一片
    thickness = max(2, int(round(min(w, h) / 320)))
    font_scale = max(0.5, min(w, h) / 900)
    text_thickness = max(1, thickness - 1)
    pad = max(4, thickness * 2)

    for det in result.detections:
        x1, y1, x2, y2 = (int(round(v)) for v in det.xyxy)
        color = _hex_to_bgr(det.color)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness, lineType=cv2.LINE_AA)

        # 标签用英文，避免 OpenCV putText 无法渲染中文
        text = f"{det.cls.upper()} {det.conf * 100:.0f}%" if show_conf else det.cls.upper()
        (tw, th), baseline = cv2.getTextSize(text, _LABEL_FONT, font_scale, text_thickness)
        # 标签贴在框上方；顶部空间不够时挪到框内
        label_y1 = y1 - th - baseline - pad
        if label_y1 < 0:
            label_y1 = y1
        label_y2 = label_y1 + th + baseline + pad
        label_x2 = min(w, x1 + tw + pad * 2)
        cv2.rectangle(canvas, (x1, label_y1), (label_x2, label_y2), color, -1, lineType=cv2.LINE_AA)
        cv2.putText(
            canvas,
            text,
            (x1 + pad, label_y2 - baseline - pad // 2),
            _LABEL_FONT,
            font_scale,
            (255, 255, 255),
            text_thickness,
            lineType=cv2.LINE_AA,
        )

    _draw_hud(canvas, result)
    return canvas


def _draw_hud(canvas: np.ndarray, result: InferenceResult) -> None:
    """左上角画一条半透明信息条。"""
    counts = result.counts
    parts = [f"{k.upper()}:{counts[k]}" for k in ("fire", "smoke") if counts[k]]
    text = "  ".join(parts) if parts else "NO TARGET"
    text += f"   {result.inference_ms:.0f}ms"
    font_scale = max(0.45, min(canvas.shape[:2]) / 1100)
    (tw, th), baseline = cv2.getTextSize(text, _LABEL_FONT, font_scale, 1)
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 0), (min(canvas.shape[1], tw + 24), th + baseline + 16), (255, 255, 255), -1)
    cv2.addWeighted(overlay, 0.72, canvas, 0.28, 0, canvas)
    cv2.putText(
        canvas,
        text,
        (12, th + 6),
        _LABEL_FONT,
        font_scale,
        (30, 41, 59),
        1,
        lineType=cv2.LINE_AA,
    )


# ---------------------------------------------------------------- 单例
_detector: FireSmokeDetector | None = None
_detector_lock = threading.Lock()


def get_detector() -> FireSmokeDetector:
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                _detector = FireSmokeDetector()
    return _detector


def _runtime_config():
    """延迟导入，避免 config <-> detector 循环引用。"""
    from .config import config_store

    return config_store.get()


# ---------------------------------------------------------------- 图像编解码工具
def decode_image(data: bytes) -> np.ndarray:
    """把上传的字节流解码成 BGR ndarray。"""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解析图片，请确认文件格式为 jpg/png/webp/bmp")
    return img


def encode_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("图片编码失败")
    return buf.tobytes()


def to_data_url(jpeg_bytes: bytes) -> str:
    import base64

    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    from datetime import datetime

    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
