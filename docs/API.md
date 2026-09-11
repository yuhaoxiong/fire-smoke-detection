# 火灾烟雾智能识别系统 — 接口契约 (v1)

> 本文件是前后端唯一契约。前端只依赖本文件，后端实现必须与之一致。
> 所有路径均以 `/api` 为前缀（WebSocket 除外），基地址默认 `http://127.0.0.1:8000`。

## 0. 通用约定

- 请求/响应编码：`UTF-8`，除文件上传外均为 `application/json`。
- 错误响应遵循 FastAPI 默认：HTTP 4xx/5xx + `{"detail": "错误描述"}`。
- 时间字段统一为 **ISO 8601 带时区**字符串，例如 `2026-09-11T11:30:00+08:00`。
- 坐标 `xyxy` 为**像素坐标**（相对原始帧）；`xyxyn` 为 **0~1 归一化坐标**。
  实时叠加框请**一律使用 `xyxyn`**，因为服务端可能对帧做了缩放。
- 类别颜色（后端下发，前端直接用）：

  | cls_id | cls | label | color |
  |---|---|---|---|
  | 0 | `fire` | 火焰 | `#ff4d3d` |
  | 1 | `smoke` | 烟雾 | `#7c8ba1` |

---

## 1. 系统与模型

### `GET /api/health`
```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_sec": 123.4,
  "model_loaded": true,
  "device": "cuda:0"
}
```

### `GET /api/model`
```json
{
  "name": "fire-smoke-yolov8n",
  "weights_path": "backend/weights/fire-smoke-yolov8n.pt",
  "weights_size_mb": 5.96,
  "imgsz": 640,
  "device": "cuda:0",
  "device_name": "NVIDIA GeForce RTX 4070 Laptop GPU",
  "loaded_at": "2026-09-11T11:30:00+08:00",
  "classes": [
    { "id": 0, "name": "fire",  "label": "火焰", "color": "#ff4d3d" },
    { "id": 1, "name": "smoke", "label": "烟雾", "color": "#7c8ba1" }
  ],
  "available": [
    {
      "value": "fire-smoke-yolov8n",
      "label": "YOLOv8n 火焰烟雾（轻量·实时推荐）",
      "path": "backend/weights/fire-smoke-yolov8n.pt",
      "exists": true,
      "size_mb": 5.96
    }
  ]
}
```

### `POST /api/model/switch`
请求体：`{ "name": "fire-smoke-yolov8s" }`
响应：同 `GET /api/model` 的结构（已切换后的模型信息）。

---

## 2. 运行参数

### `GET /api/config`
```json
{
  "conf_thres": 0.35,
  "iou_thres": 0.45,
  "imgsz": 640,
  "device": "auto",
  "alarm_conf": 0.50,
  "alarm_consecutive": 3,
  "alarm_cooldown_sec": 20,
  "save_snapshots": true,
  "max_upload_mb": 50,
  "model": "fire-smoke-yolov8n"
}
```

### `PUT /api/config`
请求体为**部分字段**（只传要改的），响应为更新后的完整 config。
修改 `device` / `imgsz` / `model` 会触发模型重载（响应可能耗时 1~5 秒）。

---

## 3. 图片检测

### `POST /api/detect/image`
`multipart/form-data`：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `file` | File | 必填 | jpg / png / webp / bmp |
| `conf` | float | 取全局配置 | 置信度阈值 |
| `iou` | float | 取全局配置 | NMS IoU 阈值 |
| `return_image` | bool | `true` | 是否返回标注图 |

响应：
```json
{
  "id": "img_20260911_113000_ab12",
  "source": "image",
  "width": 1280,
  "height": 720,
  "inference_ms": 31.2,
  "preprocess_ms": 2.1,
  "postprocess_ms": 3.4,
  "device": "cuda:0",
  "counts": { "fire": 2, "smoke": 1, "total": 3 },
  "max_conf": 0.93,
  "alarm": {
    "active": true,
    "level": "critical",
    "label": "火焰",
    "message": "检测到火焰，请立即核查",
    "event_id": 12
  },
  "detections": [
    {
      "cls_id": 0,
      "cls": "fire",
      "label": "火焰",
      "conf": 0.93,
      "xyxy": [100, 200, 300, 400],
      "xyxyn": [0.078, 0.278, 0.234, 0.556],
      "area_ratio": 0.02
    }
  ],
  "image": {
    "mime": "image/jpeg",
    "data_url": "data:image/jpeg;base64,...."
  }
}
```
`alarm.level` 取值：`"none" | "warning" | "critical"`。`alarm` 在无告警时为
`{ "active": false, "level": "none", "label": null, "message": null, "event_id": null }`。

`image` 字段仅当 `return_image=true` 时存在。

### `POST /api/detect/image/raw`
参数同上（`multipart/form-data`），但**直接返回标注后的图片字节**，`Content-Type: image/jpeg`。
便于 `curl -o out.jpg` 使用。

---

## 4. 实时摄像头（WebSocket）

### `WS /ws/detect`
连接示例：`ws://127.0.0.1:8000/ws/detect?conf=0.4&iou=0.45&annotated=false`

**客户端 → 服务端**
- 二进制帧（JPEG / PNG 字节）：待检测画面。
- 文本 JSON 控制消息：
  - `{ "type": "config", "conf": 0.4, "iou": 0.5, "annotated": true }`
  - `{ "type": "ping" }` → 服务端回 `{ "type": "pong" }`
  - `{ "type": "reset" }` → 重置本次会话的告警连击计数

**服务端 → 客户端**（文本 JSON）

连接建立后立即推送一次：
```json
{
  "type": "ready",
  "session_id": "ws_ab12cd34",
  "model": { "name": "fire-smoke-yolov8n", "classes": [ ... ] },
  "config": { "conf": 0.4, "iou": 0.45, "annotated": false }
}
```

每帧返回：
```json
{
  "type": "result",
  "seq": 1,
  "ts": 1757561400.123,
  "inference_ms": 22.1,
  "fps": 17.3,
  "width": 640,
  "height": 480,
  "counts": { "fire": 1, "smoke": 0, "total": 1 },
  "max_conf": 0.88,
  "detections": [ { "cls_id": 0, "cls": "fire", "label": "火焰", "conf": 0.88,
                    "xyxy": [10,20,30,40], "xyxyn": [0.016,0.042,0.047,0.083],
                    "area_ratio": 0.001 } ],
  "alarm": { "active": true, "level": "critical", "label": "火焰",
             "message": "连续 3 帧检测到火焰", "strikes": 3, "event_id": 13 },
  "image": { "mime": "image/jpeg", "data_url": "data:image/jpeg;base64,..." }
}
```
- `image` **仅当** `annotated=true` 时出现，默认不返回（前端自己用 canvas 画框最省带宽）。
- `alarm.strikes` 为告警连击帧数，无告警时为 `0`。
- 单帧解码/推理失败时返回 `{ "type": "error", "message": "..." }` 且**不断开连接**。

---

## 5. 视频文件检测（异步任务）

### `POST /api/detect/video`
`multipart/form-data`：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `file` | File | 必填 | mp4 / avi / mov / mkv |
| `conf` / `iou` | float | 全局配置 | 阈值 |
| `stride` | int | `2` | 每 N 帧抽检一次，用于提速 |
| `max_frames` | int | `0` | 0 表示不限 |

响应：
```json
{ "job_id": "vid_20260911_1130_ab12", "status": "processing", "total_frames": 900 }
```

### `GET /api/jobs/{job_id}`
```json
{
  "job_id": "vid_...",
  "filename": "fire.mp4",
  "status": "processing",
  "progress": 0.42,
  "processed": 380,
  "total_frames": 900,
  "fps": 14.2,
  "started_at": "2026-09-11T11:30:00+08:00",
  "finished_at": null,
  "error": null,
  "output_url": null,
  "summary": {
    "total_detections": 10,
    "fire_frames": 5,
    "smoke_frames": 3,
    "max_conf": 0.95,
    "events_created": 2
  }
}
```
`status` 取值：`queued | processing | done | failed | cancelled`。
`done` 时 `output_url` 为 `/static/videos/xxx.mp4`（可直接 `<video src>` 播放）。

### `GET /api/jobs`
返回 `{ "items": [ ...同上结构... ] }`。

### `DELETE /api/jobs/{job_id}`
取消/删除任务，返回 `{ "ok": true }`。

---

## 6. 报警事件与统计

### `GET /api/events`
查询参数：`limit`（默认 50，最大 500）、`offset`（默认 0）、`level`、`source`（`camera|image|video`）、`cls`（`fire|smoke`）

```json
{
  "total": 12,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "id": 3,
      "created_at": "2026-09-11T11:30:00+08:00",
      "level": "critical",
      "source": "camera",
      "cls": "fire",
      "label": "火焰",
      "conf": 0.93,
      "counts": { "fire": 2, "smoke": 0 },
      "snapshot_url": "/static/snapshots/20260911_113000_ab12.jpg",
      "message": "连续 3 帧检测到火焰"
    }
  ]
}
```
`snapshot_url` 在未保存快照时为 `null`。

### `GET /api/events/stats?hours=24`
```json
{
  "total": 12,
  "fire": 8,
  "smoke": 4,
  "critical": 8,
  "warning": 4,
  "recent": 5,
  "by_hour": [
    { "t": "2026-09-11T10:00:00+08:00", "fire": 1, "smoke": 0 }
  ],
  "by_source": [ { "source": "camera", "count": 9 } ],
  "latest": { "...同上事件结构..." }
}
```

### `DELETE /api/events/{id}` → `{ "ok": true }`
### `DELETE /api/events` → `{ "ok": true, "deleted": 12 }`

---

## 7. 静态资源

| 路径 | 内容 |
|---|---|
| `/static/snapshots/<file>.jpg` | 报警快照 |
| `/static/videos/<file>.mp4` | 视频检测结果 |
| `/static/uploads/<file>` | 上传的原始文件 |

---

## 8. 健康探测与联调自检

前端启动后应先请求 `GET /api/health` 与 `GET /api/model`；若失败，
在界面上展示「后端未连接」提示，并给出启动命令
`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。
