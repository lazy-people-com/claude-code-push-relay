"""
push-relay Client (WSS + Token 版)
连上 server 的 WSS 端点，实时打印收到的通知
"""
import asyncio
import json
import os
import ssl
import sys

import websockets

# 默认连 ycj 服务器的 WSS，可通过环境变量覆盖
URI = os.environ.get("WS_URI", "wss://yangchenjie.com/api/ws")
TOKEN = os.environ.get("PUSH_TOKEN", "")

# 自签证书需要跳过验证
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def build_url() -> str:
    """构造带 token 的连接 URL"""
    sep = "&" if "?" in URI else "?"
    return f"{URI}{sep}token={TOKEN}" if TOKEN else URI


async def main() -> None:
    url = build_url()
    print(f"连接 {url} ...", flush=True)
    # wss:// 用 SSL_CTX 跳过自签证书校验；ws:// 不传 ssl
    ssl_arg = SSL_CTX if url.startswith("wss://") else None
    async with websockets.connect(url, ssl=ssl_arg) as ws:
        print("✓ 已连接，等待通知 ...（Ctrl+C 退出）\n", flush=True)
        async for raw in ws:
            try:
                data = json.loads(raw)
            except Exception:
                data = {"content": raw}

            ts = data.get("timestamp", "")
            src = data.get("source", "")
            typ = data.get("type", "notification")
            content = data.get("content", "")
            print(
                f"🔔 [{ts}] [{src}/{typ}] {content}",
                flush=True,
            )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已断开")
        sys.exit(0)
