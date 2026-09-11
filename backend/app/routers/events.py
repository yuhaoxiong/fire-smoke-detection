"""报警事件与统计接口。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..schemas import EventListOut, EventStatsOut, OkOut
from ..storage import event_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_model=EventListOut)
def list_events(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    level: str | None = Query(None, description="none/warning/critical"),
    source: str | None = Query(None, description="camera/image/video"),
    cls: str | None = Query(None, description="fire/smoke"),
) -> EventListOut:
    data = event_store.list(limit=limit, offset=offset, level=level, source=source, cls=cls)
    return EventListOut(**data)


@router.get("/events/stats", response_model=EventStatsOut)
def event_stats(hours: int = Query(24, ge=1, le=720)) -> EventStatsOut:
    return EventStatsOut(**event_store.stats(hours=hours))


@router.delete("/events/{event_id}", response_model=OkOut)
def delete_event(event_id: int) -> OkOut:
    if not event_store.delete(event_id):
        raise HTTPException(status_code=404, detail=f"事件不存在：{event_id}")
    return OkOut(ok=True)


@router.delete("/events", response_model=OkOut)
def clear_events() -> OkOut:
    deleted = event_store.clear()
    logger.info("清空报警事件：%d 条", deleted)
    return OkOut(ok=True, deleted=deleted)
