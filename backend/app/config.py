"""全局配置：静态设置、模型注册表、运行期可变参数。"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 路径
BACKEND_DIR = Path(__file__).resolve().parent.parent
WEIGHTS_DIR = BACKEND_DIR / "weights"
DATA_DIR = BACKEND_DIR / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
VIDEO_DIR = DATA_DIR / "videos"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "events.db"
RUNTIME_CONFIG_PATH = DATA_DIR / "config.json"

for _d in (WEIGHTS_DIR, DATA_DIR, SNAPSHOT_DIR, VIDEO_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- 静态设置
class Settings(BaseSettings):
    """通过环境变量覆盖，前缀 ``FIRE_``，例如 ``FIRE_PORT=9000``。"""

    model_config = SettingsConfigDict(
        env_prefix="FIRE_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )

    app_name: str = "火灾烟雾智能识别系统"
    version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000

    # 默认模型（见 MODEL_REGISTRY）
    model_name: str = "fire-smoke-yolov8n"
    device: str = "auto"          # auto | cpu | cuda:0 | 0
    imgsz: int = 640

    # 检测阈值
    conf_thres: float = 0.25
    iou_thres: float = 0.45

    # 告警策略
    alarm_conf: float = 0.50      # 触发告警的置信度下限
    alarm_consecutive: int = 3    # 摄像头连续命中多少帧后报警
    alarm_cooldown_sec: int = 20  # 同一来源两条告警的最小间隔（秒）
    save_snapshots: bool = True

    # 上传限制
    max_upload_mb: int = 50

    # 跨域（开发时前端跑在 5173）
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()


# ---------------------------------------------------------------- 模型注册表
#  权重来源均已实测下载并校验过类别为 fire / smoke（见 README「权重来源」）
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "fire-smoke-yolov8n": {
        "label": "YOLOv8n 火焰烟雾（轻量·实时首选）",
        "filename": "fire-smoke-yolov8n.pt",
        "base": "yolov8n",
        "size_mb": 5.97,
        "urls": [
            "https://github.com/luminous0219/fire-and-smoke-detection-yolov8/raw/main/weights/best.pt",
            "https://github.com/Eemrkcgl/fire_smoke_detection/releases/download/first_commit/best_from_internet.pt",
        ],
        "source": "https://github.com/luminous0219/fire-and-smoke-detection-yolov8",
        "note": "6.0MB，类别 fire/smoke，适合摄像头实时检测",
    },
    "fire-smoke-yolov8s": {
        "label": "YOLOv8s 火焰烟雾（高精度）",
        "filename": "fire-smoke-yolov8s.pt",
        "base": "yolov8s",
        "size_mb": 21.5,
        "urls": [
            "https://github.com/Eemrkcgl/fire_smoke_detection/releases/download/first_commit/best_trained.pt",
            "https://github.com/Abonia1/YOLOv8-Fire-and-Smoke-Detection/raw/main/runs/detect/train/weights/best.pt",
        ],
        "source": "https://github.com/Eemrkcgl/fire_smoke_detection",
        "note": "21.5MB，类别 fire/smoke，精度更高、速度略慢",
    },
}

# 类别元信息：英文类别名 -> 中文标签 + 展示颜色
CLASS_META: dict[str, dict[str, str]] = {
    "fire": {"label": "火焰", "color": "#ff4d3d"},
    "flame": {"label": "火焰", "color": "#ff4d3d"},
    "smoke": {"label": "烟雾", "color": "#7c8ba1"},
}
DEFAULT_CLASS_COLOR = "#0ea5e9"


def resolve_class(raw_name: str) -> tuple[str, str, str]:
    """把模型输出的类别名规范化为 (key, 中文标签, 颜色)。"""
    key = str(raw_name).strip().lower()
    meta = CLASS_META.get(key)
    if meta:
        return key, meta["label"], meta["color"]
    return key, str(raw_name), DEFAULT_CLASS_COLOR


def weights_path(name: str) -> Path:
    """返回某个注册模型在本地的权重路径。"""
    entry = MODEL_REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"未注册的模型：{name}")
    return WEIGHTS_DIR / entry["filename"]


def discover_local_models() -> list[dict[str, Any]]:
    """列出所有可用模型：注册表 + weights 目录里手动放入的 .pt 文件。"""
    items: list[dict[str, Any]] = []
    known_files = {e["filename"] for e in MODEL_REGISTRY.values()}

    for name, entry in MODEL_REGISTRY.items():
        path = WEIGHTS_DIR / entry["filename"]
        items.append(
            {
                "value": name,
                "label": entry["label"],
                "path": str(path),
                "exists": path.exists(),
                "size_mb": round(path.stat().st_size / 1048576, 2) if path.exists() else None,
                "source": entry["source"],
                "note": entry["note"],
            }
        )

    # 用户自己丢进 weights/ 的权重，也能在设置页里选到
    for path in sorted(WEIGHTS_DIR.glob("*.pt")):
        if path.name in known_files:
            continue
        items.append(
            {
                "value": path.stem,
                "label": f"{path.stem}（本地自定义权重）",
                "path": str(path),
                "exists": True,
                "size_mb": round(path.stat().st_size / 1048576, 2),
                "source": None,
                "note": "位于 backend/weights/ 的自定义权重",
            }
        )
    return items


# ---------------------------------------------------------------- 运行期配置
class RuntimeConfig(BaseModel):
    """可在线修改并持久化到 ``backend/data/config.json`` 的参数。"""

    conf_thres: float = Field(default=settings.conf_thres, ge=0.01, le=0.99)
    iou_thres: float = Field(default=settings.iou_thres, ge=0.01, le=0.99)
    imgsz: int = Field(default=settings.imgsz, ge=320, le=1280)
    device: str = settings.device
    alarm_conf: float = Field(default=settings.alarm_conf, ge=0.01, le=0.99)
    alarm_consecutive: int = Field(default=settings.alarm_consecutive, ge=1, le=60)
    alarm_cooldown_sec: int = Field(default=settings.alarm_cooldown_sec, ge=0, le=3600)
    save_snapshots: bool = settings.save_snapshots
    max_upload_mb: int = Field(default=settings.max_upload_mb, ge=1, le=1024)
    model: str = settings.model_name

    @field_validator("imgsz")
    @classmethod
    def _imgsz_multiple_of_32(cls, v: int) -> int:
        # YOLO 要求输入尺寸是 32 的倍数，这里向下对齐，避免推理时报错
        return max(320, (int(v) // 32) * 32)


class ConfigStore:
    """线程安全的运行期配置容器，写入即落盘。"""

    def __init__(self, path: Path = RUNTIME_CONFIG_PATH) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._config = self._load()

    def _load(self) -> RuntimeConfig:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                return RuntimeConfig(**raw)
            except Exception as exc:  # 配置损坏时退回默认值，不让服务起不来
                logger.warning("读取运行期配置失败，使用默认值：%s", exc)
        return RuntimeConfig()

    def get(self) -> RuntimeConfig:
        with self._lock:
            return self._config.model_copy()

    def update(self, patch: dict[str, Any]) -> RuntimeConfig:
        with self._lock:
            data = self._config.model_dump()
            for key, value in patch.items():
                if value is None or key not in data:
                    continue
                data[key] = value
            self._config = RuntimeConfig(**data)
            self._persist()
            return self._config.model_copy()

    def _persist(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._config.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("保存运行期配置失败：%s", exc)


config_store = ConfigStore()

AlarmLevel = Literal["none", "warning", "critical"]
SourceKind = Literal["camera", "image", "video"]
