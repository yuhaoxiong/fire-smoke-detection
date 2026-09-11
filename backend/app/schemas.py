"""Pydantic 请求/响应模型，字段与 docs/API.md 一一对应。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AlarmLevel = Literal["none", "warning", "critical"]
JobStatus = Literal["queued", "processing", "done", "failed", "cancelled"]


class HealthOut(BaseModel):
    status: str = "ok"
    version: str
    uptime_sec: float
    model_loaded: bool
    device: str


class ModelSwitchIn(BaseModel):
    name: str = Field(min_length=1)


class ConfigIn(BaseModel):
    """部分更新，只传要改的字段。"""

    conf_thres: float | None = Field(default=None, ge=0.01, le=0.99)
    iou_thres: float | None = Field(default=None, ge=0.01, le=0.99)
    imgsz: int | None = Field(default=None, ge=320, le=1280)
    device: str | None = None
    alarm_conf: float | None = Field(default=None, ge=0.01, le=0.99)
    alarm_consecutive: int | None = Field(default=None, ge=1, le=60)
    alarm_cooldown_sec: int | None = Field(default=None, ge=0, le=3600)
    save_snapshots: bool | None = None
    max_upload_mb: int | None = Field(default=None, ge=1, le=1024)
    model: str | None = None


class DetectionOut(BaseModel):
    cls_id: int
    cls: str
    label: str
    color: str
    conf: float
    xyxy: list[int]
    xyxyn: list[float]
    area_ratio: float


class ImagePayload(BaseModel):
    mime: str = "image/jpeg"
    data_url: str


class AlarmOut(BaseModel):
    active: bool
    level: AlarmLevel
    label: str | None = None
    message: str | None = None
    event_id: int | None = None
    snapshot_url: str | None = None
    strikes: int = 0
    cooldown: bool = False


class DetectOut(BaseModel):
    id: str
    source: str
    width: int
    height: int
    inference_ms: float
    preprocess_ms: float = 0.0
    postprocess_ms: float = 0.0
    device: str
    counts: dict[str, int]
    max_conf: float
    alarm: AlarmOut
    detections: list[DetectionOut]
    image: ImagePayload | None = None


class EventOut(BaseModel):
    id: int
    created_at: str
    level: str
    source: str
    cls: str | None
    label: str | None
    conf: float
    counts: dict[str, int]
    snapshot_url: str | None
    message: str | None


class EventListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EventOut]


class EventStatsOut(BaseModel):
    total: int
    fire: int
    smoke: int
    critical: int
    warning: int
    recent: int
    by_hour: list[dict[str, Any]]
    by_source: list[dict[str, Any]]
    latest: EventOut | None = None


class VideoSubmitOut(BaseModel):
    job_id: str
    status: JobStatus
    total_frames: int


class JobOut(BaseModel):
    job_id: str
    filename: str
    status: JobStatus
    progress: float
    processed: int
    total_frames: int
    fps: float
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    output_url: str | None = None
    summary: dict[str, Any]


class JobListOut(BaseModel):
    items: list[JobOut]


class OkOut(BaseModel):
    ok: bool = True
    deleted: int | None = None
