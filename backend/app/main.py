"""火灾烟雾智能识别系统 —— FastAPI 应用入口。

启动：
    cd backend
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import (
    SNAPSHOT_DIR,
    UPLOAD_DIR,
    VIDEO_DIR,
    config_store,
    settings,
)
from .detector import get_detector
from .routers import detect, events, jobs, system, websocket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时尝试加载模型；失败不阻塞服务，前端可在设置页切换模型或提示下载权重。"""
    cfg = config_store.get()
    detector = get_detector()
    logger.info("正在加载模型 %s（device=%s, imgsz=%d）…", cfg.model, cfg.device, cfg.imgsz)
    try:
        detector.load(cfg.model, cfg.device, cfg.imgsz)
        logger.info("模型就绪：%s @ %s", detector.name, detector.device)
    except Exception as exc:
        logger.warning(
            "模型加载失败，服务仍会启动。请先执行 `python scripts/download_weights.py` 下载权重"
            "（原因：%s）",
            exc,
        )
    yield
    logger.info("服务已停止")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="基于 YOLOv8 的火焰/烟雾实时识别后端（FastAPI）。接口契约见 docs/API.md。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态资源：快照 / 结果视频 / 上传原件
app.mount("/static/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")
app.mount("/static/videos", StaticFiles(directory=VIDEO_DIR), name="videos")
app.mount("/static/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(system.router)
app.include_router(detect.router)
app.include_router(jobs.router)
app.include_router(events.router)
app.include_router(websocket.router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":  # pragma: no cover - 便捷自启动
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host if settings.host != "0.0.0.0" else "127.0.0.1",
        port=settings.port,
        reload=False,
    )
