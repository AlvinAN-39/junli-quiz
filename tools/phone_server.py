#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
phone_server.py — 一键把刷题 App 通过 Wi-Fi 提供给 iPhone 使用
==============================================================

为什么需要它：**iOS Safari 无法运行本地 .html 文件**。
在 iPhone 上「文件」App 只能预览 HTML，微信/QQ 内置浏览器同样不执行本地页面，
所以 `军理刷题.html` 直接发到手机是打不开的。iPhone 只能通过 **HTTP** 访问网页。

本脚本做的事：
  1. 自动探测本机局域网 IPv4 地址（优先 192.168.x / 10.x / 172.16-31.x）；
  2. 在 0.0.0.0 上起一个只读静态服务器，根目录 = `dist/web`；
  3. 打印访问地址 + 一个大号二维码（用 `qr_svg.py` 生成，手机相机直接扫）；
  4. 打印 iPhone 端「添加到主屏幕」的步骤。

用法：
    python tools/phone_server.py            # 默认端口 8765
    python tools/phone_server.py 9000       # 指定端口

安全说明：只在本机局域网内监听、只提供 `dist/web` 目录的静态文件，不做任何写操作。
按 Ctrl+C 停止。
"""

from __future__ import annotations

import http.server
import socket
import socketserver
import sys
import threading
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "dist" / "web"

sys.path.insert(0, str(ROOT / "tools"))
from qr_svg import render_terminal  # noqa: E402


def lan_ip() -> str:
    """探测本机在局域网中的 IPv4 地址。"""
    candidates: list[str] = []
    # 方法 1：连一个外部地址但不真发数据，内核会挑出出口网卡
    for probe in ("8.8.8.8", "1.1.1.1", "223.5.5.5"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.4)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                candidates.append(ip)
                break
        except OSError:
            continue
    # 方法 2：解析主机名
    if not candidates:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith("127."):
                    candidates.append(ip)
        except OSError:
            pass

    def score(ip: str) -> int:
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            try:
                if 16 <= int(ip.split(".")[1]) <= 31:
                    return 2
            except (ValueError, IndexError):
                pass
            return 9
        if ip.startswith("169.254."):
            return 90
        return 5

    if not candidates:
        return "127.0.0.1"
    candidates.sort(key=score)
    return candidates[0]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def end_headers(self):
        # 让 iPhone 每次拿到的是最新版（避免抓旧缓存）
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        # 只打印关键信息，避免刷屏
        try:
            msg = fmt % args
        except Exception:
            msg = str(fmt)
        if " 200 " in msg or " 304 " in msg:
            return
        print("  [http]", msg)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    if not WEB.exists():
        print(f"找不到 {WEB}\n请先运行：python tools\\bundle.py")
        return 1

    port = 8765
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"端口参数无效：{sys.argv[1]}")
            return 1

    ip = lan_ip()
    url = f"http://{ip}:{port}/"

    try:
        httpd = Server(("0.0.0.0", port), Handler)
    except OSError as e:
        print(f"端口 {port} 被占用或无法监听：{e}")
        print(f"换一个端口试试：python tools\\phone_server.py {port + 1}")
        return 1

    print()
    print("=" * 66)
    print("  军理刷题 · iPhone 访问服务已启动")
    print("=" * 66)
    print(f"  静态根目录: {WEB}")
    print(f"  访问地址  : {url}")
    print()
    print("  【iPhone 操作步骤】")
    print("   1. 确认 iPhone 和这台电脑连的是**同一个 Wi-Fi**；")
    print("   2. 用 iPhone 相机扫下面的二维码（或手动在 Safari 里输入上面的地址）；")
    print("   3. 页面打开后，点底部「分享」按钮 → 「添加到主屏幕」；")
    print("   4. 桌面出现「军理刷题」图标，点开即用，**之后断网也能用**。")
    print()
    print("  【停止服务】在窗口里按 Ctrl+C")
    print("=" * 66)
    print()
    try:
        print(render_terminal(url))
    except Exception as e:
        print(f"（二维码生成失败：{e}，请手动输入地址 {url}）")
    print()
    print(f"  地址： {url}")
    print()

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        while t.is_alive():
            t.join(0.5)
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        httpd.shutdown()
        httpd.server_close()
    print("已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
