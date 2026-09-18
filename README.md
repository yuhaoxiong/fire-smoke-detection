# 火灾烟雾智能识别系统

[![CI](https://github.com/yuhaoxiong/fire-smoke-detection/actions/workflows/ci.yml/badge.svg)](https://github.com/yuhaoxiong/fire-smoke-detection/actions/workflows/ci.yml)

基于 **YOLOv8 + FastAPI + Vue3** 的火焰/烟雾识别系统：支持**摄像头实时检测**、**图片上传检测**、
**视频文件检测**，并提供检测历史、告警统计与运行参数管理。前端为纯手写的**浅色科技风**界面
（白底 + 细描边 + 蓝色强调，无任何 UI 组件库、图表全部用 SVG/CSS 手写）。

当前状态：后端契约、前端页面、端到端链路均已验证通过（见 [自检与验收](#自检与验收)）。

---

## 功能特性

| 页面 | 能力 |
|---|---|
| 总览 Dashboard | 检测总数 / 火焰 / 烟雾 / 严重告警 KPI；近 24 小时按小时趋势（手写 SVG 折线+柱）；按来源占比（手写 SVG 环形图）；最新告警卡片 |
| 实时检测 Live | 浏览器 `getUserMedia` 采集 → 抽帧编码 JPEG → `WS /ws/detect` 单帧请求-响应；Canvas 用**归一化坐标 `xyxyn`** 叠加检测框；FPS / 推理耗时 / 目标数实时显示；连续帧告警 + 声音提醒 |
| 图片检测 Image | 拖拽/选择图片 → `POST /api/detect/image` → 原图与标注图对比、检测框列表、置信度、告警结论 |
| 视频检测 Video | 上传视频 → 异步任务 `POST /api/detect/video` → 轮询进度条 → 播放标注结果视频、汇总统计 |
| 告警记录 Events | 分页列表、按等级/来源/类别过滤、快照缩略图、单条删除 / 一键清空 |
| 系统设置 Settings | 运行状态、模型切换（n/s）、阈值参数（conf/iou/imgsz/device）、告警策略（阈值/连击/冷却）、静音开关 |

告警等级：`none`（无） / `warning`（烟雾） / `critical`（火焰）；告警判定要求**连续 N 帧**命中并遵守**冷却时间**，
避免单帧抖动刷屏。

> **默认阈值 `conf_thres = 0.25`**（可用设置页或 `PUT /api/config` 调整）。公开权重对**烟雾**的置信度普遍偏低
> （实测多在 0.17~0.35），默认 0.25 能让中等置信度的烟雾框显示出来；但烟雾分数低于告警阈值 `alarm_conf = 0.50`，
> 因此**烟雾只显示框、不写入告警记录**，只有火焰会触发 `critical` 告警。
> 综合看：降低默认阈值让烟雾**可见**，同时保持告警的**低误报**。

---

## 技术栈与约束

- **后端**：Python 3.13 + FastAPI + Uvicorn + Ultralytics(YOLOv8) + OpenCV + SQLite（标准库 `sqlite3`，无 ORM）
- **前端**：Vue 3（`<script setup>`）+ Vue Router + Vite；**依赖只有 `vue` / `vue-router` / `vite` / `@vitejs/plugin-vue`**
  - 无 Element Plus / Ant Design / Naive UI / Tailwind
  - 图表（小时趋势、来源占比）为纯 SVG 手写，不引第三方图表库
- **模型**：YOLOv8，2 类（`fire` 火焰 / `smoke` 烟雾），权重不入库（见 `.gitignore`）
- **契约**：[`docs/API.md`](docs/API.md) 是前后端唯一接口契约，字段名/类型严格一致

---

## 目录结构

```
火灾烟雾报警/
├── docs/API.md                     # 前后端唯一接口契约（v1）
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口（CORS / 静态资源 / 路由挂载 / lifespan 加载模型）
│   │   ├── config.py               # 设置、模型注册表 MODEL_REGISTRY、类别元数据、SQLite 路径
│   │   ├── detector.py             # YOLOv8 单例（自动选 cuda/cpu）、推理、OpenCV 自绘标注
│   │   ├── alarm.py                # 告警引擎（连击 + 冷却 + 快照）
│   │   ├── storage.py              # SQLite 事件存储
│   │   ├── jobs.py                 # 视频异步任务管理（线程 + 进度）
│   │   ├── schemas.py              # Pydantic 请求/响应模型
│   │   ├── utils.py                # ID 生成、上传读取（超限 413）
│   │   └── routers/                # system / detect / jobs / events / websocket
│   ├── scripts/
│   │   ├── download_weights.py     # 权重下载 + `--verify` 校验类别
│   │   └── selftest.py             # 端到端自检（含 WebSocket 通道）
│   ├── requirements.txt
│   └── weights/                    # 权重目录（*.pt 已 gitignore）
└── frontend/
    ├── src/
    │   ├── views/                  # Dashboard / Live / Image / Video / Events / Settings
    │   ├── components/             # KpiCard / EmptyState / BackendGate
    │   ├── composables/            # useBackend / useAlarmSound / useAlarmFeed
    │   ├── api/client.js           # 接口封装（唯一出网出口）
    │   ├── styles/base.css         # 浅色科技风设计系统
    │   └── router/index.js
    ├── scripts/check-bindings.mjs  # 模板绑定自检（build 的补充）
    ├── vite.config.js              # /api、/static、/ws 代理
    └── package.json
```

---

## 快速开始

### 0. 前置要求

- Python 3.10+（本项目在 3.13.9 上验证）
- Node.js 18+（本项目在 v24.10.0 上验证）
- 可选：NVIDIA GPU + 驱动（本项目在 RTX 4070 Laptop 上用 CUDA 12.4 跑通；无 GPU 自动回退 CPU）

### 1. 后端

```bash
# ① 在项目根目录创建虚拟环境
python -m venv .venv

# ② 先装 CUDA 版 PyTorch（无 GPU 可跳过，直接走第 ③ 步的 CPU 轮子）
.venv/Scripts/python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# ③ 安装其余依赖
cd backend
../.venv/Scripts/python.exe -m pip install -r requirements.txt

# ④ 下载模型权重（约 27 MB）
../.venv/Scripts/python.exe scripts/download_weights.py --verify

# ⑤ 启动服务
../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 健康检查：<http://127.0.0.1:8000/api/health>
- 交互式文档：<http://127.0.0.1:8000/docs>
- 模型加载失败**不会**阻塞服务启动，前端会在设置页提示，日志里给出下载命令。

> macOS / Linux 把 `.venv/Scripts/python.exe` 换成 `.venv/bin/python`。

### 2. 前端

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
```

开发模式下 Vite 会把 `/api`、`/static`、`/ws` 代理到 `http://127.0.0.1:8000`
（可用环境变量 `VITE_BACKEND_ORIGIN` 覆盖后端地址）。

生产构建与预览：

```bash
npm run build      # 产出 dist/，并顺带执行模板绑定自检
npm run preview    # http://127.0.0.1:4173
```

生产模式下前端默认**直连** `http://127.0.0.1:8000`（后端已开放 CORS），
可用 `VITE_API_BASE` 覆盖。

> 摄像头实时检测需要浏览器授权摄像头；`http://127.0.0.1` 属于安全上下文，
> 本地调试无需 HTTPS。

---

## 模型权重

权重来自公开的 fire/smoke 二类 YOLOv8 模型，均**未被纳入版本库**（`.gitignore` 忽略 `backend/weights/*.pt`），
请用脚本自行下载：

```bash
cd backend
../.venv/Scripts/python.exe scripts/download_weights.py --list     # 查看状态
../.venv/Scripts/python.exe scripts/download_weights.py --verify   # 下载 + 打印类别校验
../.venv/Scripts/python.exe scripts/download_weights.py --model fire-smoke-yolov8s --force
```

| 注册名 | 基座 | 大小 | 类别 | 来源 | 定位 |
|---|---|---|---|---|---|
| `fire-smoke-yolov8n` | YOLOv8n | 5.97 MB | `['fire', 'smoke']` | [luminous0219/fire-and-smoke-detection-yolov8](https://github.com/luminous0219/fire-and-smoke-detection-yolov8) | 轻量，**实时首选** |
| `fire-smoke-yolov8s` | YOLOv8s | 21.47 MB | `['fire', 'smoke']` | [Eemrkcgl/fire_smoke_detection](https://github.com/Eemrkcgl/fire_smoke_detection) | 高精度，速度略慢 |

下载脚本会在保存后重新加载权重并打印真实类别名，确认是 `fire`/`smoke` 二类；
类别与颜色在 `backend/app/config.py` 的 `MODEL_REGISTRY` / `CLASS_META` 中集中维护，
前端不硬编码颜色，一律使用后端 `/api/model` 下发的 `classes[].color`。

---

## 接口契约

完整定义见 [`docs/API.md`](docs/API.md)（v1），要点：

- 统一 `/api` 前缀；WebSocket 为 `/ws/detect`
- 时间字段统一 **ISO 8601 带时区**（如 `2026-09-11T11:30:00+08:00`）
- 坐标：`xyxy` = 像素坐标（原图），`xyxyn` = 0~1 归一化坐标；**实时叠加框统一用 `xyxyn`**
- 静态资源：`/static/snapshots`、`/static/videos`、`/static/uploads`

主要端点：

```
GET    /api/health              GET    /api/model          POST /api/model/switch
GET    /api/config              PUT    /api/config
POST   /api/detect/image        POST   /api/detect/image/raw
POST   /api/detect/video        GET    /api/jobs           GET  /api/jobs/{id}  DELETE /api/jobs/{id}
GET    /api/events              GET    /api/events/stats   DELETE /api/events/{id} | /api/events
WS     /ws/detect
```

---

## 自检与验收

**后端端到端自检**（逐条核对契约，覆盖 HTTP + WebSocket）：

```bash
cd backend
# 自检脚本额外依赖 httpx（仅开发/CI 需要，部署后端服务不需要）
../.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
../.venv/Scripts/python.exe scripts/selftest.py --image /path/to/fire.jpg --frames 3
```

校验内容：健康/模型/配置字段、事件与统计结构、`xyxy` 与 `xyxyn` 坐标合法性、
`image/raw` 的 JPEG 魔数、`WS /ws/detect` 的 `ready` / `result` / `ping→pong` / `config`
控制消息，以及告警连击是否按 `alarm_consecutive` 递增。退出码 0 表示全通过。

也可以把同一套检查跑在 Vite 代理上，验证代理配置：
`... scripts/selftest.py --base http://127.0.0.1:5173 --image ...`

**前端构建与模板自检**：

```bash
cd frontend
npm run build      # vite build + node scripts/check-bindings.mjs
```

`scripts/check-bindings.mjs` 用 `@vue/compiler-sfc` 编译每个 SFC，扫描产物中的
`_ctx.xxx` / `_resolveComponent(...)` —— 用于捕获 `vite build` 查不出来的
「模板引用了 `script setup` 里不存在的标识符」这类只在运行时静默变空白的问题。

**实测结论**（RTX 4070 Laptop / CUDA 12.4 / 640px）：

| 项目 | 结果 |
|---|---|
| 权重加载 | `fire-smoke-yolov8n` @ `cuda:0`，类别 `['fire','smoke']` |
| 图片检测（火焰） | 火焰图 0.76~0.84 置信度、`critical` 告警、`xyxy`/`xyxyn` 均合法 |
| 图片检测（烟雾） | 默认 `conf_thres=0.25` 下 3/5 张烟雾图出框（0.25~0.35），`alarm.active=false`、不产生告警记录 |
| 单帧推理 | 18~50 ms（含前后处理），`/api/detect/image/raw` 返回 JPEG |
| 实时 WS | 连续 3 帧命中 → `alarm.strikes` 1→2→3，第 3 帧转为 `critical` |
| 视频任务 | 40 帧视频 → `done`，产出标注 MP4 可从 `/static/videos/...` 播放，自动生成 1 条 `video` 来源告警 |

**持续集成（GitHub Actions）**：`.github/workflows/ci.yml` 在每次 push / PR 时并行跑两个任务：

- **前端**：`npm ci` → `npm run build`（`vite build` + `check-bindings.mjs` 模板绑定自检）。
- **后端**：装 CPU 版 PyTorch → `download_weights.py --verify` 拉权重并校验 `fire` 类别 →
  起 `uvicorn` → 跑 `scripts/selftest.py` 做端到端契约核对。

CI 里没有真实素材，用 `scripts/make_test_image.py` 生成**合成图**跑通
「上传 → 推理 → 坐标契约 → JPEG 回传」链路。它只验证**契约与流程**，
检出数通常为 0（`selftest.py` 明确允许 `counts.total == 0`），**不验证模型精度**。

---

## 常见问题

**1. 权重加载报 `dill` 相关错误 / `'gbk' codec can't decode byte 0xab`**
旧版 Ultralytics 保存的公开权重需要 `dill` 反序列化，`requirements.txt` 已显式包含 `dill>=0.3.8`；
若仍报错说明环境里没装上，手动补一句 `pip install dill` 即可。

**2. 中文路径导致异常**
项目路径若含中文，个别工具（如 git worktree）会报 `Invalid argument`；
建议克隆到纯英文路径。另外 Windows GBK 控制台打印符号/中文可能报
`UnicodeEncodeError`，仓库内脚本已统一把 stdout/stderr 切到 UTF-8。

**3. 没有 GPU / CUDA 版本对不上**
先装 CUDA 版 torch 再装 `requirements.txt`；不装也能跑（CPU 自动回退，速度下降）。
可在设置页把 `device` 改成 `cpu`，或直接用 `PUT /api/config` 修改（改 `device`/`imgsz`/`model` 会触发模型重载）。

**4. 前端提示「后端未连接」**
确认后端已在 `127.0.0.1:8000` 运行；页面会直接给出启动命令。
开发环境请用 `npm run dev`（走 Vite 代理），不要用 `file://` 直接打开 `index.html`。

**5. 摄像头打不开**
浏览器需授权摄像头；`getUserMedia` 只在 `localhost` / HTTPS 下可用。
若设备被其他程序占用（如会议软件），先释放再重试。

---

## 已知限制

- 公开权重以**火焰**样本为主，**烟雾**置信度普遍偏低（实测 0.17~0.35）。默认 `conf_thres=0.25`
  已让多数烟雾框可见，但仍有部分烟雾图在 0.25 以下未检出；且烟雾低于 `alarm_conf=0.50`，
  **只显示不告警**。若要多召回烟雾，可在设置页调低 `conf_thres`；若要求烟雾也告警，需下调 `alarm_conf`
  （会显著增加误报）。对精度要求高的场景建议换用 `fire-smoke-yolov8s` 或接入自有数据微调。
- 视频任务是进程内后台线程（非分布式队列），重启后端会丢失未完成任务。
- 事件存储为 SQLite 单文件，适合单机部署；多实例部署需替换为共享存储。
- 实时通道为「单帧请求-响应」，不做服务端推流；帧率取决于浏览器编码 + 网络往返 + 推理耗时。
