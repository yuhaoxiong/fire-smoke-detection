"""下载并校验 fire/smoke YOLOv8 权重到 ``backend/weights/``。

用法（在 backend 目录下执行）::

    python scripts/download_weights.py --list          # 查看注册表与本地状态
    python scripts/download_weights.py                 # 下载缺失的权重
    python scripts/download_weights.py --verify        # 下载后用 ultralytics 读类别名做校验
    python scripts/download_weights.py --model fire-smoke-yolov8s --force

权重来源均为实测可下载的公开仓库（详见 README「权重来源」）。
脚本只做下载 + 校验，不使用任何需要密钥的接口。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows 控制台默认 GBK，会因 ▶ / → 等字符直接抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 非 TTY 或已被重定向
        pass

from app.config import MODEL_REGISTRY, WEIGHTS_DIR, discover_local_models  # noqa: E402

MIN_BYTES = 1_000_000  # 小于 1MB 基本可以断定是 HTML 错误页
CHUNK = 1024 * 256


def _human(size: float) -> str:
    return f"{size / 1048576:.2f} MB"


def _download(url: str, dest: Path) -> int:
    """带进度地下载单个 URL，返回字节数。"""
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "fire-smoke-detector/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with tmp.open("wb") as fh:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done / total * 100
                    sys.stdout.write(f"\r    下载中 {pct:5.1f}%  {_human(done)}/{_human(total)}")
                else:
                    sys.stdout.write(f"\r    下载中 {_human(done)}")
                sys.stdout.flush()
    sys.stdout.write("\r" + " " * 60 + "\r")
    tmp.replace(dest)
    return done


def _verify(path: Path) -> bool:
    """用 ultralytics 读取权重，确认类别里包含 fire / smoke。"""
    try:
        from ultralytics import YOLO
    except Exception as exc:  # ultralytics 未安装
        print(f"    [跳过校验] 无法导入 ultralytics：{exc}")
        return True
    try:
        model = YOLO(str(path))
        names = [str(v).strip().lower() for v in (getattr(model, "names", {}) or {}).values()]
    except Exception as exc:
        print(f"    [校验失败] 无法加载权重：{exc}")
        return False
    print(f"    类别：{names}")
    hit = {"fire", "flame"} & set(names)
    if not hit:
        print("    [校验失败] 类别中没有 fire/flame，权重可能不是火焰烟雾模型")
        return False
    print("    [校验通过] 包含 fire 类别")
    return True


def cmd_list() -> int:
    print(f"权重目录：{WEIGHTS_DIR}\n")
    for item in discover_local_models():
        mark = "✓" if item["exists"] else "✗"
        size = f"{item['size_mb']} MB" if item["exists"] else "未下载"
        print(f"  [{mark}] {item['value']:<22} {size:<12} {item['label']}")
        if item.get("source"):
            print(f"        来源：{item['source']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 fire/smoke YOLOv8 权重")
    parser.add_argument("--list", action="store_true", help="只列出注册表与本地状态")
    parser.add_argument("--model", action="append", help="只处理指定模型（可重复）")
    parser.add_argument("--force", action="store_true", help="已存在也重新下载")
    parser.add_argument("--verify", action="store_true", help="下载后用 ultralytics 校验类别")
    args = parser.parse_args()

    if args.list:
        return cmd_list()

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    targets = args.model or list(MODEL_REGISTRY.keys())
    unknown = [n for n in targets if n not in MODEL_REGISTRY]
    if unknown:
        print(f"未知的模型名：{unknown}\n可选：{list(MODEL_REGISTRY)}")
        return 2

    failed: list[str] = []
    for name in targets:
        entry = MODEL_REGISTRY[name]
        dest = WEIGHTS_DIR / entry["filename"]
        print(f"\n▶ {name}  →  {dest.name}")

        if dest.exists() and not args.force and dest.stat().st_size >= MIN_BYTES:
            print(f"  已存在（{_human(dest.stat().st_size)}），跳过。加 --force 可强制重下。")
            if args.verify:
                _verify(dest)
            continue

        ok = False
        for url in entry["urls"]:
            print(f"  尝试：{url}")
            try:
                size = _download(url, dest)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                print(f"    下载失败：{exc}")
                continue
            if size < MIN_BYTES:
                print(f"    文件过小（{_human(size)}），可能是错误页面，忽略。")
                dest.unlink(missing_ok=True)
                continue
            print(f"    完成：{_human(size)}")
            ok = True
            break

        if not ok:
            failed.append(name)
            print("  全部下载源均失败，请手动下载后放入 weights/ 目录（README 有直链）。")
            continue

        if args.verify and not _verify(dest):
            failed.append(name)

    print()
    if failed:
        print(f"以下模型未就绪：{failed}")
        return 1

    total = sum(
        (WEIGHTS_DIR / e["filename"]).stat().st_size
        for e in MODEL_REGISTRY.values()
        if (WEIGHTS_DIR / e["filename"]).exists()
    )
    print(f"全部就绪，权重合计 {_human(total)}（{WEIGHTS_DIR}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
