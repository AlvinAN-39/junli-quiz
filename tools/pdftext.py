#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdftext.py — 纯 Python 标准库实现的 PDF 文字层提取器
=====================================================

背景：本机 Python 环境没有 pypdf / PyMuPDF / pdfminer / pdfplumber，
因此本模块只依赖标准库（zlib / re / sys / json / pathlib）来还原 PDF 文字。

支持：
  * 交叉引用表 + `/XRef` 流 + `/ObjStm` 对象流（PDF 1.5+，FlateDecode）
  * 页面树遍历（/Root -> /Pages -> /Kids），按真实页码顺序输出
  * 内容流解析：BT/ET、Tf、Td/TD/Tm/T*、TL、Tj、TJ、'、"、Do(Form XObject 递归)
  * Type0 CID 字体：/Encoding /Identity-H、/ToUnicode CMap（bfchar/bfrange，含数组目标）
  * 简单字体：内置 WinAnsi/Standard 编码 + /Differences 差异数组
  * 字符串转义：\\n \\r \\t \\b \\f \\( \\) \\\\ \\ddd，以及 <十六进制串>
  * 基于文本矩阵 y 位移的自动换行 / 段落分隔 / 按宽度插空格

用法：
    python pdftext.py <input.pdf> <output.txt> [--verbose]
"""

from __future__ import annotations

import re
import sys
import zlib
from pathlib import Path

# --------------------------------------------------------------------------
# 1. 基础工具
# --------------------------------------------------------------------------

WHITESPACE = b"\x00\t\n\x0c\r "
DELIMITERS = b"()<>[]{}/%"


def is_ws(b: int) -> bool:
    return b in WHITESPACE


def is_delim(b: int) -> bool:
    return b in DELIMITERS


def is_regular(b: int) -> bool:
    return not is_ws(b) and not is_delim(b)


def to_int(b: bytes, default: int = 0) -> int:
    try:
        return int(b)
    except (TypeError, ValueError):
        try:
            return int(float(b))
        except (TypeError, ValueError):
            return default


def to_float(b, default: float = 0.0) -> float:
    try:
        return float(b)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# 2. 词法分析器：把 PDF 对象语法切成 token / 对象
# --------------------------------------------------------------------------

class Lexer:
    """极简 PDF 对象词法分析器。"""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos
        self.n = len(data)

    def skip_ws(self) -> None:
        d, n = self.data, self.n
        while self.pos < n:
            c = d[self.pos]
            if c in WHITESPACE:
                self.pos += 1
            elif c == 0x25:  # '%' 注释到行尾
                while self.pos < n and d[self.pos] not in b"\r\n":
                    self.pos += 1
            else:
                return

    def read_token(self) -> bytes:
        """读一个裸 token（关键字或数字）。"""
        self.skip_ws()
        d, n, start = self.data, self.n, self.pos
        while self.pos < n and is_regular(d[self.pos]):
            self.pos += 1
        if self.pos == start:  # 定界符本身
            self.pos += 1
            return d[start:self.pos]
        return d[start:self.pos]

    def peek_keyword(self) -> bytes:
        save = self.pos
        tok = self.read_token()
        self.pos = save
        return tok

    def read_literal_string(self) -> bytes:
        """读取 (...) 字符串，返回已解码的原始字节。"""
        d, n = self.data, self.n
        assert d[self.pos] == 0x28
        self.pos += 1
        depth = 1
        out = bytearray()
        while self.pos < n:
            c = d[self.pos]
            if c == 0x5C:  # backslash
                self.pos += 1
                if self.pos >= n:
                    break
                e = d[self.pos]
                if e in b"nrtbf":
                    out.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}[e])
                    self.pos += 1
                elif e in b"()\\":
                    out.append(e)
                    self.pos += 1
                elif 0x30 <= e <= 0x37:  # 八进制最多 3 位
                    oct_digits = bytearray()
                    while self.pos < n and len(oct_digits) < 3 and 0x30 <= d[self.pos] <= 0x37:
                        oct_digits.append(d[self.pos])
                        self.pos += 1
                    out.append(int(oct_digits, 8) & 0xFF)
                elif e == 0x0D:  # 行继续
                    self.pos += 1
                    if self.pos < n and d[self.pos] == 0x0A:
                        self.pos += 1
                elif e == 0x0A:
                    self.pos += 1
                else:
                    out.append(e)
                    self.pos += 1
            elif c == 0x28:
                depth += 1
                out.append(c)
                self.pos += 1
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    self.pos += 1
                    break
                out.append(c)
                self.pos += 1
            else:
                out.append(c)
                self.pos += 1
        return bytes(out)

    def read_hex_string(self) -> bytes:
        """读取 <...> 十六进制字符串，返回解码字节。"""
        d, n = self.data, self.n
        assert d[self.pos] == 0x3C
        self.pos += 1
        digits = bytearray()
        while self.pos < n and d[self.pos] != 0x3E:
            c = d[self.pos]
            if not is_ws(c):
                digits.append(c)
            self.pos += 1
        self.pos += 1  # 跳过 '>'
        if len(digits) % 2:
            digits.append(0x30)
        try:
            return bytes.fromhex(digits.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return b""


class Name(str):
    """PDF 名字对象 /Foo"""
    __slots__ = ()


class Ref:
    """间接引用 12 0 R"""
    __slots__ = ("num", "gen")

    def __init__(self, num: int, gen: int = 0):
        self.num = num
        self.gen = gen

    def __repr__(self) -> str:
        return f"Ref({self.num})"

    def __eq__(self, other):
        return isinstance(other, Ref) and other.num == self.num

    def __hash__(self):
        return hash(("Ref", self.num))


class Stream:
    __slots__ = ("dict", "raw", "doc")

    def __init__(self, d: dict, raw: bytes, doc):
        self.dict = d
        self.raw = raw
        self.doc = doc

    def get_data(self) -> bytes:
        """按 /Filter 链解码流数据。"""
        data = self.raw
        filters = self.dict.get("Filter")
        parms = self.dict.get("DecodeParms") or self.dict.get("DP")
        if filters is None:
            return data
        if not isinstance(filters, list):
            filters = [filters]
            parms = [parms]
        elif not isinstance(parms, list):
            parms = [parms] * len(filters)
        while len(parms) < len(filters):
            parms.append(None)
        for f, p in zip(filters, parms):
            fname = str(f)
            if fname in ("FlateDecode", "Fl"):
                try:
                    data = zlib.decompress(data)
                except zlib.error:
                    try:
                        data = zlib.decompressobj().decompress(data)
                    except zlib.error:
                        try:  # 容错：跳过损坏头部
                            data = zlib.decompressobj().decompress(data[2:])
                        except zlib.error:
                            return b""
                if isinstance(p, dict) and to_int(p.get("Predictor", 0)) >= 2:
                    data = apply_predictor(data, p)
            elif fname in ("ASCIIHexDecode", "AHx"):
                hexpart = re.sub(rb"[^0-9A-Fa-f>]", b"", data).split(b">")[0]
                if len(hexpart) % 2:
                    hexpart += b"0"
                try:
                    data = bytes.fromhex(hexpart.decode("ascii"))
                except (ValueError, UnicodeDecodeError):
                    return b""
            elif fname in ("ASCII85Decode", "A85"):
                try:
                    import base64
                    data = base64.a85decode(data, adobe=True)
                except Exception:
                    return b""
            elif fname in ("LZWDecode", "LZW"):
                data = lzw_decode(data)
            elif fname in ("DCTDecode", "JPXDecode", "CCITTFaxDecode", "JBIG2Decode"):
                return b""  # 图片流，无文字
            elif fname in ("Crypt",):
                continue
            else:
                return data
        return data


def apply_predictor(data: bytes, parms: dict) -> bytes:
    """PNG / TIFF predictor（用于 XRef 流与部分内容流）。"""
    pred = to_int(parms.get("Predictor", 1))
    colors = to_int(parms.get("Colors", 1))
    bpc = to_int(parms.get("BitsPerComponent", 8))
    columns = to_int(parms.get("Columns", 1))
    if pred < 2:
        return data
    bpp = max(1, (colors * bpc + 7) // 8)
    rowlen = (columns * colors * bpc + 7) // 8
    if pred == 2:  # TIFF predictor（仅支持 8bit）
        if bpc != 8:
            return data
        out = bytearray(data)
        for r in range(0, len(out) - rowlen + 1, rowlen):
            for i in range(bpp, rowlen):
                out[r + i] = (out[r + i] + out[r + i - bpp]) & 0xFF
        return bytes(out)
    # PNG predictors
    out = bytearray()
    prev = bytearray(rowlen)
    i = 0
    n = len(data)
    while i + 1 <= n:
        ft = data[i]
        i += 1
        row = bytearray(data[i:i + rowlen])
        if len(row) < rowlen:
            row.extend(b"\x00" * (rowlen - len(row)))
        i += rowlen
        if ft == 1:
            for j in range(bpp, rowlen):
                row[j] = (row[j] + row[j - bpp]) & 0xFF
        elif ft == 2:
            for j in range(rowlen):
                row[j] = (row[j] + prev[j]) & 0xFF
        elif ft == 3:
            for j in range(rowlen):
                left = row[j - bpp] if j >= bpp else 0
                row[j] = (row[j] + ((left + prev[j]) >> 1)) & 0xFF
        elif ft == 4:
            for j in range(rowlen):
                a = row[j - bpp] if j >= bpp else 0
                b = prev[j]
                c = prev[j - bpp] if j >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[j] = (row[j] + pr) & 0xFF
        out.extend(row)
        prev = row
        if i >= n:
            break
    return bytes(out)


def lzw_decode(data: bytes, early: int = 1) -> bytes:
    """LZW 解码（PDF 用，必要时回退）。"""
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    bitpos = 0
    codelen = 9
    prev = None
    total_bits = len(data) * 8
    while bitpos + codelen <= total_bits:
        byte_i = bitpos >> 3
        chunk = int.from_bytes(data[byte_i:byte_i + 3].ljust(3, b"\x00"), "big")
        code = (chunk >> (24 - codelen - (bitpos & 7))) & ((1 << codelen) - 1)
        bitpos += codelen
        if code == 256:
            table = [bytes([i]) for i in range(256)] + [b"", b""]
            codelen = 9
            prev = None
            continue
        if code == 257:
            break
        if prev is None:
            entry = table[code]
        else:
            if code < len(table):
                entry = table[code]
                table.append(prev + entry[:1])
            else:
                entry = prev + prev[:1]
                table.append(entry)
        out.extend(entry)
        prev = entry
        if len(table) + early >= (1 << codelen) and codelen < 12:
            codelen += 1
    return bytes(out)


# --------------------------------------------------------------------------
# 3. PDF 文档：对象装载、对象流、页面树
# --------------------------------------------------------------------------

class PDFDocument:
    def __init__(self, path: Path, verbose: bool = False):
        self.path = path
        self.verbose = verbose
        self.data = path.read_bytes()
        self.objects: dict[int, object] = {}
        self.trailer: dict = {}
        self._load()

    # ---------------- 对象解析 ----------------

    def _load(self) -> None:
        data = self.data
        # 先扫所有 "N G obj" 直接对象
        for m in re.finditer(rb"(?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b", data):
            num = int(m.group(1))
            if num in self.objects:
                continue
            try:
                obj = self._parse_object_at(m.end())
            except Exception:
                continue
            if obj is not None:
                self.objects[num] = obj
        self._load_objstms()
        self.trailer = self._find_trailer()
        if self.verbose:
            print(f"  [pdf] 直接对象 {len(self.objects)} 个", file=sys.stderr)

    def _find_trailer(self) -> dict:
        idx = self.data.rfind(b"trailer")
        if idx >= 0:
            try:
                lx = Lexer(self.data, idx + len(b"trailer"))
                t = lx.parse_object()
                if isinstance(t, dict):
                    return t
            except Exception:
                pass
        # 回退：XRef 流里找 /Root
        for m in re.finditer(rb"/Root\s+(\d+)\s+\d+\s+R", self.data):
            return {"Root": Ref(int(m.group(1)))}
        return {}

    def _load_objstms(self) -> None:
        """展开 /ObjStm 对象流（PDF 1.5+）。"""
        for num in list(self.objects.keys()):
            obj = self.objects[num]
            if not isinstance(obj, Stream):
                continue
            if str(obj.dict.get("Type", "")) != "ObjStm":
                continue
            try:
                payload = obj.get_data()
                n = to_int(obj.dict.get("N", 0))
                first = to_int(obj.dict.get("First", 0))
                header = payload[:first]
                nums = [int(x) for x in re.findall(rb"\d+", header)]
                pairs = list(zip(nums[0::2], nums[1::2]))[:n]
                for i, (onum, off) in enumerate(pairs):
                    start = first + off
                    end = first + pairs[i + 1][1] if i + 1 < len(pairs) else len(payload)
                    if onum in self.objects:
                        continue
                    try:
                        lx = Lexer(payload[start:end])
                        self.objects[onum] = lx.parse_object()
                    except Exception:
                        continue
            except Exception:
                continue

    def _parse_object_at(self, pos: int):
        lx = Lexer(self.data, pos)
        obj = lx.parse_object()
        # 可能是流：检测 stream / endstream
        lx.skip_ws()
        if isinstance(obj, dict) and self.data[lx.pos:lx.pos + 6] == b"stream":
            lx.pos += 6
            if self.data[lx.pos:lx.pos + 2] == b"\r\n":
                lx.pos += 2
            elif self.data[lx.pos:lx.pos + 1] in (b"\n", b"\r"):
                lx.pos += 1
            length = obj.get("Length")
            resolved = self.resolve(length)
            start = lx.pos
            if isinstance(resolved, int) and 0 <= resolved <= len(self.data) - start:
                raw = self.data[start:start + resolved]
            else:
                end = self.data.find(b"endstream", start)
                raw = self.data[start:end if end >= 0 else len(self.data)]
                if raw.endswith(b"\r\n"):
                    raw = raw[:-2]
                elif raw.endswith(b"\n") or raw.endswith(b"\r"):
                    raw = raw[:-1]
            return Stream(obj, raw, self)
        return obj

    def resolve(self, obj):
        """跟随间接引用。"""
        seen = 0
        while isinstance(obj, Ref) and seen < 64:
            obj = self.objects.get(obj.num)
            seen += 1
        return obj

    # ---------------- 页面遍历 ----------------

    def get_pages(self) -> list[dict]:
        root = self.resolve(self.trailer.get("Root"))
        pages: list[dict] = []
        if isinstance(root, dict):
            pages_obj = self.resolve(root.get("Pages"))
            if isinstance(pages_obj, dict):
                self._walk_pages(pages_obj, pages, set(), 0)
        if not pages:
            # 回退：直接按对象号找 /Type /Page
            for num in sorted(self.objects):
                o = self.objects[num]
                if isinstance(o, dict) and str(o.get("Type", "")) == "Page":
                    pages.append(o)
        return pages

    def _walk_pages(self, node: dict, out: list, seen: set, depth: int) -> None:
        if depth > 64 or id(node) in seen:
            return
        seen.add(id(node))
        ntype = str(node.get("Type", ""))
        if ntype == "Page":
            out.append(node)
            return
        kids = self.resolve(node.get("Kids"))
        if isinstance(kids, list):
            for k in kids:
                kk = self.resolve(k)
                if isinstance(kk, dict):
                    self._walk_pages(kk, out, seen, depth + 1)


# 把 parse_object 挂到 Lexer 上（放在这里便于阅读，逻辑与 Lexer 紧耦合）
def _lexer_parse_object(self: Lexer):
    self.skip_ws()
    if self.pos >= self.n:
        return None
    d = self.data
    c = d[self.pos]

    if c == 0x2F:  # /Name
        self.pos += 1
        start = self.pos
        while self.pos < self.n and is_regular(d[self.pos]):
            self.pos += 1
        raw = d[start:self.pos]
        out = bytearray()
        i = 0
        while i < len(raw):
            if raw[i] == 0x23 and i + 2 < len(raw):  # #XX 转义
                try:
                    out.append(int(raw[i + 1:i + 3], 16))
                    i += 3
                    continue
                except ValueError:
                    pass
            out.append(raw[i])
            i += 1
        return Name(out.decode("latin-1"))

    if c == 0x28:  # (string)
        return self.read_literal_string()

    if c == 0x3C:  # <hex> 或 <<dict>>
        if d[self.pos:self.pos + 2] == b"<<":
            self.pos += 2
            result: dict = {}
            while True:
                self.skip_ws()
                if d[self.pos:self.pos + 2] == b">>":
                    self.pos += 2
                    break
                if self.pos >= self.n:
                    break
                key = self.parse_object()
                if key is None:
                    break
                val = self.parse_object()
                result[str(key)] = val
            return result
        return self.read_hex_string()

    if c == 0x5B:  # [array]
        self.pos += 1
        arr = []
        while True:
            self.skip_ws()
            if self.pos >= self.n:
                break
            if d[self.pos] == 0x5D:
                self.pos += 1
                break
            v = self.parse_object()
            if v is None:
                break
            arr.append(v)
        return arr

    if c == 0x5D or c == 0x3E:
        self.pos += 1
        return None

    # 数字 / 引用 / 关键字
    tok = self.read_token()
    if not tok:
        self.pos += 1
        return None
    if re.fullmatch(rb"[+-]?\d+", tok):
        # 可能是 "N G R"
        save = self.pos
        self.skip_ws()
        tok2 = self.read_token()
        if re.fullmatch(rb"\d+", tok2):
            self.skip_ws()
            tok3 = self.read_token()
            if tok3 == b"R":
                return Ref(int(tok), int(tok2))
        self.pos = save
        return int(tok)
    if re.fullmatch(rb"[+-]?(\d*\.\d*|\d+)", tok):
        return to_float(tok)
    if tok == b"true":
        return True
    if tok == b"false":
        return False
    if tok == b"null":
        return None
    return tok.decode("latin-1", "replace")


Lexer.parse_object = _lexer_parse_object  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# 4. ToUnicode CMap 解析
# --------------------------------------------------------------------------

def _decode_cmap_hex(token: str) -> str:
    """把 CMap 里的十六进制目标串解码成 Unicode 文本。"""
    token = token.strip().strip("<>")
    if not token:
        return ""
    if len(token) % 2:
        token += "0"
    try:
        raw = bytes.fromhex(token)
    except ValueError:
        return ""
    if len(raw) >= 2 and len(raw) % 2 == 0:
        # 优先按 UTF-16BE 解；若含 BOM 或高位字节，UTF-16BE 一般正确
        try:
            txt = raw.decode("utf-16-be")
            if txt.strip("\x00"):
                return txt
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("latin-1")
    except Exception:
        return ""


def parse_tounicode_cmap(data: bytes) -> dict[int, str]:
    """解析 ToUnicode CMap，返回 {code: text}。支持 bfchar 与 bfrange。"""
    mapping: dict[int, str] = {}
    if not data:
        return mapping
    text = data.decode("latin-1", "replace")

    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            try:
                code = int(src, 16)
            except ValueError:
                continue
            mapping[code] = _decode_cmap_hex(dst)

    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        # 形式 1: <lo> <hi> <dst>
        for lo, hi, dst in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block
        ):
            try:
                lo_i, hi_i = int(lo, 16), int(hi, 16)
            except ValueError:
                continue
            if hi_i < lo_i or hi_i - lo_i > 65535:
                continue
            base = _decode_cmap_hex(dst)
            if not base:
                for c in range(lo_i, hi_i + 1):
                    mapping.setdefault(c, "")
                continue
            # 逐字符偏移（仅对 BMP 单字符增量正确）
            for k in range(hi_i - lo_i + 1):
                if k == 0:
                    mapping.setdefault(lo_i, base)
                else:
                    mapping.setdefault(lo_i + k, chr(ord(base[0]) + k) + base[1:]
                                       if ord(base[-1]) + k <= 0x10FFFF else base + chr(k))
        # 形式 2: <lo> <hi> [ <d1> <d2> ... ]
        for lo, hi, arr in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", block, re.S
        ):
            try:
                lo_i = int(lo, 16)
            except ValueError:
                continue
            items = re.findall(r"<([0-9A-Fa-f]*)>", arr)
            for k, item in enumerate(items):
                mapping.setdefault(lo_i + k, _decode_cmap_hex(item))
    return mapping


# --------------------------------------------------------------------------
# 5. 字体
# --------------------------------------------------------------------------

# 常见简单字体的 WinAnsi 编码近似（PDF 未给 ToUnicode 时兜底）
_WINANSI_HIGH = {
    0x80: "\u20ac", 0x82: "\u201a", 0x83: "\u0192", 0x84: "\u201e", 0x85: "\u2026",
    0x86: "\u2020", 0x87: "\u2021", 0x88: "\u02c6", 0x89: "\u2030", 0x8a: "\u0160",
    0x8b: "\u2039", 0x8c: "\u0152", 0x8e: "\u017d", 0x91: "\u2018", 0x92: "\u2019",
    0x93: "\u201c", 0x94: "\u201d", 0x95: "\u2022", 0x96: "\u2013", 0x97: "\u2014",
    0x98: "\u02dc", 0x99: "\u2122", 0x9a: "\u0161", 0x9b: "\u203a", 0x9c: "\u0153",
    0x9e: "\u017e", 0x9f: "\u0178",
}


class FontInfo:
    __slots__ = ("name", "is_cid", "cmap", "bytes_per_code", "simple_map")

    def __init__(self, name: str):
        self.name = name
        self.is_cid = False
        self.cmap: dict[int, str] = {}
        self.bytes_per_code = 1
        self.simple_map: dict[int, str] = {}

    def decode(self, raw: bytes) -> str:
        """把字符串原始字节解码为 Unicode。"""
        if raw is None:
            return ""
        if self.bytes_per_code == 2 or self.is_cid:
            codes = [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw) - 1, 2)]
            out = []
            for c in codes:
                if c in self.cmap:
                    out.append(self.cmap[c])
                elif c >= 0x20 and c < 0x7F:
                    out.append(chr(c))
                else:
                    out.append("")
            return "".join(out)
        # 简单字体
        out = []
        for b in raw:
            if b in self.simple_map:
                out.append(self.simple_map[b])
            elif 0x20 <= b <= 0x7E:
                out.append(chr(b))
            elif b in _WINANSI_HIGH:
                out.append(_WINANSI_HIGH[b])
            elif b >= 0xA0:
                out.append(chr(b))  # Latin-1 近似
            elif b in (0x09, 0x0A, 0x0D):
                out.append(" ")
            else:
                out.append("")
        return "".join(out)


def load_font(doc: PDFDocument, font_dict: dict, name: str) -> FontInfo:
    fi = FontInfo(name)
    fd = doc.resolve(font_dict.get("FontDescriptor")) if isinstance(font_dict, dict) else None
    subtype = str(font_dict.get("Subtype", "")) if isinstance(font_dict, dict) else ""

    # 类型0（CID）：走 DescendantFonts -> CIDFont，取 W/Encoding，并用 ToUnicode 映射
    if subtype == "Type0" or "DescendantFonts" in font_dict:
        fi.is_cid = True
        fi.bytes_per_code = 2
        enc = str(font_dict.get("Encoding", ""))
        if "Identity" in enc:
            fi.bytes_per_code = 2
        tu = doc.resolve(font_dict.get("ToUnicode"))
        if isinstance(tu, Stream):
            fi.cmap = parse_tounicode_cmap(tu.get_data())
        if not fi.cmap and fi.bytes_per_code == 2:
            # 无 ToUnicode：尝试从 CIDSystemInfo 猜测（GBK-EUC-H 等），失败则 ASCII 兜底
            desc = doc.resolve(font_dict.get("DescendantFonts"))
            if isinstance(desc, list) and desc:
                d0 = doc.resolve(desc[0])
                if isinstance(d0, dict):
                    csi = doc.resolve(d0.get("CIDSystemInfo"))
                    if isinstance(csi, dict):
                        reg = str(csi.get("Registry", ""))
                        if "Adobe" in reg and str(csi.get("Ordering", "")) == "GB1":
                            for c in range(0x20, 0x7F):
                                fi.cmap[c] = chr(c)
        return fi

    # 简单字体
    tu = doc.resolve(font_dict.get("ToUnicode"))
    if isinstance(tu, Stream):
        cm = parse_tounicode_cmap(tu.get_data())
        if cm:
            fi.simple_map = {k: v for k, v in cm.items() if k <= 0xFF}
            return fi
    # /Differences
    enc = doc.resolve(font_dict.get("Encoding"))
    if isinstance(enc, dict):
        diff = doc.resolve(enc.get("Differences"))
        if isinstance(diff, list):
            cur = 0
            for item in diff:
                if isinstance(item, (int, float)):
                    cur = int(item)
                else:
                    nm = str(item)
                    fi.simple_map[cur] = _glyph_name_to_text(nm)
                    cur += 1
    if fd and fi.simple_map:
        pass
    return fi


_GLYPH_NAMES = {
    "space": " ", "quotesingle": "'", "quotedblleft": "\u201c", "quotedblright": "\u201d",
    "quoteleft": "\u2018", "quoteright": "\u2019", "endash": "\u2013", "emdash": "\u2014",
    "bullet": "\u2022", "ellipsis": "\u2026", "period": ".", "comma": ",", "colon": ":",
    "semicolon": ";", "question": "?", "exclam": "!", "parenleft": "(", "parenright": ")",
    "bracketleft": "[", "bracketright": "]", "hyphen": "-", "slash": "/", "percent": "%",
    "numbersign": "#", "dollar": "$", "ampersand": "&", "asterisk": "*", "plus": "+",
    "equal": "=", "underscore": "_", "at": "@", "asciitilde": "~", "bar": "|",
    "braceleft": "{", "braceright": "}", "less": "<", "greater": ">", "quotedbl": '"',
    "degree": "\u00b0", "multiply": "\u00d7", "divide": "\u00f7", "plusminus": "\u00b1",
}


def _glyph_name_to_text(nm: str) -> str:
    if nm in _GLYPH_NAMES:
        return _GLYPH_NAMES[nm]
    if nm.startswith("uni") and len(nm) >= 7:
        try:
            return chr(int(nm[3:7], 16))
        except ValueError:
            return ""
    if nm.startswith("u") and len(nm) >= 5:
        try:
            return chr(int(nm[1:5], 16))
        except ValueError:
            return ""
    if len(nm) == 1:
        return nm
    return ""


# --------------------------------------------------------------------------
# 6. 内容流 -> 文本
# --------------------------------------------------------------------------

TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}


class TextExtractor:
    def __init__(self, doc: PDFDocument):
        self.doc = doc
        self.tj_offset = 0.0

    # ---------- 内容流分词 ----------
    def _run_content(self, data: bytes, out: list, resources: dict, depth: int = 0) -> None:
        """解析内容流，把文本片段按行写入 out。"""
        if not data or depth > 8:
            return
        lx = Lexer(data)
        stack: list = []
        fonts: dict = {}
        font = FontInfo("default")
        leading = 0.0
        font_size = 10.0
        char_space = 0.0
        word_space = 0.0
        h_scale = 1.0
        # 文本矩阵 / 行矩阵
        tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        tlm = list(tm)
        cur_line: list[str] = []
        cur_y = None
        last_x = None
        last_end_x = None

        def flush_line(force: bool = False):
            nonlocal cur_line, last_end_x
            text = "".join(cur_line).rstrip()
            if text:
                out.append(("line", text))
            cur_line = []
            last_end_x = None

        while lx.pos < lx.n:
            save = lx.pos
            obj = lx.parse_object()
            if obj is None:
                if lx.pos == save:
                    lx.pos += 1
                continue

            if isinstance(obj, (Name, bytes)) or isinstance(obj, (int, float, list, dict)):
                stack.append(obj)
                continue

            op = obj if isinstance(obj, str) else ""
            if op not in (
                "BT", "ET", "Tf", "Td", "TD", "Tm", "T*", "TL", "Tc", "Tw", "Tz", "Ts",
                "Tj", "TJ", "'", '"', "Do", "Tr", "q", "Q", "cm", "gs", "BI", "EI",
            ):
                stack = []
                continue

            try:
                if op == "BT":
                    tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
                    tlm = list(tm)
                    cur_y = None
                elif op == "ET":
                    flush_line()
                elif op == "Tf" and len(stack) >= 2:
                    fname = str(stack[-2])
                    font_size = abs(to_float(stack[-1], 10.0)) or 10.0
                    if fname not in fonts:
                        fd = resources.get("Font") if isinstance(resources, dict) else None
                        fd = self.doc.resolve(fd)
                        target = None
                        if isinstance(fd, dict):
                            target = self.doc.resolve(fd.get(fname))
                        fonts[fname] = (load_font(self.doc, target, fname)
                                        if isinstance(target, dict) else FontInfo(fname))
                    font = fonts[fname]
                elif op == "TL" and stack:
                    leading = to_float(stack[-1])
                elif op == "Tc" and stack:
                    char_space = to_float(stack[-1])
                elif op == "Tw" and stack:
                    word_space = to_float(stack[-1])
                elif op == "Tz" and stack:
                    h_scale = to_float(stack[-1], 100.0) / 100.0
                elif op in ("Td", "TD") and len(stack) >= 2:
                    tx, ty = to_float(stack[-2]), to_float(stack[-1])
                    if op == "TD":
                        leading = -ty
                    tlm = _mat_mul([1, 0, 0, 1, tx, ty], tlm)
                    tm = list(tlm)
                elif op == "Tm" and len(stack) >= 6:
                    tlm = [to_float(v) for v in stack[-6:]]
                    tm = list(tlm)
                elif op == "T*":
                    tlm = _mat_mul([1, 0, 0, 1, 0, -leading], tlm)
                    tm = list(tlm)
                elif op in ("Tj", "TJ", "'", '"'):
                    if op in ("'", '"'):
                        tlm = _mat_mul([1, 0, 0, 1, 0, -leading], tlm)
                        tm = list(tlm)
                        if op == '"' and len(stack) >= 1:
                            pass
                    strargs = [a for a in stack if isinstance(a, bytes)]
                    arr = None
                    for a in reversed(stack):
                        if isinstance(a, list):
                            arr = a
                            break
                    segments: list[str] = []
                    if op == "TJ" and arr is not None:
                        for el in arr:
                            if isinstance(el, bytes):
                                segments.append(font.decode(el))
                            elif isinstance(el, (int, float)):
                                v = float(el)
                                if v < -180:       # 大负位移 ≈ 空格
                                    segments.append(" ")
                                elif v < -60:
                                    segments.append(" ")
                    elif strargs:
                        segments.append(font.decode(strargs[-1]))
                    text = "".join(segments)
                    y = tm[5]
                    x = tm[4]
                    if text.strip():
                        if cur_y is None:
                            cur_y = y
                        elif abs(y - cur_y) > max(1.0, font_size * 0.3):
                            flush_line()
                            cur_y = y
                        elif (last_end_x is not None and x - last_end_x > font_size * 0.24
                              and cur_line and not cur_line[-1].endswith(" ")
                              and not text.startswith(" ")):
                            cur_line.append(" ")
                        cur_line.append(text)
                        # 估算本次文本末端 x（粗略，足够判断空格）
                        approx_w = sum(
                            (font_size * (1.0 if ord(ch) < 0x2E80 else 1.0))
                            for ch in text
                        )
                        last_end_x = x + approx_w * h_scale * 0.5
                        tm = _mat_mul([1, 0, 0, 1, approx_w * h_scale * 0.5, 0], tm)
                elif op == "Do" and stack and depth < 8:
                    xname = str(stack[-1])
                    xo = self.doc.resolve((resources or {}).get("XObject"))
                    if isinstance(xo, dict):
                        target = self.doc.resolve(xo.get(xname))
                        if isinstance(target, Stream):
                            if str(target.dict.get("Subtype", "")) == "Form":
                                flush_line()
                                sub_res = self.doc.resolve(target.dict.get("Resources")) or resources
                                self._run_content(target.get_data(), out, sub_res, depth + 1)
                elif op == "EI":
                    # 跳过内联图片数据（BI ... EI）
                    pass
            except Exception:
                pass
            stack = []

        flush_line()

    # ---------- 页面 ----------
    def extract_page(self, page: dict) -> list[str]:
        contents = self.doc.resolve(page.get("Contents"))
        raw_streams: list[bytes] = []
        if isinstance(contents, Stream):
            raw_streams.append(contents.get_data())
        elif isinstance(contents, list):
            for c in contents:
                cc = self.doc.resolve(c)
                if isinstance(cc, Stream):
                    raw_streams.append(cc.get_data())
        resources = self.doc.resolve(page.get("Resources")) or {}
        out: list[tuple[str, str]] = []
        for raw in raw_streams:
            self._run_content(raw, out, resources)
        lines = [t for kind, t in out if kind == "line"]
        return _merge_lines(lines)


def _mat_mul(a: list, b: list) -> list:
    """3x2 矩阵相乘 a × b。"""
    return [
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    ]


_PAREN_ONLY = re.compile(r"^[\(\)\[\]【】\s]*$")


def _merge_lines(lines: list[str]) -> list[str]:
    """合并被 PDF 硬切开的行：下一行不是新条目开头时续接。"""
    merged: list[str] = []
    for line in lines:
        line = re.sub(r"[ \t\u00a0]+", " ", line).strip()
        if not line or _PAREN_ONLY.match(line):
            continue
        if merged:
            prev = merged[-1]
            # 续行判定：上一行没有以句读/答案/选项结束，且当前行不以编号或选项字母开头
            starts_new = re.match(
                r"^(\d{1,3}\s*[、.．)）]|[（(]\s*\d{1,3}\s*[)）]|[A-Ha-h]\s*[、.．)）]"
                r"|[一二三四五六七八九十]+\s*[、.．]|第[一二三四五六七八九十\d]+[章节讲部分]"
                r"|[【（(]?\s*(答案|解析|参考答案|判断题|单选题|多选题|填空题|简答题|名词解释))",
                line,
            )
            ends_clean = re.search(r"[。！？；：\)）】”\"'\.]$", prev) or re.search(
                r"(答案|解析)[：:]\s*\S+$", prev)
            short_prev = len(prev) < 45
            if not starts_new and (short_prev or not ends_clean):
                merged[-1] = prev + line
                continue
        merged.append(line)
    return merged


# --------------------------------------------------------------------------
# 7. 主流程
# --------------------------------------------------------------------------

def extract_pdf(path: Path, verbose: bool = False) -> str:
    doc = PDFDocument(path, verbose=verbose)
    pages = doc.get_pages()
    if verbose:
        print(f"  [pdf] 页面 {len(pages)} 页", file=sys.stderr)
    ex = TextExtractor(doc)
    chunks: list[str] = []
    for i, page in enumerate(pages, 1):
        chunks.append(f"=== PAGE {i} ===")
        try:
            lines = ex.extract_page(page)
        except Exception as e:  # 单页失败不影响整体
            lines = [f"[页面 {i} 解析失败: {e}]"]
        chunks.extend(lines)
        chunks.append("")
    return "\n".join(chunks)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    verbose = "--verbose" in argv or "-v" in argv
    if len(args) < 2:
        print(__doc__)
        return 2
    src, dst = Path(args[0]), Path(args[1])
    if not src.exists():
        print(f"文件不存在: {src}", file=sys.stderr)
        return 1
    text = extract_pdf(src, verbose=verbose)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    nonempty = sum(1 for ln in text.splitlines() if ln.strip())
    print(f"{src.name} -> {dst}")
    print(f"  字符 {len(text)}，其中中文 {cjk}，非空行 {nonempty}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
