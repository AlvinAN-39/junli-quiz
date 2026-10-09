#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_icons.py — 从 app/icons/icon.svg 的设计参数生成 PNG 图标（纯标准库）
========================================================================

为什么需要 PNG：**iOS 的 apple-touch-icon 只认位图**，SVG 会被忽略，
主屏图标会退化成页面截图。manifest 里的 192/512 也按惯例给 PNG。
（本脚本不解析 SVG，而是把 icon.svg 的几何参数**复刻**成同一套图形：
 圆角矩形渐变底 + 白描边盾牌 + 金色五角星 + 两道书脊线。）

为什么用纯标准库：本项目 tools/ 一律零第三方依赖（见 tests/test_sources_compile.py）。
这里自带一个极小的扫描线光栅器 + PNG 编码器，4 倍超采样后降采样做抗锯齿，
输出稳定可复现（同一份代码跑两次得到完全相同的字节）。

用法：
    python tools/make_icons.py
产物（写入 app/icons/）：
    apple-touch-icon.png  180x180   iOS 主屏图标
    icon-192.png          192x192   manifest（any）
    icon-512.png          512x512   manifest（any + maskable）
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "icons"
SS = 4                      # 超采样倍数
UNIT = 64.0                 # icon.svg 的 viewBox 尺寸

# icon.svg 里的配色
BG_TOP = (0x1C, 0x7A, 0x49)
BG_BOTTOM = (0x0D, 0x3A, 0x26)
SHIELD = (255, 255, 255, int(0.92 * 255))
SHIELD_INNER = (255, 255, 255, int(0.08 * 255))
GOLD = (0xF2, 0xC0, 0x3A, 255)
GOLD_EDGE = (0xFF, 0xF8, 0xE1, int(0.5 * 255))
BAR1 = (255, 255, 255, int(0.85 * 255))
BAR2 = (255, 255, 255, int(0.55 * 255))


class Canvas:
    """RGBA 画布（bytearray），带 alpha 混合。"""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.buf = bytearray(w * h * 4)      # 全透明

    def blend(self, x: int, y: int, rgba):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        r, g, b, a = rgba
        if a <= 0:
            return
        i = (y * self.w + x) * 4
        buf = self.buf
        if a >= 255:
            buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = r, g, b, 255
            return
        sa = a / 255.0
        da = buf[i + 3] / 255.0
        oa = sa + da * (1 - sa)
        if oa <= 0:
            return
        for k, c in enumerate((r, g, b)):
            dc = buf[i + k]
            buf[i + k] = int(round((c * sa + dc * da * (1 - sa)) / oa))
        buf[i + 3] = int(round(oa * 255))

    def fill_polygon(self, pts, rgba):
        """扫描线（奇偶规则）填充多边形。"""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0, y1 = int(min(ys)), int(max(ys)) + 1
        n = len(pts)
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            yc = y + 0.5
            xs = []
            for i in range(n):
                x1, yy1 = pts[i]
                x2, yy2 = pts[(i + 1) % n]
                if (yy1 <= yc < yy2) or (yy2 <= yc < yy1):
                    xs.append(x1 + (yc - yy1) * (x2 - x1) / (yy2 - yy1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                xa, xb = xs[i], xs[i + 1]
                for x in range(max(0, int(xa)), min(self.w, int(xb) + 1)):
                    if xa <= x + 0.5 <= xb:
                        self.blend(x, y, rgba)

    def fill_round_rect(self, x, y, w, h, r, rgba):
        self.fill_polygon(round_rect_path(x, y, w, h, r), rgba)


def round_rect_path(x, y, w, h, r, steps=8):
    """圆角矩形 → 多边形点列（每角用圆弧采样）。"""
    import math
    pts = []
    corners = [
        (x + w - r, y + r, -math.pi / 2, 0),          # 右上
        (x + w - r, y + h - r, 0, math.pi / 2),       # 右下
        (x + r, y + h - r, math.pi / 2, math.pi),     # 左下
        (x + r, y + r, math.pi, math.pi * 1.5),       # 左上
    ]
    for cx, cy, a0, a1 in corners:
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def cubic(p0, p1, p2, p3, steps=14):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        pts.append((x, y))
    return pts


def shield_path(scale_to=1.0, inset=0.0):
    """icon.svg 的盾牌轮廓（外/内两套，按比例缩放）。"""
    def T(p):
        x = 32 + (p[0] - 32) * scale_to
        y = 32 + (p[1] - 32) * scale_to
        return (x, y)
    pts = [T((32, 7)), T((53, 15)), T((53, 30.5))]
    pts += cubic(T((53, 30.5)), T((53, 43)), T((44.5, 51.5)), T((32, 57)))
    pts += cubic(T((32, 57)), T((19.5, 51.5)), T((11, 43)), T((11, 30.5)))
    pts += [T((11, 15))]
    return pts


def inner_shield_path():
    pts = [(32, 12.5), (48, 18.8), (48, 30.4)]
    pts += cubic((48, 30.4), (48, 39.4), (41.6, 46), (32, 50.6))
    pts += cubic((32, 50.6), (22.4, 46), (16, 39.4), (16, 30.4))
    pts += [(16, 18.8)]
    return pts


STAR = [(32, 17), (35.06, 25.79), (44.36, 25.98), (36.95, 31.61), (39.64, 40.52),
        (32, 35.2), (24.36, 40.52), (27.05, 31.61), (19.64, 25.98), (28.94, 25.79)]


def render(size: int) -> bytes:
    """渲染一张 size×size 的 RGBA 像素表（4 倍超采样后降采样）。"""
    big = size * SS
    s = big / UNIT
    c = Canvas(big, big)

    # 1) 圆角矩形 + 竖向渐变底
    path = round_rect_path(0, 0, big, big, 14 * s, steps=24)
    for y in range(big):
        t = y / (big - 1)
        col = (int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t),
               int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t),
               int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t), 255)
        # 逐行填一次（扫描线在整宽上就是一行）
        ys = [p[1] for p in path]
        if y < min(ys) or y > max(ys):
            continue
        yc = y + 0.5
        xs = []
        n = len(path)
        for i in range(n):
            x1, y1 = path[i]
            x2, y2 = path[(i + 1) % n]
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(max(0, int(xs[i])), min(big, int(xs[i + 1]) + 1)):
                if xs[i] <= x + 0.5 <= xs[i + 1]:
                    c.blend(x, y, col)

    def P(pts):
        return [(x * s, y * s) for x, y in pts]

    # 2) 盾牌：外层白描边 + 内层极淡填充
    c.fill_polygon(P(shield_path()), SHIELD)
    c.fill_polygon(P(inner_shield_path()), SHIELD_INNER)

    # 3) 五角星（金色 + 浅描边）
    c.fill_polygon(P(STAR), GOLD)
    c.fill_polygon(P([(x + 0.35, y + 0.35) for x, y in STAR]), GOLD_EDGE)

    # 4) 两道书脊线（用圆角矩形模拟圆头线）
    c.fill_round_rect(22 * s, 46.4 * s, 20 * s, 2.2 * s, 1.1 * s, BAR1)
    c.fill_round_rect(25 * s, 41.6 * s, 14 * s, 2.0 * s, 1.0 * s, BAR2)

    # 5) 降采样（SS×SS 盒式平均 → 抗锯齿）
    out = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for dy in range(SS):
                for dx in range(SS):
                    i = ((y * SS + dy) * big + (x * SS + dx)) * 4
                    r += c.buf[i]; g += c.buf[i + 1]; b += c.buf[i + 2]; a += c.buf[i + 3]
            n = SS * SS
            o = (y * size + x) * 4
            out[o] = r // n; out[o + 1] = g // n; out[o + 2] = b // n; out[o + 3] = a // n
    return bytes(out)


def png_bytes(size: int, rgba: bytes) -> bytes:
    """把 RGBA 像素表编码成 PNG（无第三方依赖）。"""
    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)                       # filter: none
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)   # 8bit RGBA
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [("apple-touch-icon.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)]
    for name, size in targets:
        data = png_bytes(size, render(size))
        (OUT / name).write_bytes(data)
        print(f"  {name}  {size}x{size}  {len(data) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
