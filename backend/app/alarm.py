"""告警判定引擎。

规则（都能在设置页在线调整）：
- 只在命中类别的置信度 >= ``alarm_conf`` 时才认为「这一帧有情况」。
- 摄像头来源要求**连续 N 帧**（``alarm_consecutive``）命中才真正报警，避免单帧误报闪烁。
- 图片 / 视频这类单帧或抽样来源，命中即报警。
- 同一 ``state_key`` 在 ``alarm_cooldown_sec`` 内最多产生一条事件，防止刷屏。
- 火焰优先级高于烟雾：同一帧同时有火和烟时，按火焰报 critical。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from .config import SNAPSHOT_DIR, config_store
from .detector import InferenceResult
from .storage import event_store

logger = logging.getLogger(__name__)

_NO_ALARM: dict[str, Any] = {
    "active": False,
    "level": "none",
    "label": None,
    "message": None,
    "event_id": None,
    "strikes": 0,
}

_FIRE_KEYS = ("fire", "flame")


@dataclass
class _State:
    """单个来源的连击与冷却状态。"""

    strikes: int = 0
    last_event_ts: float = 0.0
    last_frame_ts: float = 0.0


class AlarmEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, _State] = {}

    def reset(self, state_key: str) -> None:
        with self._lock:
            self._states.pop(state_key, None)

    def evaluate(
        self,
        *,
        result: InferenceResult,
        source: str,
        state_key: str,
        frame: np.ndarray | None = None,
        require_consecutive: bool | None = None,
        apply_cooldown: bool = True,
    ) -> dict[str, Any]:
        """返回告警字典（结构与 docs/API.md 的 ``alarm`` 字段一致）。

        图片检测是用户的一次独立操作，传 ``apply_cooldown=False``，
        否则连传两张图只会产生一条事件。
        """
        cfg = config_store.get()
        if require_consecutive is None:
            require_consecutive = source == "camera"

        # 1) 挑出置信度达标的目标，火焰优先
        fire = [d for d in result.detections if d.cls in _FIRE_KEYS and d.conf >= cfg.alarm_conf]
        smoke = [d for d in result.detections if d.cls == "smoke" and d.conf >= cfg.alarm_conf]

        hit: str | None = None
        best_conf = 0.0
        if fire:
            hit, best_conf = "fire", max(d.conf for d in fire)
        elif smoke:
            hit, best_conf = "smoke", max(d.conf for d in smoke)

        now = time.time()
        with self._lock:
            state = self._states.setdefault(state_key, _State())
            state.last_frame_ts = now

            if hit is None:
                # 没命中则连击清零，避免「偶发命中累积成告警」
                state.strikes = 0
                return dict(_NO_ALARM)

            state.strikes += 1
            strikes = state.strikes

            need = int(cfg.alarm_consecutive) if require_consecutive else 1
            if strikes < need:
                return {**_NO_ALARM, "strikes": strikes}

            if apply_cooldown and now - state.last_event_ts < float(cfg.alarm_cooldown_sec):
                # 仍在冷却期：已经报过了，不再重复建事件
                return {**_NO_ALARM, "strikes": strikes, "cooldown": True}

            state.last_event_ts = now
            # 冷却期内不必再累积，报完一次重新计数
            state.strikes = 0

        level = "critical" if hit == "fire" else "warning"
        label = "火焰" if hit == "fire" else "烟雾"
        counts = result.counts

        if require_consecutive:
            message = f"连续 {need} 帧检测到{label}"
        else:
            message = f"检测到{label}"

        snapshot = None
        if cfg.save_snapshots and frame is not None:
            snapshot = self._save_snapshot(frame, source, hit, best_conf, counts)
            if snapshot is None:
                logger.warning("快照保存失败，事件仍会记录")

        event = event_store.add(
            level=level,
            source=source,
            cls=hit,
            label=label,
            conf=best_conf,
            counts=counts,
            snapshot=snapshot,
            message=message,
        )

        return {
            "active": True,
            "level": level,
            "label": label,
            "message": message,
            "event_id": event["id"],
            "snapshot_url": event["snapshot_url"],
            "strikes": 1 if not require_consecutive else need,
        }

    @staticmethod
    def _save_snapshot(
        frame: np.ndarray,
        source: str,
        cls: str,
        conf: float,
        counts: dict[str, int],
    ) -> str | None:
        """把触发告警的那一帧存成 jpg，文件名即快照名。"""
        try:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            # 毫秒后缀，避免同一秒内多条事件互相覆盖
            ms = int((time.time() % 1) * 1000)
            name = f"{stamp}_{ms:03d}_{source}_{cls}_{int(conf * 100)}.jpg"
            path = SNAPSHOT_DIR / name
            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            ok, buf = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88]
            )
            if not ok:
                return None
            path.write_bytes(buf.tobytes())
            return name
        except Exception as exc:
            logger.warning("保存快照异常：%s", exc)
            return None


alarm_engine = AlarmEngine()
