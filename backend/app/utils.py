"""跨路由复用的小工具：ID 生成、上传校验。"""

from __future__ import annotations

import os
import time
import uuid

from fastapi import HTTPException, UploadFile

from .config import config_store


def new_id(prefix: str) -> str:
    """生成形如 ``img_20260911_113000_ab12cd`` 的短 ID。"""
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def check_suffix(filename: str | None, allowed: set[str]) -> str:
    """校验上传文件名后缀；返回小写后缀。"""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext and ext not in allowed:
        allowed_text = " / ".join(sorted(allowed))
        raise HTTPException(status_code=400, detail=f"不支持的文件格式 {ext}，仅支持 {allowed_text}")
    return ext


async def read_upload(file: UploadFile, max_mb: int | None = None) -> bytes:
    """读取上传内容并做大小限制，返回原始字节。"""
    cfg = config_store.get()
    limit_mb = int(max_mb or cfg.max_upload_mb)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(data) > limit_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(data) / 1048576:.1f} MB），上限 {limit_mb} MB",
        )
    return data
