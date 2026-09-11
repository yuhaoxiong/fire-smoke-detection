"""WebSocket 实时摄像头检测：``WS /ws/detect``。

客户端发 JPEG 二进制帧，服务端回 JSON（检测框用归一化坐标 ``xyxyn``），
默认不回传标注图；把 ``annotated`` 设为 true 才返回 data URL。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from ..alarm import alarm_engine
from ..config import config_store
from ..detector import (
    ModelNotFoundError,
    annotate,
    decode_image,
    encode_jpeg,
    get_detector,
    to_data_url,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ws"])


def _clamp(value: float) -> float:
    return min(0.99, max(0.01, float(value)))


def _alarm_payload(alarm: dict[str, Any]) -> dict[str, Any]:
    """裁剪成契约里约定的 alarm 结构，顺带保证 JSON 友好。"""
    return {
        "active": bool(alarm.get("active")),
        "level": alarm.get("level") or "none",
        "label": alarm.get("label"),
        "message": alarm.get("message"),
        "strikes": int(alarm.get("strikes") or 0),
        "event_id": alarm.get("event_id"),
        "snapshot_url": alarm.get("snapshot_url"),
        "cooldown": bool(alarm.get("cooldown")),
    }


@router.websocket("/ws/detect")
async def ws_detect(websocket: WebSocket) -> None:
    await websocket.accept()

    cfg = config_store.get()
    params = websocket.query_params

    def _float_param(key: str, default: float) -> float:
        raw = params.get(key)
        if raw in (None, ""):
            return default
        try:
            return _clamp(float(raw))
        except (TypeError, ValueError):
            return default

    def _bool_param(key: str, default: bool = False) -> bool:
        raw = params.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in ("1", "true", "yes", "on")

    conf = _float_param("conf", cfg.conf_thres)
    iou = _float_param("iou", cfg.iou_thres)
    annotated = _bool_param("annotated", False)
    session_id = f"ws_{uuid.uuid4().hex[:8]}"
    state_key = f"camera:{session_id}"

    detector = get_detector()
    try:
        await run_in_threadpool(detector.ensure_loaded)
    except ModelNotFoundError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    except Exception as exc:  # 权重损坏 / CUDA 问题等
        logger.exception("WebSocket 会话加载模型失败")
        await websocket.send_json({"type": "error", "message": f"模型加载失败：{exc}"})

    await websocket.send_json(
        {
            "type": "ready",
            "session_id": session_id,
            "model": {
                "name": detector.name,
                "loaded": detector.is_loaded,
                "classes": detector.classes,
            },
            "config": {"conf": conf, "iou": iou, "annotated": annotated},
        }
    )

    seq = 0
    last_ts: float | None = None
    fps = 0.0

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            text = message.get("text")
            data = message.get("bytes")

            # ------------------------------------------------ 文本控制消息
            if text is not None:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "无效的 JSON 控制消息"})
                    continue

                kind = payload.get("type")
                if kind == "ping":
                    await websocket.send_json({"type": "pong"})
                elif kind == "config":
                    if payload.get("conf") is not None:
                        conf = _clamp(payload["conf"])
                    if payload.get("iou") is not None:
                        iou = _clamp(payload["iou"])
                    if payload.get("annotated") is not None:
                        annotated = bool(payload["annotated"])
                    await websocket.send_json(
                        {"type": "config", "config": {"conf": conf, "iou": iou, "annotated": annotated}}
                    )
                elif kind == "reset":
                    alarm_engine.reset(state_key)
                    await websocket.send_json({"type": "reset", "ok": True})
                    seq = 0
                else:
                    await websocket.send_json(
                        {"type": "error", "message": f"未知的控制消息：{kind}"}
                    )
                continue

            # ------------------------------------------------ 二进制图像帧
            if not data:
                continue

            if not detector.is_loaded:
                await websocket.send_json({"type": "error", "message": "模型未加载，无法推理"})
                continue

            try:
                frame = decode_image(data)
            except ValueError as exc:
                # 单帧解码失败不断开连接，让前端继续送下一帧
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue

            try:
                result = await run_in_threadpool(detector.infer, frame, conf, iou)
            except Exception as exc:
                logger.exception("WebSocket 单帧推理失败")
                await websocket.send_json({"type": "error", "message": f"推理失败：{exc}"})
                continue

            now = time.time()
            if last_ts is not None and now > last_ts:
                inst = 1.0 / (now - last_ts)
                fps = inst if fps == 0 else fps * 0.8 + inst * 0.2
            last_ts = now
            seq += 1

            alarm = alarm_engine.evaluate(
                result=result,
                source="camera",
                state_key=state_key,
                frame=frame,
                require_consecutive=True,
            )

            out: dict[str, Any] = {
                "type": "result",
                "seq": seq,
                "ts": round(now, 3),
                "inference_ms": result.inference_ms,
                "fps": round(fps, 1),
                "width": result.width,
                "height": result.height,
                "counts": result.counts,
                "max_conf": round(result.max_conf, 4),
                "detections": [d.to_dict() for d in result.detections],
                "alarm": _alarm_payload(alarm),
            }
            if annotated:
                canvas = annotate(frame, result)
                out["image"] = {"mime": "image/jpeg", "data_url": to_data_url(encode_jpeg(canvas))}

            await websocket.send_json(out)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket 会话异常中止")
    finally:
        alarm_engine.reset(state_key)
        logger.info("WebSocket 会话结束：%s（共 %d 帧）", session_id, seq)
