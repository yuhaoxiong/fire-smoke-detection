"""系统、模型与参数配置接口。"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import MODEL_REGISTRY, config_store, settings
from ..detector import ModelNotFoundError, get_detector
from ..schemas import ConfigIn, HealthOut, ModelSwitchIn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["system"])

_START_TS = time.time()


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    detector = get_detector()
    return HealthOut(
        status="ok",
        version=settings.version,
        uptime_sec=round(time.time() - _START_TS, 1),
        model_loaded=detector.is_loaded,
        device=detector.device,
    )


@router.get("/model")
def model_info() -> dict[str, Any]:
    detector = get_detector()
    if not detector.is_loaded:
        # 未加载时也返回可用列表，方便前端在设置页选择并触发首次加载
        cfg = config_store.get()
        return {
            "name": cfg.model,
            "weights_path": None,
            "weights_size_mb": None,
            "imgsz": cfg.imgsz,
            "device": cfg.device,
            "device_name": None,
            "loaded_at": None,
            "classes": [],
            "num_classes": 0,
            "available": __import__(
                "app.config", fromlist=["discover_local_models"]
            ).discover_local_models(),
            "loaded": False,
        }
    info = detector.info()
    info["loaded"] = True
    return info


@router.post("/model/switch")
def switch_model(payload: ModelSwitchIn) -> dict[str, Any]:
    detector = get_detector()
    if payload.name not in MODEL_REGISTRY and not any(
        m["value"] == payload.name for m in __import__(
            "app.config", fromlist=["discover_local_models"]
        ).discover_local_models()
    ):
        raise HTTPException(status_code=404, detail=f"模型不存在：{payload.name}")

    cfg = config_store.get()
    try:
        detector.load(payload.name, cfg.device, cfg.imgsz)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # 权重损坏、CUDA OOM 等
        logger.exception("切换模型失败")
        raise HTTPException(status_code=500, detail=f"加载模型失败：{exc}") from exc

    config_store.update({"model": payload.name})
    info = detector.info()
    info["loaded"] = True
    return info


@router.get("/config")
def get_config() -> dict[str, Any]:
    return config_store.get().model_dump()


@router.put("/config")
def update_config(payload: ConfigIn) -> dict[str, Any]:
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        return config_store.get().model_dump()

    current = config_store.get()

    # 这三项变了必须重新加载模型（imgsz 影响预热尺寸，device 影响显存/速度）
    need_reload = any(
        key in patch and patch[key] != getattr(current, key)
        for key in ("model", "device", "imgsz")
    )

    updated = config_store.update(patch)

    if need_reload:
        detector = get_detector()
        already_correct = (
            detector.is_loaded
            and detector.name == updated.model
            and detector.device == detector.resolve_device(updated.device)
            and detector._imgsz == updated.imgsz
        )
        if not already_correct:
            try:
                detector.load(updated.model, updated.device, updated.imgsz)
            except ModelNotFoundError as exc:
                # 权重缺失时保留配置，但把失败原因告诉调用方
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except Exception as exc:
                logger.exception("应用新配置时重载模型失败")
                raise HTTPException(status_code=500, detail=f"重载模型失败：{exc}") from exc

    return updated.model_dump()


@router.get("/detect-id")
def new_detect_id() -> dict[str, str]:
    """给前端用的轻量 ID 生成器（也用于联调自检）。"""
    return {"id": uuid.uuid4().hex[:12]}
