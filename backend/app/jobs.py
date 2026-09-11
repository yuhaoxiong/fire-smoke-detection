"""视频文件检测：后台线程逐帧推理、写标注视频、汇报进度。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .alarm import alarm_engine
from .config import UPLOAD_DIR, VIDEO_DIR, config_store
from .detector import annotate, get_detector
from .storage import event_store

logger = logging.getLogger(__name__)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


@dataclass
class VideoJob:
    job_id: str
    filename: str
    src_path: Path
    status: str = "queued"
    processed: int = 0
    total_frames: int = 0
    fps: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    output_path: Path | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    conf: float = 0.35
    iou: float = 0.45
    stride: int = 2
    max_frames: int = 0
    # 汇总
    total_detections: int = 0
    fire_frames: int = 0
    smoke_frames: int = 0
    max_conf: float = 0.0
    events_created: int = 0
    _created: float = field(default_factory=time.time)

    @property
    def progress(self) -> float:
        if self.status == "done":
            return 1.0
        if not self.total_frames:
            return 0.0
        return min(0.999, self.processed / float(self.total_frames))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "status": self.status,
            "progress": round(self.progress, 4),
            "processed": self.processed,
            "total_frames": self.total_frames,
            "fps": round(self.fps, 2),
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "error": self.error,
            "output_url": (
                f"/static/videos/{self.output_path.name}"
                if self.output_path and self.status == "done"
                else None
            ),
            "summary": {
                "total_detections": self.total_detections,
                "fire_frames": self.fire_frames,
                "smoke_frames": self.smoke_frames,
                "max_conf": round(self.max_conf, 4),
                "events_created": self.events_created,
            },
        }

    def to_submit_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "status": self.status, "total_frames": self.total_frames}


class VideoJobManager:
    """串行执行视频任务（GPU 只有一个，并发跑只会互相拖慢）。"""

    def __init__(self, max_jobs: int = 50) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, VideoJob] = {}
        self._order: list[str] = []
        self._max_jobs = max_jobs

    # ------------------------------------------------------------ 提交
    def submit(
        self,
        *,
        filename: str,
        data: bytes,
        conf: float | None = None,
        iou: float | None = None,
        stride: int = 2,
        max_frames: int = 0,
    ) -> VideoJob:
        cfg = config_store.get()
        job_id = f"vid_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        suffix = Path(filename).suffix or ".mp4"
        src_path = UPLOAD_DIR / f"{job_id}{suffix}"
        src_path.write_bytes(data)

        cap = cv2.VideoCapture(str(src_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()

        job = VideoJob(
            job_id=job_id,
            filename=filename,
            src_path=src_path,
            total_frames=total,
            conf=float(cfg.conf_thres if conf is None else conf),
            iou=float(cfg.iou_thres if iou is None else iou),
            stride=max(1, int(stride)),
            max_frames=max(0, int(max_frames)),
        )

        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._evict_locked()

        thread = threading.Thread(
            target=self._run, args=(job,), name=f"video-{job_id}", daemon=True
        )
        thread.start()
        return job

    def _evict_locked(self) -> None:
        while len(self._order) > self._max_jobs:
            oldest = self._order.pop(0)
            old = self._jobs.get(oldest)
            if old and old.status in ("queued", "processing"):
                self._order.append(oldest)  # 运行中的不动
                break
            self._jobs.pop(oldest, None)

    # ------------------------------------------------------------ 执行
    def _run(self, job: VideoJob) -> None:
        job.status = "processing"
        job.started_at = time.time()
        started = time.perf_counter()
        writer: cv2.VideoWriter | None = None
        try:
            detector = get_detector()
            cap = cv2.VideoCapture(str(job.src_path))
            if not cap.isOpened():
                raise RuntimeError("无法打开视频文件，请确认编码格式受支持")

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            if not job.total_frames:
                job.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

            out_path = VIDEO_DIR / f"{job.job_id}_annotated.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_path), fourcc, native_fps, (width, height))
            if not writer.isOpened():
                raise RuntimeError("无法创建输出视频，请检查 OpenCV 编码器")

            index = 0
            last_result = None
            last_frame: np.ndarray | None = None
            window_start = time.perf_counter()
            window_frames = 0

            while True:
                if job.cancel.is_set():
                    job.status = "cancelled"
                    break
                ok, frame = cap.read()
                if not ok:
                    break
                index += 1
                if job.max_frames and index > job.max_frames:
                    break

                # 抽帧：非采样帧直接复制上一帧的框，保证输出视频每一帧都有内容
                if index % job.stride == 0 or last_result is None:
                    last_result = detector.infer(frame, conf=job.conf, iou=job.iou)
                    last_frame = frame
                    counts = last_result.counts
                    if counts["total"]:
                        job.total_detections += counts["total"]
                        job.max_conf = max(job.max_conf, last_result.max_conf)
                        if counts["fire"]:
                            job.fire_frames += 1
                        if counts["smoke"]:
                            job.smoke_frames += 1
                    # 视频来源不要求连击，命中即报警，但受冷却时间约束
                    alarm = alarm_engine.evaluate(
                        result=last_result,
                        source="video",
                        state_key=f"video:{job.job_id}",
                        frame=frame,
                        require_consecutive=False,
                    )
                    if alarm.get("active"):
                        job.events_created += 1

                assert last_result is not None
                writer.write(annotate(frame, last_result))
                job.processed = index
                window_frames += 1

                # 每 30 帧更新一次速率，避免频繁取时钟
                if window_frames >= 30:
                    elapsed = time.perf_counter() - window_start
                    job.fps = window_frames / elapsed if elapsed > 0 else 0.0
                    window_start, window_frames = time.perf_counter(), 0

            cap.release()
            if job.status != "cancelled":
                total_elapsed = time.perf_counter() - started
                job.fps = job.processed / total_elapsed if total_elapsed > 0 else 0.0
                job.status = "done"
                job.output_path = out_path
        except Exception as exc:
            logger.exception("视频任务 %s 失败", job.job_id)
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            if writer is not None:
                writer.release()
            job.finished_at = time.time()
            job.cancel.set()

    # ------------------------------------------------------------ 查询
    def get(self, job_id: str) -> VideoJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[VideoJob]:
        with self._lock:
            jobs = [self._jobs[j] for j in self._order if j in self._jobs]
        return sorted(jobs, key=lambda j: j.started_at or j._created, reverse=True)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.cancel.set()
            self._jobs.pop(job_id, None)
            if job_id in self._order:
                self._order.remove(job_id)
        # 清理磁盘上的中间文件
        for path in (job.src_path, job.output_path):
            try:
                if path and path.exists():
                    path.unlink()
            except OSError as exc:
                logger.warning("清理任务文件失败 %s：%s", path, exc)
        return True


video_jobs = VideoJobManager()
