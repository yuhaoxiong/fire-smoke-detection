"""图片检测接口。

- ``POST /api/detect/image``      返回 JSON（含检测框、告警、可选标注图 data URL）
- ``POST /api/detect/image/raw``  直接返回标注后的 JPEG 字节，方便 ``curl -o out.jpg``
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from ..alarm import alarm_engine
from ..detector import (
    ModelNotFoundError,
    annotate,
    decode_image,
    encode_jpeg,
    get_detector,
    to_data_url,
)
from ..schemas import AlarmOut, DetectOut, DetectionOut, ImagePayload
from ..utils import check_suffix, new_id, read_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/detect", tags=["detect"])

ALLOWED_IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@router.post("/image", response_model=DetectOut)
async def detect_image(
    file: UploadFile = File(..., description="待检测图片"),
    conf: float | None = Form(None, ge=0.01, le=0.99),
    iou: float | None = Form(None, ge=0.01, le=0.99),
    return_image: bool = Form(True),
) -> DetectOut:
    check_suffix(file.filename, ALLOWED_IMAGE_SUFFIX)
    data = await read_upload(file)

    t0 = time.perf_counter()
    try:
        frame = decode_image(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    preprocess_ms = (time.perf_counter() - t0) * 1000.0

    detector = get_detector()
    try:
        result = detector.infer(frame, conf=conf, iou=iou)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("图片推理失败")
        raise HTTPException(status_code=500, detail=f"推理失败：{exc}") from exc

    # 图片是用户的独立操作：命中即报，且不吃冷却（否则连传两张图只出一条事件）
    alarm = alarm_engine.evaluate(
        result=result,
        source="image",
        state_key="image",
        frame=frame,
        require_consecutive=False,
        apply_cooldown=False,
    )

    image_payload: ImagePayload | None = None
    postprocess_ms = 0.0
    if return_image:
        t1 = time.perf_counter()
        canvas = annotate(frame, result)
        postprocess_ms = (time.perf_counter() - t1) * 1000.0
        image_payload = ImagePayload(mime="image/jpeg", data_url=to_data_url(encode_jpeg(canvas)))

    return DetectOut(
        id=new_id("img"),
        source="image",
        width=result.width,
        height=result.height,
        inference_ms=result.inference_ms,
        preprocess_ms=round(preprocess_ms, 2),
        postprocess_ms=round(postprocess_ms, 2),
        device=result.device,
        counts=result.counts,
        max_conf=round(result.max_conf, 4),
        alarm=AlarmOut(**alarm),
        detections=[DetectionOut(**d.to_dict()) for d in result.detections],
        image=image_payload,
    )


@router.post(
    "/image/raw",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}, "description": "标注后的 JPEG 图片"}},
)
async def detect_image_raw(
    file: UploadFile = File(..., description="待检测图片"),
    conf: float | None = Form(None, ge=0.01, le=0.99),
    iou: float | None = Form(None, ge=0.01, le=0.99),
) -> Response:
    """与 ``/image`` 参数一致，但直接返回标注图片字节。"""
    check_suffix(file.filename, ALLOWED_IMAGE_SUFFIX)
    data = await read_upload(file)

    try:
        frame = decode_image(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    detector = get_detector()
    try:
        result = detector.infer(frame, conf=conf, iou=iou)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    alarm_engine.evaluate(
        result=result,
        source="image",
        state_key="image",
        frame=frame,
        require_consecutive=False,
        apply_cooldown=False,
    )

    jpeg = encode_jpeg(annotate(frame, result))
    return Response(content=jpeg, media_type="image/jpeg")
