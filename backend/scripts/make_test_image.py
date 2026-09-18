#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成一张合成测试图，供 CI / 本地跑通端到端自检使用。

用法（在 backend 目录下执行）::

    ../.venv/Scripts/python.exe scripts/make_test_image.py
    ../.venv/Scripts/python.exe scripts/make_test_image.py --out /tmp/t.jpg --width 960 --height 540

**用途与边界**：
  合成图用来验证「上传 → 推理 → 坐标契约 → JPEG 回传」这条**链路**是否通，
  图上没有真实火焰/烟雾，检出数通常为 0 —— 这是预期的，
  ``scripts/selftest.py`` 明确允许 ``counts.total == 0``。
  它**不用于**验证模型精度；精度验证请用真实火焰/烟雾素材。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# Windows 控制台默认 GBK，中文可能直接抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "testdata" / "synthetic.jpg"


def build(width: int, height: int) -> Image.Image:
    """深色背景 + 网格 + 中心暖色光斑，给模型一个「类火」候选区域。"""
    img = Image.new("RGB", (width, height), (30, 34, 42))
    draw = ImageDraw.Draw(img)

    # 背景结构线，模拟摄像头画面里的网格/墙面
    for x in range(0, width, max(1, width // 12)):
        draw.line([(x, 0), (x, height)], fill=(44, 50, 62), width=1)
    for y in range(0, height, max(1, height // 8)):
        draw.line([(0, y), (width, y)], fill=(44, 50, 62), width=1)

    # 由外向内叠加暖色椭圆：外圈暗、中心亮
    cx, cy = width * 0.5, height * 0.68
    steps = 90
    for i in range(steps, 0, -1):
        r = i / steps
        rx = width * 0.22 * r
        ry = height * 0.42 * r
        draw.ellipse(
            [cx - rx, cy - ry, cx + rx, cy + ry],
            fill=(
                int(255 * (1 - r) ** 0.6),
                int(120 * (1 - r) + 40),
                int(30 * (1 - r) ** 2),
            ),
        )
    return img


def main() -> int:
    parser = argparse.ArgumentParser(description="生成合成测试图（自检用）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"输出路径（默认 {DEFAULT_OUT}）")
    parser.add_argument("--width", type=int, default=960, help="宽度（默认 960）")
    parser.add_argument("--height", type=int, default=540, help="高度（默认 540）")
    parser.add_argument("--quality", type=int, default=90, help="JPEG 质量（默认 90）")
    args = parser.parse_args()

    if args.width < 32 or args.height < 32:
        print(f"尺寸过小：{args.width}x{args.height}")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    build(args.width, args.height).save(out, "JPEG", quality=args.quality)
    print(f"已生成 {out}（{args.width}x{args.height}，{out.stat().st_size} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
