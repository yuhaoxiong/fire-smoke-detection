"""视频文件检测任务接口。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..jobs import video_jobs
from ..schemas import JobListOut, JobOut, OkOut, VideoSubmitOut
from ..utils import check_suffix, read_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["jobs"])

ALLOWED_VIDEO_SUFFIX = {".mp4", ".avi", ".mov", ".mkv"}


@router.post("/detect/video", response_model=VideoSubmitOut)
async def detect_video(
    file: UploadFile = File(..., description="待检测视频"),
    conf: float | None = Form(None, ge=0.01, le=0.99),
    iou: float | None = Form(None, ge=0.01, le=0.99),
    stride: int = Form(2, ge=1, le=60),
    max_frames: int = Form(0, ge=0),
) -> VideoSubmitOut:
    check_suffix(file.filename, ALLOWED_VIDEO_SUFFIX)
    data = await read_upload(file)

    try:
        job = video_jobs.submit(
            filename=file.filename or "video.mp4",
            data=data,
            conf=conf,
            iou=iou,
            stride=stride,
            max_frames=max_frames,
        )
    except Exception as exc:
        logger.exception("提交视频任务失败")
        raise HTTPException(status_code=400, detail=f"无法读取视频：{exc}") from exc

    return VideoSubmitOut(**job.to_submit_dict())


@router.get("/jobs", response_model=JobListOut)
def list_jobs() -> JobListOut:
    return JobListOut(items=[JobOut(**job.to_dict()) for job in video_jobs.list()])


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str) -> JobOut:
    job = video_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{job_id}")
    return JobOut(**job.to_dict())


@router.delete("/jobs/{job_id}", response_model=OkOut)
def delete_job(job_id: str) -> OkOut:
    if not video_jobs.delete(job_id):
        raise HTTPException(status_code=404, detail=f"任务不存在：{job_id}")
    return OkOut(ok=True)
