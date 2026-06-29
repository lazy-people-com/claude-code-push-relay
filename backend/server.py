"""
push-relay Server (内网 HTTP 版，nginx 反代对外提供 HTTPS)
- /              : 前端入口（client.html）
- /<静态文件>    : frontend/ 下的静态资源
- /api/ws        : WebSocket 端点，需 token
- /api/notify    : HTTPS POST 推送端点，需 token
- /api/health    : 健康检查

监听 PORT（默认 8080），不对外暴露，由 nginx 反向代理。
Token: 环境变量 PUSH_TOKEN 或 ./token 文件
前端目录: ../frontend（相对 backend/）
"""
import asyncio
import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path

from aiohttp import web

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))

# API 路径
WS_PATH = "/api/ws"
NOTIFY_PATH = "/api/notify"
HEALTH_PATH = "/api/health"

# 路径
BACKEND_DIR = Path(__file__).parent
TOKEN_FILE = BACKEND_DIR / "token"
FRONTEND_DIR = Path(
    os.environ.get("FRONTEND_DIR", str(BACKEND_DIR.parent / "frontend"))
)

# 当前所有连上的 WebSocket 接收端
clients: set[web.WebSocketResponse] = set()


def log(msg: str) -> None:
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] {msg}",
        file=sys.stderr,
        flush=True,
    )


def load_or_create_token() -> str:
    """从环境变量、token 文件或自动生成中获取 token"""
    env_token = os.environ.get("PUSH_TOKEN")
    if env_token:
        log("Token 从环境变量 PUSH_TOKEN 读取")
        return env_token

    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            log(f"Token 从 {TOKEN_FILE} 读取")
            return token

    # 自动生成
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    log(f"自动生成 Token 并写入 {TOKEN_FILE}")
    return token


TOKEN: str = ""  # 启动时填充


def extract_token(request: web.Request) -> str:
    """从请求中提取 token：优先 query 参数，其次 Authorization Bearer"""
    token = request.query.get("token", "").strip()
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return ""


def check_token(request: web.Request) -> bool:
    return secrets.compare_digest(extract_token(request), TOKEN)


# ─── API 处理器 ──────────────────────────────────────


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    if not check_token(request):
        log(f"WS 鉴权失败: {request.remote}")
        return web.Response(status=401, text="Unauthorized")

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    log(f"接收端连接: {request.remote}，当前共 {len(clients)} 个")
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                log(f"接收端发来: {msg.data}")
    except Exception as e:
        log(f"WebSocket 异常: {e}")
    finally:
        clients.discard(ws)
        log(f"接收端断开，剩余 {len(clients)} 个")
    return ws


async def notify_handler(request: web.Request) -> web.Response:
    if not check_token(request):
        log(f"Notify 鉴权失败: {request.remote}")
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        data = await request.json()
    except Exception:
        body = await request.text()
        data = {"content": body}

    payload = json.dumps(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "source": data.get("source", "claude-code"),
            "type": data.get("type", "notification"),
            "content": data.get("content", ""),
        },
        ensure_ascii=False,
    )
    log(f"推送: {payload}")

    if not clients:
        return web.json_response(
            {"ok": False, "error": "没有连接的接收端"}, status=404
        )

    targets = list(clients)
    results = await asyncio.gather(
        *[c.send_str(payload) for c in targets], return_exceptions=True
    )
    sent = sum(1 for r in results if not isinstance(r, Exception))
    return web.json_response({"ok": True, "sent_to": sent, "total": len(targets)})


async def health_handler(request: web.Request) -> web.Response:
    # 通过 X-Forwarded-* 头拿真实客户端 IP
    real_ip = request.headers.get("X-Forwarded-For", request.remote)
    proto = request.headers.get("X-Forwarded-Proto", "http")
    return web.json_response(
        {
            "ok": True,
            "clients": len(clients),
            "proto": proto,
            "client": real_ip,
            "time": datetime.now().isoformat(),
        }
    )


# ─── 前端静态文件 ─────────────────────────────────────


async def index_handler(request: web.Request) -> web.Response:
    """根路径返回前端页面"""
    index_path = FRONTEND_DIR / "client.html"
    if not index_path.exists():
        return web.Response(
            status=404,
            text=f"Frontend not found at {index_path}",
        )
    resp = web.FileResponse(index_path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


async def static_handler(request: web.Request) -> web.Response:
    """前端静态文件：/{filename}，仅允许白名单扩展名"""
    filename = request.match_info["filename"]
    # 防止路径穿越
    if "/" in filename or ".." in filename:
        return web.Response(status=403, text="Forbidden")
    file_path = (FRONTEND_DIR / filename).resolve()
    if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
        return web.Response(status=403, text="Forbidden")
    if not file_path.is_file():
        return web.Response(status=404, text=f"Not Found: {filename}")
    resp = web.FileResponse(file_path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ─── 启动 ─────────────────────────────────────────────


async def main() -> None:
    global TOKEN
    TOKEN = load_or_create_token()

    app = web.Application()

    # 静态文件
    app.router.add_get("/", index_handler)
    app.router.add_get("/{filename:.+}", static_handler)

    # API
    app.router.add_get(WS_PATH, websocket_handler)
    app.router.add_post(NOTIFY_PATH, notify_handler)
    app.router.add_get(HEALTH_PATH, health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    log(f"Server 已启动，监听 {HOST}:{PORT}（内部 HTTP，nginx 反代对外）")
    log(f"  前端入口:      http://{HOST}:{PORT}/")
    log(f"  WebSocket:     ws://{HOST}:{PORT}{WS_PATH}?token=***")
    log(f"  推送端点:      POST http://{HOST}:{PORT}{NOTIFY_PATH}?token=***")
    log(f"  健康检查:      GET  http://{HOST}:{PORT}{HEALTH_PATH}")
    log(f"  前端目录:      {FRONTEND_DIR}")
    log("")
    log(f"  Token: {TOKEN}")
    log("")

    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Server 停止")