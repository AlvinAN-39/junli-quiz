#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qr_svg.py — 极简 QR 码生成器（纯标准库，输出终端可读的方块图）
================================================================

为什么自己写：目标环境没有 `qrcode` / `segno` / PIL 之外的依赖，也不该让用户装包。
这里实现 QR Model 2，**字节模式**，纠错等级 M，版本 1~10 自动选择，
输出用「两个空格 = 白、两个实心块 = 黑」的字符画，终端里扫得出来；
同时可导出 SVG（矢量、可打印）。

参考：ISO/IEC 18004。仅覆盖实现所需的子集。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# GF(256) 运算（本原多项式 0x11D）
# ---------------------------------------------------------------------------
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n: int) -> list[int]:
    poly = [1]
    for i in range(n):
        poly = _poly_mul(poly, [1, _EXP[i]])
    return poly


def _poly_mul(a: list[int], b: list[int]) -> list[int]:
    out = [0] * (len(a) + len(b) - 1)
    for i, av in enumerate(a):
        if av == 0:
            continue
        for j, bv in enumerate(b):
            out[i + j] ^= _mul(av, bv)
    return out


def _rs_encode(data: list[int], ec_len: int) -> list[int]:
    gen = _rs_generator(ec_len)
    res = list(data) + [0] * ec_len
    for i in range(len(data)):
        coef = res[i]
        if coef == 0:
            continue
        for j, g in enumerate(gen):
            res[i + j] ^= _mul(g, coef)
    return res[len(data):]


# ---------------------------------------------------------------------------
# 版本表（版本 1~10，纠错等级 M）
# data_cw: 数据码字数；ec_cw: 每块纠错码字数；blocks: 块数（简化为等分）
# ---------------------------------------------------------------------------
VERSIONS_M = {
    # version: (total_codewords, ec_per_block, [(block_count, data_per_block), ...])
    1:  (26,   10, [(1, 16)]),
    2:  (44,   16, [(1, 28)]),
    3:  (70,   26, [(1, 44)]),
    4:  (100,  18, [(2, 32)]),
    5:  (134,  24, [(2, 43)]),
    6:  (172,  16, [(4, 27)]),
    7:  (196,  18, [(4, 31)]),
    8:  (242,  22, [(2, 38), (2, 39)]),
    9:  (292,  22, [(3, 36), (2, 37)]),
    10: (346,  26, [(4, 43), (1, 44)]),
}

ALIGN_CENTERS = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}


def _data_capacity(ver: int) -> int:
    _, _, parts = VERSIONS_M[ver]
    return sum(cnt * d for cnt, d in parts)


# ---------------------------------------------------------------------------
# 位缓冲
# ---------------------------------------------------------------------------
class _Bits:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def put(self, value: int, length: int) -> None:
        for i in range(length - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def to_bytes(self) -> list[int]:
        out = []
        for i in range(0, len(self.bits), 8):
            chunk = self.bits[i:i + 8]
            while len(chunk) < 8:
                chunk.append(0)
            b = 0
            for bit in chunk:
                b = (b << 1) | bit
            out.append(b)
        return out

    def __len__(self) -> int:
        return len(self.bits)


def _choose_version(nbytes: int) -> int:
    for ver in sorted(VERSIONS_M):
        cap = _data_capacity(ver)
        # 模式指示符 4bit + 字符计数（版本 1~9: 8bit；10: 16bit）
        cc = 8 if ver <= 9 else 16
        if 4 + cc + nbytes * 8 <= cap * 8:
            return ver
    raise ValueError("内容过长，超出本实现支持范围（版本 10 / 纠错 M）")


def _make_codewords(data: bytes) -> tuple[int, list[int]]:
    ver = _choose_version(len(data))
    total_cw, ec_per_block, parts = VERSIONS_M[ver]
    cap = _data_capacity(ver)
    cc_bits = 8 if ver <= 9 else 16

    bits = _Bits()
    bits.put(0b0100, 4)                 # 字节模式
    bits.put(len(data), cc_bits)
    for b in data:
        bits.put(b, 8)
    # 结束符
    remain = cap * 8 - len(bits)
    bits.put(0, min(4, remain))
    # 补齐到字节边界
    while len(bits) % 8:
        bits.put(0, 1)
    cw = bits.to_bytes()
    # 填充码字
    pads = (0xEC, 0x11)
    i = 0
    while len(cw) < cap:
        cw.append(pads[i % 2])
        i += 1

    # 分块 + 纠错 + 交织
    data_blocks: list[list[int]] = []
    ec_blocks: list[list[int]] = []
    pos = 0
    for cnt, dlen in parts:
        for _ in range(cnt):
            blk = cw[pos:pos + dlen]
            pos += dlen
            data_blocks.append(blk)
            ec_blocks.append(_rs_encode(blk, ec_per_block))

    max_d = max(len(b) for b in data_blocks)
    max_e = ec_per_block
    interleaved: list[int] = []
    for i in range(max_d):
        for b in data_blocks:
            if i < len(b):
                interleaved.append(b[i])
    for i in range(max_e):
        for b in ec_blocks:
            if i < len(b):
                interleaved.append(b[i])
    _ = total_cw
    return ver, interleaved


# ---------------------------------------------------------------------------
# 矩阵构造
# ---------------------------------------------------------------------------
def _new_matrix(size: int):
    return [[None] * size for _ in range(size)]


def _place_finder(m, row: int, col: int) -> None:
    for r in range(-1, 8):
        for c in range(-1, 8):
            rr, cc = row + r, col + c
            if not (0 <= rr < len(m) and 0 <= cc < len(m)):
                continue
            inside = (0 <= r <= 6 and 0 <= c <= 6)
            if not inside:
                m[rr][cc] = 0
                continue
            edge = r in (0, 6) or c in (0, 6)
            core = 2 <= r <= 4 and 2 <= c <= 4
            m[rr][cc] = 1 if (edge or core) else 0


def _place_alignment(m, centers: list[int]) -> None:
    for r in centers:
        for c in centers:
            if m[r][c] is not None:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    edge = max(abs(dr), abs(dc))
                    m[r + dr][c + dc] = 1 if edge != 1 else 0


def _place_timing(m) -> None:
    size = len(m)
    for i in range(8, size - 8):
        if m[6][i] is None:
            m[6][i] = 1 if i % 2 == 0 else 0
        if m[i][6] is None:
            m[i][6] = 1 if i % 2 == 0 else 0


def _reserve_format(m) -> None:
    size = len(m)
    for i in range(9):
        for (r, c) in ((8, i), (i, 8)):
            if 0 <= r < size and 0 <= c < size and m[r][c] is None:
                m[r][c] = 0
    for i in range(8):
        if m[8][size - 1 - i] is None:
            m[8][size - 1 - i] = 0
        if m[size - 1 - i][8] is None:
            m[size - 1 - i][8] = 0
    m[size - 8][8] = 1   # 固定暗模块


# 掩码函数
MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]

# 纠错等级 M 的格式信息位（5bit 数据），用于查表
_EC_BITS = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}


def _format_bits(ec: str, mask: int) -> int:
    data = (_EC_BITS[ec] << 3) | mask
    rem = data << 10
    for i in range(4, -1, -1):
        if rem & (1 << (i + 10)):
            rem ^= 0b10100110111 << i
    return ((data << 10) | rem) ^ 0b101010000010010


def _place_format(m, ec: str, mask: int) -> None:
    size = len(m)
    bits = _format_bits(ec, mask)
    for i in range(15):
        bit = (bits >> i) & 1
        # 左上
        if i < 6:
            m[8][i] = bit
        elif i == 6:
            m[8][7] = bit
        elif i == 7:
            m[8][8] = bit
        elif i == 8:
            m[7][8] = bit
        else:
            m[14 - i][8] = bit
        # 右上 / 左下
        if i < 8:
            m[8][size - 1 - i] = bit
        else:
            m[size - 15 + i][8] = bit
    m[size - 8][8] = 1


def _place_data(m, codewords: list[int], mask_id: int) -> None:
    size = len(m)
    bits: list[int] = []
    for cw in codewords:
        for i in range(7, -1, -1):
            bits.append((cw >> i) & 1)
    maskf = MASKS[mask_id]
    idx = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:          # 跳过垂直定时线
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if m[row][c] is None:
                    bit = bits[idx] if idx < len(bits) else 0
                    idx += 1
                    if maskf(row, c):
                        bit ^= 1
                    m[row][c] = bit
        upward = not upward
        col -= 2


def _penalty(m) -> int:
    size = len(m)
    score = 0
    # 规则 1：同色连续
    for line in list(m) + [list(col) for col in zip(*m)]:
        run = 1
        for i in range(1, size):
            if line[i] == line[i - 1]:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run = 1
        if run >= 5:
            score += 3 + (run - 5)
    # 规则 2：2x2 同色
    for r in range(size - 1):
        for c in range(size - 1):
            v = m[r][c]
            if v == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    # 规则 4：黑白比例
    dark = sum(sum(row) for row in m)
    ratio = dark * 100 // (size * size)
    score += 10 * (abs(ratio - 50) // 5)
    return score


def make_matrix(text: str) -> list[list[int]]:
    data = text.encode("utf-8")
    ver, codewords = _make_codewords(data)
    size = ver * 4 + 17

    best = None
    for mask_id in range(8):
        m = _new_matrix(size)
        _place_finder(m, 0, 0)
        _place_finder(m, 0, size - 7)
        _place_finder(m, size - 7, 0)
        _place_alignment(m, ALIGN_CENTERS[ver])
        _place_timing(m)
        _reserve_format(m)
        _place_data(m, codewords, mask_id)
        _place_format(m, "M", mask_id)
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    assert best is not None
    return best[1]


def render_terminal(text: str, compat: bool = False) -> str:
    """用「两个空格 = 白、两个实心块 = 黑」渲染，终端里可直接扫。

    `compat=True` 时使用 ASCII 风格的 '##'（在 cmd.exe 的旧代码页下更稳）。
    """
    m = make_matrix(text)
    size = len(m)
    dark = "##" if compat else "██"
    light = "  "
    lines = []
    border = light * (size + 4)
    lines.append(border)
    lines.append(border)
    for row in m:
        lines.append(light * 2 + "".join(dark if v else light for v in row) + light * 2)
    lines.append(border)
    lines.append(border)
    return "\n".join(lines)


def render_svg(text: str, scale: int = 8, quiet: int = 4) -> str:
    m = make_matrix(text)
    size = len(m)
    dim = (size + quiet * 2) * scale
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{dim}" height="{dim}" '
        f'viewBox="0 0 {dim} {dim}" shape-rendering="crispEdges">',
        f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>',
    ]
    for r, row in enumerate(m):
        for c, v in enumerate(row):
            if v:
                x = (c + quiet) * scale
                y = (r + quiet) * scale
                parts.append(f'<rect x="{x}" y="{y}" width="{scale}" height="{scale}" fill="#000000"/>')
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    import sys
    txt = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    print(render_terminal(txt))
    print(f"\n内容: {txt}")
