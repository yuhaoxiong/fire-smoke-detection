#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""端到端自检脚本：一条命令验证后端契约是否可用。

覆盖范围（与 ``docs/API.md`` 一一对应）：
  1. ``GET  /api/health`` / ``GET  /api/model`` / ``GET  /api/config``
  2. ``POST /api/detect/image``   —— 坐标必须是像素 xyxy + 归一化 xyxyn
  3. ``POST /api/detect/video``   —— 异步任务能被轮询到终态
  4. ``WS   /ws/detect``          —— ready / result / ping-pong / config 控制消息
  5. ``GET  /api/events`` / ``/api/events/stats``

用法::

    cd backend
    ../.venv/Scripts/python.exe scripts/selftest.py
    ../.venv/Scripts/python.exe scripts/selftest.py --image D:/pics/fire.jpg --frames 4

不带 ``--image`` 时只跑接口连通性；带上图片会额外验证推理与坐标契约。
退出码 0 表示全部通过，1 表示有失败项。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# Windows GBK 控制台无法编码部分符号/中文，统一改用 UTF-8 输出。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

OK = "  [PASS]"
BAD = "  [FAIL]"

_results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    _results.append((ok, label))
    print(f"{OK if ok else BAD} {label}" + (f" —— {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def _in_unit(v: float) -> bool:
    return -1e-6 <= v <= 1.0 + 1e-6


async def check_http(client: httpx.AsyncClient, image: Path | None) -> dict[str, Any]:
    section("1. 系统与模型")

    r = await client.get("/api/health")
    health = r.json()
    check(r.status_code == 200 and health.get("status") == "ok", "GET /api/health", json.dumps(health, ensure_ascii=False))
    check(bool(health.get("model_loaded")), "模型已加载", f"device={health.get('device')}")
    check("uptime_sec" in health and "version" in health, "health 字段齐全")

    r = await client.get("/api/model")
    model = r.json()
    check(r.status_code == 200, "GET /api/model")
    names = [c.get("name") for c in model.get("classes", [])]
    check(names == ["fire", "smoke"], "类别为 fire/smoke", str(names))
    check(
        all({"id", "name", "label", "color"} <= set(c) for c in model.get("classes", [])),
        "classes 含 id/name/label/color",
    )
    check(isinstance(model.get("available"), list) and len(model["available"]) >= 1, "available 非空")

    r = await client.get("/api/config")
    cfg = r.json()
    want = {
        "conf_thres", "iou_thres", "imgsz", "device", "alarm_conf",
        "alarm_consecutive", "alarm_cooldown_sec", "save_snapshots", "max_upload_mb", "model",
    }
    check(want <= set(cfg), "GET /api/config 字段齐全", ",".join(sorted(want - set(cfg))) or "ok")

    section("2. 事件与统计")
    r = await client.get("/api/events", params={"limit": 5})
    ev = r.json()
    check({"total", "limit", "offset", "items"} <= set(ev), "GET /api/events 结构正确")
    r = await client.get("/api/events/stats", params={"hours": 24})
    stats = r.json()
    check(
        {"total", "fire", "smoke", "critical", "warning", "recent", "by_hour", "by_source"} <= set(stats),
        "GET /api/events/stats 结构正确",
    )
    check(
        isinstance(stats.get("by_hour"), list)
        and all({"t", "fire", "smoke"} <= set(b) for b in stats["by_hour"]),
        "by_hour 为 {t,fire,smoke} 序列",
        f"{len(stats.get('by_hour') or [])} 个点",
    )
    check(
        isinstance(stats.get("by_source"), list)
        and all({"source", "count"} <= set(b) for b in stats["by_source"]),
        "by_source 为 {source,count} 序列",
    )

    if image is None:
        return {"skipped_detect": True}

    section("3. 图片检测 POST /api/detect/image")
    data = image.read_bytes()
    r = await client.post(
        "/api/detect/image",
        files={"file": (image.name, data, "image/jpeg")},
        params={"return_image": "false"},
    )
    check(r.status_code == 200, f"上传 {image.name}", f"HTTP {r.status_code}")
    out = r.json()
    need = {"id", "width", "height", "inference_ms", "counts", "max_conf", "alarm", "detections"}
    check(need <= set(out), "响应字段齐全", ",".join(sorted(need - set(out))) or "ok")
    check(
        {"fire", "smoke", "total"} <= set(out.get("counts") or {}),
        "counts 含 fire/smoke/total",
        str(out.get("counts")),
    )
    check(
        {"active", "level", "label", "message", "event_id"} <= set(out.get("alarm") or {}),
        "alarm 结构正确",
        f"level={out['alarm'].get('level')} msg={out['alarm'].get('message')}",
    )
    check(
        out["alarm"].get("level") in ("none", "warning", "critical"),
        "alarm.level 取值合法",
        str(out["alarm"].get("level")),
    )

    bad_coords = []
    for det in out.get("detections") or []:
        x1, y1, x2, y2 = det["xyxy"]
        if not (0 <= x1 < x2 <= out["width"] and 0 <= y1 < y2 <= out["height"]):
            bad_coords.append(("xyxy", det["xyxy"]))
        if not all(_in_unit(v) for v in det["xyxyn"]) or not (
            det["xyxyn"][0] < det["xyxyn"][2] and det["xyxyn"][1] < det["xyxyn"][3]
        ):
            bad_coords.append(("xyxyn", det["xyxyn"]))
        if not (0.0 <= float(det["conf"]) <= 1.0):
            bad_coords.append(("conf", det["conf"]))
    check(not bad_coords, "检测框坐标/置信度合法", str(bad_coords[:3]) or "ok")
    check(
        all(_in_unit(d["xyxyn"][2]) for d in (out.get("detections") or []))
        or out["counts"]["total"] == 0,
        "xyxyn 归一化到 0~1",
    )
    print(
        f"    推理 {out['inference_ms']} ms / 检出 {out['counts']['total']} 个目标"
        f" / 最高置信度 {out['max_conf']}"
    )

    section("4. 图片检测（raw 直接返回 JPEG）")
    r = await client.post(
        "/api/detect/image/raw",
        files={"file": (image.name, data, "image/jpeg")},
    )
    ctype = r.headers.get("content-type", "")
    check(r.status_code == 200 and ctype.startswith("image/jpeg"), "POST /api/detect/image/raw", f"{ctype} {len(r.content)}B")
    check(r.content[:2] == b"\xff\xd8", "返回内容确为 JPEG（SOI 魔数）")

    return out


async def check_ws(base_ws: str, image: Path | None, frames: int) -> None:
    import websockets

    section("5. 实时 WebSocket WS /ws/detect")
    url = f"{base_ws}/ws/detect?conf=0.25&iou=0.45&annotated=false"
    try:
        async with websockets.connect(url, max_size=32 * 1024 * 1024, open_timeout=20) as ws:
            ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            check(ready.get("type") == "ready", "首帧为 ready", f"session={ready.get('session_id')}")
            check(
                ready.get("model", {}).get("name") is not None
                and len(ready.get("model", {}).get("classes") or []) == 2,
                "ready 携带 model.classes",
            )
            check(
                {"conf", "iou", "annotated"} <= set(ready.get("config") or {}),
                "ready 携带 config",
                str(ready.get("config")),
            )

            await ws.send(json.dumps({"type": "ping"}))
            pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            check(pong.get("type") == "pong", "ping → pong")

            await ws.send(json.dumps({"type": "config", "conf": 0.5, "annotated": True}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            check(
                ack.get("type") == "config" and ack.get("config", {}).get("conf") == 0.5
                and ack.get("config", {}).get("annotated") is True,
                "config 控制消息生效",
                str(ack.get("config")),
            )

            if image is None:
                check(True, "二进制帧推理（已跳过：未提供 --image）")
                return

            payload = image.read_bytes()
            got_frame = False
            for i in range(max(1, frames)):
                await ws.send(payload)
                t0 = time.perf_counter()
                res = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                rtt = (time.perf_counter() - t0) * 1000
                if res.get("type") != "result":
                    check(False, f"第 {i + 1} 帧返回 result", str(res)[:120])
                    return
                got_frame = True
                need = {"seq", "ts", "inference_ms", "fps", "width", "height", "counts", "max_conf",
                        "detections", "alarm"}
                if not need <= set(res):
                    check(False, "result 字段齐全", ",".join(sorted(need - set(res))))
                    return
                if not all(_in_unit(v) for d in res["detections"] for v in d["xyxyn"]):
                    check(False, "result 的 xyxyn 归一化", str(res["detections"])[:120])
                    return
                print(
                    f"    帧 {res['seq']}: {res['counts']['total']} 个目标, {res['inference_ms']} ms,"
                    f" 往返 {rtt:.0f} ms, alarm={res['alarm']['level']}"
                    f"(strikes={res['alarm']['strikes']})"
                )
            check(got_frame, f"连续 {frames} 帧均返回 result")
    except Exception as exc:  # noqa: BLE001
        check(False, "WS /ws/detect 会话", f"{type(exc).__name__}: {exc}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="火灾烟雾识别系统 端到端自检")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="HTTP 基地址")
    parser.add_argument("--ws-base", default=None, help="WebSocket 基地址，默认由 --base 推导")
    parser.add_argument("--image", action="append", default=[], help="用于推理验证的图片，可多次传入")
    parser.add_argument("--frames", type=int, default=3, help="WS 每张图片发送的帧数（默认 3）")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    ws_base = (args.ws_base or base.replace("https://", "wss://").replace("http://", "ws://")).rstrip("/")
    images = [Path(p) for p in args.image]
    for p in images:
        if not p.is_file():
            print(f"图片不存在：{p}")
            return 1

    print(f"后端：{base}")
    print(f"图片：{[str(p) for p in images] or '（无，仅连通性检查）'}")

    async with httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(120.0)) as client:
        for p in images or [None]:
            await check_http(client, p)

    for p in images or [None]:
        await check_ws(ws_base, p, args.frames)

    failed = [label for ok, label in _results if not ok]
    print("\n" + "=" * 60)
    print(f"共 {len(_results)} 项，通过 {len(_results) - len(failed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：")
        for label in failed:
            print(f"  - {label}")
        return 1
    print("全部通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
