#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_qr_svg.py — `tools/qr_svg.py`（纯标准库 QR 生成器）的测试
========================================================================

QR 码是「错了也照样画出一张图」的典型：矩阵永远有 0/1，
但只有**可被符合规范的扫码器解码**才算正确。所以这里不满足于结构断言：

1. 用**独立复制的 ISO/IEC 18004 版本表 / 校正图形坐标表**交叉核对模块内的表；
2. 用**标准附录里的格式信息常量**核对 BCH 编码（L/M/Q/H + mask 0）；
3. 用**标准里的版本信息常量**核对 BCH(18,6) 编码（版本 7~10）；
4. 用**综合校验子全零**核对 RS 纠错编码（数学性质，不依赖生成多项式写法）；
5. 写一个**独立的逆向读取器**：功能模块几何图按规范**在测试里另写一份**
   （不复用 qr_svg 的放置函数），再还原掩码 → 反向蛇形扫描 → 反交织 →
   解析字节模式，把生成的矩阵真正解码回原文，并校验数据区格子数
   等于「码字数 × 8 + 剩余位」。

第 5 条曾经抓到真问题：版本 ≥ 7 时矩阵少了两个 18 位的版本信息块，
多出 36 个格子被当成数据区 —— 自洽的往返解码发现不了，只有按规范另写几何图才暴露。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import qr_svg as Q

# ---------------------------------------------------------------------------
# 独立常量表（ISO/IEC 18004）
# 刻意与 tools/qr_svg.py 各写一份：两份不一致即说明有人改动过实现或表。
# ---------------------------------------------------------------------------
# 表 9：纠错等级 M。version: (总码字数, 每块纠错码字, [(块数, 每块数据码字), ...])
ISO_VERSIONS_M = {
    1:  (26,  10, [(1, 16)]),
    2:  (44,  16, [(1, 28)]),
    3:  (70,  26, [(1, 44)]),
    4:  (100, 18, [(2, 32)]),
    5:  (134, 24, [(2, 43)]),
    6:  (172, 16, [(4, 27)]),
    7:  (196, 18, [(4, 31)]),
    8:  (242, 22, [(2, 38), (2, 39)]),
    9:  (292, 22, [(3, 36), (2, 37)]),
    10: (346, 26, [(4, 43), (1, 44)]),
}

# 表 1：剩余位（remainder bits）。数据区格子数 = 总码字数 × 8 + 剩余位。
ISO_REMAINDER_BITS = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7,
                      7: 0, 8: 0, 9: 0, 10: 0}

# 附录 E：校正图形中心坐标
ISO_ALIGN_CENTERS = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}

# 附录 C：格式信息常量（纠错等级 + mask 0）
ISO_FORMAT_MASK0 = {"L": 0x77C4, "M": 0x5412, "Q": 0x355F, "H": 0x1689}
FORMAT_XOR = 0b101010000010010

# 附录 D：版本信息常量（6 位版本号 + 12 位 BCH）
ISO_VERSION_BITS = {7: 0x07C94, 8: 0x085BC, 9: 0x09A99, 10: 0x0A4D3}

# 每个版本对应的**代表性载荷字节数**（按 _choose_version 的容量边界取）：
# 版本 1~9 用 8 位字符计数（n ≤ 数据码字数 - 2），版本 10 用 16 位（n ≤ 213）。
VERSION_PAYLOAD_BYTES = {1: 10, 2: 20, 3: 30, 4: 50, 5: 70,
                         6: 95, 7: 115, 8: 140, 9: 165, 10: 213}


# ---------------------------------------------------------------------------
# 测试侧的独立读取器
# ---------------------------------------------------------------------------
def _read_format_bits(m):
    """从矩阵读回 15 位格式信息（位置照规范）。"""
    bits = 0
    for i in range(15):
        if i < 6:
            b = m[8][i]
        elif i == 6:
            b = m[8][7]
        elif i == 7:
            b = m[8][8]
        elif i == 8:
            b = m[7][8]
        else:
            b = m[14 - i][8]
        bits |= (b & 1) << i
    return bits


def _read_version_bits(m, ver):
    """读回右上/左下两个版本信息块；版本 < 7 返回 (None, None)。"""
    if ver < 7:
        return None, None
    size = len(m)
    top_right = 0
    bottom_left = 0
    for i in range(18):
        top_right |= (m[i // 3][size - 11 + (i % 3)] & 1) << i
        bottom_left |= (m[size - 11 + (i % 3)][i // 3] & 1) << i
    return top_right, bottom_left


def _function_map(ver):
    """按规范**另写一份**功能模块几何图（True = 功能模块，不参与数据）。

    这是本测试独立性的关键：不复用 qr_svg 的 _place_finder/_place_alignment/…，
    否则写入端漏放某个图形时，读取端会「同样地漏」而自洽通过。
    """
    size = ver * 4 + 17
    fn = [[False] * size for _ in range(size)]

    # 定位图形 + 分隔符：三个角各 8×8
    for (r0, c0) in ((0, 0), (0, size - 8), (size - 8, 0)):
        for r in range(r0, r0 + 8):
            for c in range(c0, c0 + 8):
                fn[r][c] = True

    # 校正图形：与定位图形重叠的组合不画。
    # 必须在定时图形**之前**判定 —— 校正图形的中心可以落在定时线上
    # （如版本 10 的 (6,28) 与 (28,6)），先画定时线会把它们误判为「已占用」而漏掉。
    centers = ISO_ALIGN_CENTERS[ver]
    for r in centers:
        for c in centers:
            if fn[r][c]:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    fn[r + dr][c + dc] = True

    # 定时图形
    for i in range(8, size - 8):
        fn[6][i] = True
        fn[i][6] = True

    # 格式信息 + 固定暗模块
    for i in range(9):
        fn[8][i] = True
        fn[i][8] = True
    for i in range(8):
        fn[8][size - 1 - i] = True
        fn[size - 1 - i][8] = True

    # 版本信息（版本 7 及以上）：右上 6×3 + 左下 3×6
    if ver >= 7:
        for i in range(6):
            for j in range(3):
                fn[i][size - 11 + j] = True
                fn[size - 11 + j][i] = True

    return fn


def _data_bits(m, ver, mask_id):
    """反向蛇形扫描取回数据位，并还原掩码（数据区由 _function_map 判定）。"""
    size = len(m)
    fn = _function_map(ver)
    maskf = Q.MASKS[mask_id]
    bits = []
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if not fn[row][c]:
                    bit = m[row][c]
                    if maskf(row, c):
                        bit ^= 1
                    bits.append(bit)
        upward = not upward
        col -= 2
    return bits


def _bits_to_codewords(bits, n_codewords):
    out = []
    for i in range(n_codewords):
        b = 0
        for k in range(8):
            b = (b << 1) | bits[i * 8 + k]
        out.append(b)
    return out


def _deinterleave_data(cw, ver):
    """反交织：取出数据码字（按块顺序拼回原始数据流）。"""
    _total, _ecpb, parts = ISO_VERSIONS_M[ver]
    blocks = []
    for cnt, dlen in parts:
        for _ in range(cnt):
            blocks.append([dlen, []])
    max_d = max(dlen for dlen, _ in blocks)
    idx = 0
    for i in range(max_d):
        for b in blocks:
            if i < b[0]:
                b[1].append(cw[idx])
                idx += 1
    data = []
    for b in blocks:
        data.extend(b[1])
    return data


def decode_byte_mode(text):
    """把 make_matrix(text) 的结果解码回原文；返回 (版本, 纠错位, 掩码, 模式, 载荷)。"""
    m = Q.make_matrix(text)
    size = len(m)
    ver = (size - 17) // 4
    fmt = _read_format_bits(m) ^ FORMAT_XOR
    ec_bits = (fmt >> 13) & 0b11
    mask_id = (fmt >> 10) & 0b111

    total_cw = ISO_VERSIONS_M[ver][0]
    cw = _bits_to_codewords(_data_bits(m, ver, mask_id), total_cw)
    data = _deinterleave_data(cw, ver)

    bits = []
    for x in data:
        for i in range(7, -1, -1):
            bits.append((x >> i) & 1)

    pos = 0

    def take(n):
        nonlocal pos
        v = 0
        for _ in range(n):
            v = (v << 1) | bits[pos]
            pos += 1
        return v

    mode = take(4)
    cc_bits = 8 if ver <= 9 else 16
    n = take(cc_bits)
    payload = bytes(take(8) for _ in range(n))
    return ver, ec_bits, mask_id, mode, payload


def poly_eval(coeffs, x):
    """最高次项在前的多项式求值（GF(256)）。"""
    acc = 0
    for c in coeffs:
        acc = Q._mul(acc, x) ^ c
    return acc


class TestGaloisField(unittest.TestCase):
    def test_log_exp_are_inverses(self):
        for i in range(1, 256):
            with self.subTest(i=i):
                self.assertEqual(Q._EXP[Q._LOG[i]], i)

    def test_exp_table_wraps(self):
        for i in range(255, 512):
            self.assertEqual(Q._EXP[i], Q._EXP[i - 255])

    def test_mul_basic_laws(self):
        self.assertEqual(Q._mul(0, 123), 0)
        self.assertEqual(Q._mul(123, 0), 0)
        self.assertEqual(Q._mul(1, 123), 123)
        self.assertEqual(Q._mul(2, 3), 6)

    def test_mul_reduces_by_primitive_polynomial(self):
        # 0x80 << 1 = 0x100 → 按 0x11D 归约 → 0x1D
        self.assertEqual(Q._mul(0x80, 2), 0x1D)

    def test_mul_is_commutative_and_associative_on_samples(self):
        for a in (1, 2, 7, 53, 128, 200, 255):
            for b in (3, 17, 99, 200, 254):
                with self.subTest(a=a, b=b):
                    self.assertEqual(Q._mul(a, b), Q._mul(b, a))
                    for c in (5, 77, 250):
                        self.assertEqual(Q._mul(Q._mul(a, b), c),
                                         Q._mul(a, Q._mul(b, c)))


class TestReedSolomon(unittest.TestCase):
    def test_generator_degree_and_roots(self):
        for n in (10, 16, 18, 22, 26):
            with self.subTest(n=n):
                g = Q._rs_generator(n)
                self.assertEqual(len(g), n + 1)
                self.assertEqual(g[0], 1)
                for i in range(n):
                    self.assertEqual(poly_eval(g, Q._EXP[i]), 0)

    def test_encode_makes_all_syndromes_zero(self):
        """RS 码的判定性质：整码字在 α^0..α^(ec-1) 处取值必须全为 0。"""
        data = [0x10, 0x20, 0x0C, 0x56, 0x61, 0x80, 0xEC, 0x11,
                0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11]
        for ec_len in (10, 16, 18, 22, 26):
            with self.subTest(ec_len=ec_len):
                ec = Q._rs_encode(data, ec_len)
                self.assertEqual(len(ec), ec_len)
                full = data + ec
                self.assertEqual([poly_eval(full, Q._EXP[i]) for i in range(ec_len)],
                                 [0] * ec_len)

    def test_encode_of_zero_data_is_zero(self):
        self.assertEqual(Q._rs_encode([0] * 16, 10), [0] * 10)


class TestVersionTable(unittest.TestCase):
    def test_matches_iso_table(self):
        self.assertEqual(Q.VERSIONS_M, ISO_VERSIONS_M)

    def test_alignment_centers_match_iso_table(self):
        self.assertEqual(Q.ALIGN_CENTERS, ISO_ALIGN_CENTERS)

    def test_total_codewords_consistent(self):
        for ver, (total, ecpb, parts) in ISO_VERSIONS_M.items():
            with self.subTest(ver=ver):
                data = sum(cnt * dlen for cnt, dlen in parts)
                blocks = sum(cnt for cnt, _ in parts)
                self.assertEqual(data + blocks * ecpb, total)

    def test_data_capacity_matches_table(self):
        for ver, (_total, _ecpb, parts) in ISO_VERSIONS_M.items():
            with self.subTest(ver=ver):
                self.assertEqual(Q._data_capacity(ver),
                                 sum(cnt * dlen for cnt, dlen in parts))

    def test_choose_version_boundaries(self):
        # 版本 1~9 字符计数 8 位：4 + 8 + n*8 ≤ 16*8 → n ≤ 14
        self.assertEqual(Q._choose_version(1), 1)
        self.assertEqual(Q._choose_version(14), 1)
        self.assertEqual(Q._choose_version(15), 2)
        # 版本 10 容量 216 码字、字符计数 16 位：n ≤ 213
        self.assertEqual(Q._choose_version(213), 10)

    def test_choose_version_rejects_oversized_payload(self):
        with self.assertRaises(ValueError):
            Q._choose_version(214)
        with self.assertRaises(ValueError):
            Q.make_matrix("a" * 214)


class TestFormatInformation(unittest.TestCase):
    def test_bch_matches_standard_constants(self):
        for ec, want in ISO_FORMAT_MASK0.items():
            with self.subTest(ec=ec):
                self.assertEqual(Q._format_bits(ec, 0), want)

    def test_format_bits_depend_on_mask(self):
        seen = {Q._format_bits("M", m) for m in range(8)}
        self.assertEqual(len(seen), 8)

    def test_format_bits_round_trip_through_matrix(self):
        m = Q.make_matrix("https://example.com")
        fmt = _read_format_bits(m) ^ FORMAT_XOR
        ec_bits = (fmt >> 13) & 0b11
        mask_id = (fmt >> 10) & 0b111
        self.assertEqual(ec_bits, 0b00, "纠错等级应为 M")
        self.assertEqual(Q._format_bits("M", mask_id), _read_format_bits(m))


class TestVersionInformation(unittest.TestCase):
    """版本 7 起必须在右上、左下各写一个 18 位版本信息块。"""

    def test_bch_matches_standard_constants(self):
        for ver, want in ISO_VERSION_BITS.items():
            with self.subTest(ver=ver):
                self.assertEqual(Q._version_bits(ver), want)

    def test_version_bits_are_18_bit(self):
        for ver in range(7, 11):
            with self.subTest(ver=ver):
                self.assertLess(Q._version_bits(ver), 1 << 18)

    def test_place_version_info_is_noop_below_7(self):
        for ver in range(1, 7):
            size = ver * 4 + 17
            m = Q._new_matrix(size)
            Q._place_version_info(m, ver)
            self.assertTrue(all(v is None for row in m for v in row),
                            f"版本 {ver} 不应写入版本信息")

    def test_both_blocks_read_back_from_matrix(self):
        for ver in (7, 8, 9, 10):
            text = "a" * VERSION_PAYLOAD_BYTES[ver]
            with self.subTest(ver=ver):
                self.assertEqual(Q._choose_version(len(text.encode("utf-8"))), ver)
                m = Q.make_matrix(text)
                top_right, bottom_left = _read_version_bits(m, ver)
                self.assertEqual(top_right, ISO_VERSION_BITS[ver])
                self.assertEqual(bottom_left, ISO_VERSION_BITS[ver])

    def test_low_versions_have_no_version_info(self):
        m = Q.make_matrix("https://example.com")   # 版本 2
        top_right, bottom_left = _read_version_bits(m, 2)
        self.assertIsNone(top_right)
        self.assertIsNone(bottom_left)


class TestMatrixStructure(unittest.TestCase):
    def test_size_follows_version(self):
        for text in ("x", "https://example.com", "中文内容测试", "a" * 60):
            with self.subTest(text=text):
                ver = Q._choose_version(len(text.encode("utf-8")))
                self.assertEqual(len(Q.make_matrix(text)), ver * 4 + 17)

    def test_every_cell_is_binary(self):
        m = Q.make_matrix("https://example.com")
        for row in m:
            for v in row:
                self.assertIn(v, (0, 1))

    def test_finder_patterns(self):
        m = Q.make_matrix("https://example.com")
        size = len(m)
        for (r0, c0) in ((0, 0), (0, size - 7), (size - 7, 0)):
            for r in range(7):
                for c in range(7):
                    edge = r in (0, 6) or c in (0, 6)
                    core = 2 <= r <= 4 and 2 <= c <= 4
                    self.assertEqual(m[r0 + r][c0 + c], 1 if (edge or core) else 0,
                                     f"定位图形 ({r0},{c0}) 第 ({r},{c}) 格")

    def test_timing_patterns(self):
        m = Q.make_matrix("https://example.com")
        size = len(m)
        for i in range(8, size - 8):
            self.assertEqual(m[6][i], 1 if i % 2 == 0 else 0)
            self.assertEqual(m[i][6], 1 if i % 2 == 0 else 0)

    def test_dark_module(self):
        m = Q.make_matrix("https://example.com")
        self.assertEqual(m[len(m) - 8][8], 1)

    def test_alignment_patterns_present_from_version_2(self):
        m = Q.make_matrix("https://example.com")  # 19 字节 → 版本 2
        self.assertEqual(len(m), 25)
        self.assertEqual(m[18][18], 1)
        self.assertEqual(m[17][17], 0)

    def test_deterministic(self):
        self.assertEqual(Q.make_matrix("https://example.com"),
                         Q.make_matrix("https://example.com"))

    def test_chosen_mask_minimises_penalty(self):
        """掩码选择规则：取惩罚分最小者（并列时取序号较小者）。"""
        text = "https://example.com"
        ver, codewords = Q._make_codewords(text.encode("utf-8"))
        size = ver * 4 + 17
        scores = []
        for mask_id in range(8):
            m = Q._new_matrix(size)
            Q._place_finder(m, 0, 0)
            Q._place_finder(m, 0, size - 7)
            Q._place_finder(m, size - 7, 0)
            Q._place_alignment(m, Q.ALIGN_CENTERS[ver])
            Q._place_timing(m)
            Q._reserve_format(m)
            Q._place_version_info(m, ver)
            Q._place_data(m, codewords, mask_id)
            Q._place_format(m, "M", mask_id)
            scores.append(Q._penalty(m))
        expected = scores.index(min(scores))
        _ver, _ec, mask_id, _mode, _payload = decode_byte_mode(text)
        self.assertEqual(mask_id, expected)
        self.assertEqual(scores[expected], min(scores))


class TestDataRegion(unittest.TestCase):
    """数据区格子数必须严格等于「总码字数 × 8 + 剩余位」。"""

    def test_data_region_size_matches_spec(self):
        for ver in range(1, 11):
            with self.subTest(ver=ver):
                size = ver * 4 + 17
                fn = _function_map(ver)
                data_cells = sum(1 for row in fn for v in row if not v)
                total_cw = ISO_VERSIONS_M[ver][0]
                self.assertEqual(data_cells, total_cw * 8 + ISO_REMAINDER_BITS[ver])

    def test_version_payload_table_matches_choose_version(self):
        # 先证明测试用的载荷确实落在目标版本区间
        for ver, nbytes in VERSION_PAYLOAD_BYTES.items():
            with self.subTest(ver=ver):
                self.assertEqual(Q._choose_version(nbytes), ver)

    def test_function_map_matches_generated_matrix_shape(self):
        # 每个版本都真正生成一次，确保几何图与产物尺寸一致
        for ver, nbytes in VERSION_PAYLOAD_BYTES.items():
            text = "a" * nbytes
            with self.subTest(ver=ver):
                m = Q.make_matrix(text)
                self.assertEqual(len(m), ver * 4 + 17)
                self.assertEqual(len(_function_map(ver)), len(m))


class TestRoundTripDecode(unittest.TestCase):
    """端到端：生成的矩阵必须能被独立读取器解码回原文。"""

    CASES = (
        "x",
        "",
        "https://example.com",
        "中文测试内容",
        "a" * 14,        # 版本 1 上限
        "a" * 15,        # 版本 1 → 2 的边界
        "a" * 100,       # 版本 6（多块交织）
        "a" * 115,       # 版本 7（首次出现版本信息块）
        "a" * 140,       # 版本 8（两种块长交织）
        "a" * 165,       # 版本 9（3+2 块交织）
        "a" * 213,       # 版本 10（16 位字符计数）+ 上限
        "🇨🇳 军事理论 quiz?q=1&a=2",
    )

    def test_payload_round_trips(self):
        for text in self.CASES:
            with self.subTest(text=text[:24], nbytes=len(text.encode("utf-8"))):
                ver, ec_bits, mask_id, mode, payload = decode_byte_mode(text)
                self.assertEqual(mode, 0b0100, "必须是字节模式")
                self.assertEqual(ec_bits, 0b00, "纠错等级必须是 M")
                self.assertIn(mask_id, range(8))
                self.assertEqual(payload, text.encode("utf-8"))
                self.assertEqual(ver, Q._choose_version(len(text.encode("utf-8"))))

    def test_data_region_holds_exact_codewords_plus_remainder(self):
        for text in self.CASES:
            with self.subTest(text=text[:24]):
                m = Q.make_matrix(text)
                size = len(m)
                ver = (size - 17) // 4
                fmt = _read_format_bits(m) ^ FORMAT_XOR
                bits = _data_bits(m, ver, (fmt >> 10) & 0b111)
                total_cw = ISO_VERSIONS_M[ver][0]
                self.assertEqual(len(bits), total_cw * 8 + ISO_REMAINDER_BITS[ver])

    def test_all_codeword_blocks_satisfy_syndromes(self):
        """反交织后每块的 RS 综合校验子都必须为 0。"""
        for text in ("https://example.com", "a" * 100, "a" * 115, "a" * 165, "a" * 213):
            with self.subTest(text=text[:24]):
                m = Q.make_matrix(text)
                size = len(m)
                ver = (size - 17) // 4
                fmt = _read_format_bits(m) ^ FORMAT_XOR
                total_cw = ISO_VERSIONS_M[ver][0]
                cw = _bits_to_codewords(_data_bits(m, ver, (fmt >> 10) & 0b111), total_cw)

                _total, ecpb, parts = ISO_VERSIONS_M[ver]
                blocks = []
                for cnt, dlen in parts:
                    for _ in range(cnt):
                        blocks.append([dlen, []])
                idx = 0
                max_d = max(dlen for dlen, _ in blocks)
                for i in range(max_d):
                    for b in blocks:
                        if i < b[0]:
                            b[1].append(cw[idx])
                            idx += 1
                for i in range(ecpb):
                    for b in blocks:
                        b[1].append(cw[idx])
                        idx += 1
                for b in blocks:
                    self.assertEqual(
                        [poly_eval(b[1], Q._EXP[i]) for i in range(ecpb)],
                        [0] * ecpb, "某数据块纠错码字不满足 RS 校验子")


class TestRenderers(unittest.TestCase):
    def test_terminal_dimensions(self):
        text = "https://example.com"
        size = len(Q.make_matrix(text))
        out = Q.render_terminal(text).split("\n")
        self.assertEqual(len(out), size + 4)
        for line in out:
            self.assertEqual(len(line), (size + 4) * 2)

    def test_terminal_compat_uses_ascii(self):
        text = "https://example.com"
        normal = Q.render_terminal(text, compat=False)
        compat = Q.render_terminal(text, compat=True)
        self.assertIn("██", normal)
        self.assertNotIn("██", compat)
        self.assertIn("##", compat)

    def test_terminal_border_rows_are_blank(self):
        out = Q.render_terminal("x").split("\n")
        for line in (out[0], out[1], out[-1], out[-2]):
            self.assertEqual(line.strip(), "")

    def test_svg_is_wellformed_and_sized(self):
        text = "https://example.com"
        svg = Q.render_svg(text, scale=8, quiet=4)
        size = len(Q.make_matrix(text))
        dim = (size + 8) * 8
        self.assertTrue(svg.startswith("<svg "))
        self.assertTrue(svg.rstrip().endswith("</svg>"))
        self.assertIn(f'width="{dim}"', svg)
        self.assertIn(f'height="{dim}"', svg)
        self.assertIn(f'viewBox="0 0 {dim} {dim}"', svg)

    def test_svg_rect_count_matches_dark_modules(self):
        text = "https://example.com"
        m = Q.make_matrix(text)
        dark = sum(sum(row) for row in m)
        svg = Q.render_svg(text)
        # 1 个白色底 + 每个黑模块 1 个 rect
        self.assertEqual(len(re.findall(r"<rect ", svg)), dark + 1)

    def test_svg_respects_scale_and_quiet_zone(self):
        svg = Q.render_svg("x", scale=3, quiet=0)
        size = len(Q.make_matrix("x"))
        dim = size * 3
        self.assertIn(f'width="{dim}"', svg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
