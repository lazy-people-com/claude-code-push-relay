"""
push-relay Client (WSS + Token 版)
连上 server 的 WSS 端点,实时打印收到的通知。
支持新字段: host / tool / tool_input / task / stop_reason
时间显示为本地时区(ISO 字符串带时区偏移 → astimezone 转换)。
"""
import asyncio
import json
import os
import ssl
import sys
from datetime import datetime

import websockets

# 默认连 ycj 服务器的 WSS,可通过环境变量覆盖
URI = os.environ.get("WS_URI", "wss://yangchenjie.com/api/ws")
TOKEN = os.environ.get("PUSH_TOKEN", "")

# 自签证书需要跳过验证
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# WSS 关闭码 → 用户可读中文提示(与 frontend/_common.js 保持一致;
# 4xxx 段是 IANA 留给应用层,server 端定义见 backend/server.py WS_CLOSE_*)
WS_CLOSE_REASONS = {
    1000: "正常关闭",
    1006: "连接异常(证书未信任?服务器不可达?)",
    1008: "连接策略违规",
    4400: "服务器内部错误",
    4401: "未授权(缺少或无效的 Token)",
    4403: "权限不足(非 master)",
}


def describe_close(code: int | None, reason: str | None = "") -> str:
    if code == 1006:
        return WS_CLOSE_REASONS[1006]
    if code in WS_CLOSE_REASONS:
        return WS_CLOSE_REASONS[code]
    if code and code >= 4000:
        return f"服务器拒绝 (HTTP {code})"
    return (reason or f"已断开 [code={code}]").strip()


def build_url() -> str:
    """构造带 token 的连接 URL"""
    sep = "&" if "?" in URI else "?"
    return f"{URI}{sep}token={TOKEN}" if TOKEN else URI


def fmt_local(ts: str) -> str:
    """将 server 端的 ISO 时间(带时区)转为本地时区可读字符串"""
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    except Exception:
        return ts


async def main() -> None:
    url = build_url()
    print(f"连接 {url} ...", flush=True)
    ssl_arg = SSL_CTX if url.startswith("wss://") else None
    # 显式声明心跳参数(websockets>=12 默认就有,显式更稳)
    async with websockets.connect(
        url,
        ssl=ssl_arg,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
    ) as ws:
        print("✓ 已连接,等待通知 ...(Ctrl+C 退出)\n", flush=True)
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {"content": raw}

                ts = fmt_local(data.get("timestamp", ""))
                src = data.get("source", "")
                typ = data.get("type", "notification")
                content = data.get("content", "")
                host = data.get("host", "")
                tool = data.get("tool", "")
                tool_in = data.get("tool_input", "")
                task = data.get("task", "")
                stop = data.get("stop_reason", "")

                # 拼接徽章: 主机 / 工具 / 停止原因(各自独立维度)
                badges = []
                if host: badges.append(f"🖥{host}")
                if tool: badges.append(f"🔧{tool}")
                if stop: badges.append(f"⟶{stop}")
                badge_str = f" [{' '.join(badges)}]" if badges else ""

                print(f"🔔 [{ts}] [{src}/{typ}]{badge_str} {content}", flush=True)

                # 详细任务 / 工具入参 各占一行
                if tool_in:
                    print(f"   ⚙️  {tool_in}", flush=True)
                if task and task != content:
                    print(f"   📋 {task}", flush=True)
        except websockets.ConnectionClosed as e:
            print(f"\n✗ 连接关闭: {describe_close(e.code, e.reason)}", flush=True)
        except websockets.ConnectionClosedError as e:
            # 协议层异常断开(收尾时 rcvd=1006 等)
            print(f"\n✗ 连接异常: {describe_close(e.code, e.reason)}", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已断开")
        sys.exit(0)
