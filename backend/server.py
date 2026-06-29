"""
push-relay Server (内网 HTTP 版,nginx 反代对外提供 HTTPS)
- /              : 前端入口 (client.html)
- /admin         : Token 管理页 (admin.html)
- /<静态文件>    : frontend/ 下的静态资源
- /api/ws        : WebSocket 端点,需任意有效 token
- /api/notify    : HTTPS POST 推送端点,需任意有效 token
- /api/health    : 健康检查
- /api/tokens    : Token 管理 (需 master token)

监听 PORT(默认 8080),不对外暴露,由 nginx 反向代理。
Token: 持久化到 backend/tokens.json (Argon2id 摘要,不含明文)
环境变量 PUSH_TOKEN 兼容: 启动时作为 user token 注入(仅内存,不落盘)
"""
import asyncio
import json
import os
import secrets
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiohttp import web
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))

# API 路径
WS_PATH = "/api/ws"
NOTIFY_PATH = "/api/notify"
HEALTH_PATH = "/api/health"
TOKENS_PATH = "/api/tokens"

# 路径
BACKEND_DIR = Path(__file__).parent
TOKENS_FILE = BACKEND_DIR / "tokens.json"
LEGACY_TOKEN_FILE = BACKEND_DIR / "token"  # 老版本单 token 文件
MASTER_ONCE_FILE = BACKEND_DIR / ".master-once"  # 首次启动保存 master 明文,用户读完应删
FRONTEND_DIR = Path(
    os.environ.get("FRONTEND_DIR", str(BACKEND_DIR.parent / "frontend"))
)

# 当前所有连上的 WebSocket 接收端
clients: set[web.WebSocketResponse] = set()

# Argon2 hasher(线程安全,verifier 自身无状态)
_HASHER = PasswordHasher()

# Token 存储(启动时填充)
TOKEN_STORE: "TokenStore"  # type: ignore


def log(msg: str) -> None:
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] {msg}",
        file=sys.stderr,
        flush=True,
    )


# ─── Token 存储 ──────────────────────────────────────


class TokenStore:
    """多 token + master 持久化。摘要用 Argon2id,明文永不落盘。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.tokens: list[dict] = []
        self._lock = threading.Lock()  # 保护 self.tokens 在线程间安全

    def load(self) -> None:
        """加载 tokens.json;不存在则从老 backend/token 迁移并生成 master。"""
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.tokens = data.get("tokens", [])
            log(f"从 {self.path} 加载 {len(self.tokens)} 个 token")
        else:
            log(f"{self.path} 不存在,执行首次启动迁移")
            self._first_time_setup()

        # 注入 PUSH_TOKEN 环境变量(兼容老配置;不落盘)
        env_token = os.environ.get("PUSH_TOKEN", "").strip()
        if env_token:
            # 检查是否已经存在等价 token(env 变量可能在重启后还在)
            if not any(t.get("_from_env") for t in self.tokens):
                record, _ = self._create_with_secret(
                    env_token, "env-PUSH_TOKEN", "user"
                )
                record["_from_env"] = True  # 标记不落盘
                self.tokens.append(record)
                log("⚠️  PUSH_TOKEN 环境变量已注入为 user token (in-memory, 不落盘)")
                log("    建议: 访问 /admin 创建一个新的 user token,填到 ~/.zshrc,然后移除 PUSH_TOKEN")
        else:
            if any(t.get("_from_env") for t in self.tokens):
                # 重启后环境变量没了,清掉
                self.tokens = [t for t in self.tokens if not t.get("_from_env")]

    def _first_time_setup(self) -> None:
        """首次启动:迁移老 token + 生成 master。"""
        # 1) 迁移老的 backend/token
        legacy = None
        if LEGACY_TOKEN_FILE.exists():
            legacy = LEGACY_TOKEN_FILE.read_text(encoding="utf-8").strip()
            LEGACY_TOKEN_FILE.rename(LEGACY_TOKEN_FILE.with_suffix(".migrated"))
            log(f"已迁移老 token 文件 → {LEGACY_TOKEN_FILE}.migrated (请手动删除)")

        # 2) 创建 master
        master_record, master_secret = self._generate("bootstrap-master", "master")
        self.tokens = [master_record]

        # 3) 老 token 转为 user
        if legacy:
            user_record, _ = self._create_with_secret(legacy, "legacy-import", "user")
            self.tokens.append(user_record)

        # 4) 落盘
        self.save()

        # 5) 在启动日志中**只一次**打印 master 明文 + 写入一次性文件
        try:
            MASTER_ONCE_FILE.write_text(master_secret + "\n", encoding="utf-8")
            MASTER_ONCE_FILE.chmod(0o600)
        except OSError as e:
            log(f"⚠️  写入 {MASTER_ONCE_FILE} 失败: {e}")
        log("")
        log("╔══════════════════════════════════════════════════════╗")
        log("║  ⚠️  MASTER TOKEN (仅此一次, 请立即保存!)            ║")
        log("╚══════════════════════════════════════════════════════╝")
        log(f"  {master_secret}")
        log("")
        if MASTER_ONCE_FILE.exists():
            log(f"  也已写入: {MASTER_ONCE_FILE} (chmod 600)")
            log(f"  建议: 保存后立即删除该文件,并访问 /admin 创建新 token")
        log("")

    def _make_secret(self, role: str) -> str:
        return f"pr_{role}_{secrets.token_urlsafe(24)}"

    def _generate(self, name: str, role: str) -> tuple[dict, str]:
        return self._create_with_secret(self._make_secret(role), name, role)

    def _create_with_secret(
        self, secret: str, name: str, role: str
    ) -> tuple[dict, str]:
        return {
            "id": "tk_" + secrets.token_hex(4),
            "name": name,
            "role": role,
            "token_hash": _HASHER.hash(secret),
            "prefix": secret[:16],
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "last_used_at": None,
            "revoked": False,
        }, secret

    def verify(self, presented: str) -> Optional[dict]:
        """同步,CPU 密集,应在 to_thread 中调用。"""
        with self._lock:
            tokens_snapshot = list(self.tokens)
        for record in tokens_snapshot:
            if record.get("revoked"):
                continue
            try:
                _HASHER.verify(record["token_hash"], presented)
                return record
            except (VerifyMismatchError, InvalidHashError, VerificationError):
                continue
        return None

    def touch(self, record: dict) -> None:
        """更新 last_used_at(仅内存,不写盘 — 避免高频 IO)。"""
        with self._lock:
            record["last_used_at"] = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )

    def create(self, name: str, role: str) -> tuple[Optional[dict], Optional[str], Optional[str]]:
        """(record, plaintext, error)"""
        if role not in ("user", "master"):
            return None, None, f"role 必须是 user 或 master,收到: {role!r}"
        if role == "master":
            if any(t["role"] == "master" and not t["revoked"] for t in self.tokens):
                return None, None, "master token 已存在,全局只允许 1 个"
        record, secret = self._generate(name or f"{role}-token", role)
        with self._lock:
            self.tokens.append(record)
            self.save()
        return record, secret, None

    def revoke(self, token_id: str) -> Optional[str]:
        """返回 error msg 或 None"""
        with self._lock:
            target = next((t for t in self.tokens if t["id"] == token_id), None)
            if not target:
                return "token 不存在"
            if target["role"] == "master" and not target["revoked"]:
                active_masters = [
                    t for t in self.tokens
                    if t["role"] == "master" and not t["revoked"]
                ]
                if len(active_masters) <= 1:
                    return "不能吊销唯一的 master token"
            target["revoked"] = True
            self.save()
        return None

    def rotate(self, token_id: str) -> tuple[Optional[dict], Optional[str], Optional[str]]:
        """(record, plaintext, error)"""
        with self._lock:
            target = next((t for t in self.tokens if t["id"] == token_id), None)
            if not target:
                return None, None, "token 不存在"
            new_record, new_secret = self._generate(target["name"], target["role"])
            new_record["id"] = target["id"]
            new_record["created_at"] = target["created_at"]
            idx = self.tokens.index(target)
            self.tokens[idx] = new_record
            self.save()
        return new_record, new_secret, None

    def list_public(self) -> list[dict]:
        """列出所有 token(无明文、无摘要)。"""
        with self._lock:
            return [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "role": t["role"],
                    "prefix": t["prefix"],
                    "created_at": t["created_at"],
                    "last_used_at": t.get("last_used_at"),
                    "revoked": t.get("revoked", False),
                }
                for t in self.tokens
                if not t.get("_from_env")  # 不展示 env-var token
            ]

    def get(self, token_id: str) -> Optional[dict]:
        with self._lock:
            target = next((t for t in self.tokens if t["id"] == token_id), None)
            if not target:
                return None
            return {
                "id": target["id"],
                "name": target["name"],
                "role": target["role"],
                "prefix": target["prefix"],
                "created_at": target["created_at"],
                "last_used_at": target.get("last_used_at"),
                "revoked": target.get("revoked", False),
            }

    def save(self) -> None:
        """原子写入(过滤 env 标记)。"""
        data = {
            "version": 2,
            "tokens": [t for t in self.tokens if not t.get("_from_env")],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.chmod(0o600)
        os.replace(tmp, self.path)


# ─── 鉴权 ────────────────────────────────────────────


def extract_token(request: web.Request) -> str:
    """从请求中提取 token:优先 query 参数,其次 Authorization Bearer。"""
    token = request.query.get("token", "").strip()
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return ""


async def check_token_async(
    request: web.Request, required_role: Optional[str] = None
) -> Optional[dict]:
    """异步 token 校验。返回 token record 或 None。"""
    presented = extract_token(request)
    if not presented:
        return None
    record = await asyncio.to_thread(TOKEN_STORE.verify, presented)
    if record is None:
        return None
    if required_role == "master" and record["role"] != "master":
        return None
    TOKEN_STORE.touch(record)
    return record


# ─── API 处理器 ──────────────────────────────────────


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    record = await check_token_async(request)
    if record is None:
        log(f"WS 鉴权失败: {request.remote}")
        return web.Response(status=401, text="Unauthorized")

    # heartbeat=30: 每 30s 自动发 ping,30s 内无 pong 则主动关
    ws = web.WebSocketResponse(heartbeat=30.0, autoclose=True)
    await ws.prepare(request)
    clients.add(ws)
    log(
        f"接收端连接: {request.remote} "
        f"(role={record['role']}, name={record['name']}), "
        f"当前共 {len(clients)} 个"
    )
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                log(f"接收端发来: {msg.data}")
    except Exception as e:
        log(f"WebSocket 异常: {e}")
    finally:
        clients.discard(ws)
        log(
            f"接收端断开 (code={ws.close_code}, reason={ws.reason!r}), "
            f"剩余 {len(clients)} 个"
        )
    return ws


async def notify_handler(request: web.Request) -> web.Response:
    record = await check_token_async(request)
    if record is None:
        log(f"Notify 鉴权失败: {request.remote}")
        return web.json_response(
            {"ok": False, "error": "unauthorized"}, status=401
        )

    try:
        data = await request.json()
    except Exception:
        body = await request.text()
        data = {"content": body}

    # 透传新字段,缺省降级为 ""
    payload = json.dumps(
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": data.get("source", "claude-code"),
            "type": data.get("type", "notification"),
            "content": data.get("content", ""),
            "host": data.get("host", ""),
            "tool": data.get("tool", ""),
            "tool_input": data.get("tool_input", ""),
            "task": data.get("task", ""),
            "stop_reason": data.get("stop_reason", ""),
        },
        ensure_ascii=False,
    )
    log(f"推送 [{record['name']}]: {payload}")

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
    real_ip = request.headers.get("X-Forwarded-For", request.remote)
    proto = request.headers.get("X-Forwarded-Proto", "http")
    return web.json_response(
        {
            "ok": True,
            "clients": len(clients),
            "proto": proto,
            "client": real_ip,
            "time": datetime.now().astimezone().isoformat(),
        }
    )


# ─── Token 管理 API(均需 master token)───────────────


async def tokens_list_handler(request: web.Request) -> web.Response:
    record = request.get("token_record")
    if not record:
        return web.json_response(
            {"ok": False, "error": "需要 master token"}, status=401
        )
    return web.json_response({"ok": True, "tokens": TOKEN_STORE.list_public()})


async def tokens_create_handler(request: web.Request) -> web.Response:
    if not request.get("token_record"):
        return web.json_response(
            {"ok": False, "error": "需要 master token"}, status=401
        )
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "需要 JSON body"}, status=400)
    name = (data.get("name") or "").strip()
    role = (data.get("role") or "user").strip()
    record, secret, err = TOKEN_STORE.create(name, role)
    if err:
        status = 409 if "已存在" in err else 400
        return web.json_response({"ok": False, "error": err}, status=status)
    log(f"[ADMIN] master 创建 token: id={record['id']} name={name!r} role={role}")
    return web.json_response(
        {
            "ok": True,
            "token": {
                "id": record["id"],
                "name": record["name"],
                "role": record["role"],
                "prefix": record["prefix"],
                "created_at": record["created_at"],
            },
            "secret": secret,  # ← 仅此一次响应出现,后端不存明文
        },
        status=201,
    )


async def tokens_get_handler(request: web.Request) -> web.Response:
    if not request.get("token_record"):
        return web.json_response(
            {"ok": False, "error": "需要 master token"}, status=401
        )
    token_id = request.match_info["id"]
    record = TOKEN_STORE.get(token_id)
    if not record:
        return web.json_response({"ok": False, "error": "token 不存在"}, status=404)
    return web.json_response({"ok": True, "token": record})


async def tokens_delete_handler(request: web.Request) -> web.Response:
    if not request.get("token_record"):
        return web.json_response(
            {"ok": False, "error": "需要 master token"}, status=401
        )
    token_id = request.match_info["id"]
    err = TOKEN_STORE.revoke(token_id)
    if err:
        status = 409 if "不能" in err or "已存在" in err else 404
        return web.json_response({"ok": False, "error": err}, status=status)
    log(f"[ADMIN] master 吊销 token: id={token_id}")
    return web.json_response({"ok": True})


async def tokens_rotate_handler(request: web.Request) -> web.Response:
    if not request.get("token_record"):
        return web.json_response(
            {"ok": False, "error": "需要 master token"}, status=401
        )
    token_id = request.match_info["id"]
    record, secret, err = TOKEN_STORE.rotate(token_id)
    if err:
        return web.json_response({"ok": False, "error": err}, status=404)
    log(f"[ADMIN] master 轮换 token: id={token_id}")
    return web.json_response(
        {
            "ok": True,
            "token": {
                "id": record["id"],
                "name": record["name"],
                "role": record["role"],
                "prefix": record["prefix"],
                "created_at": record["created_at"],
            },
            "secret": secret,
        }
    )


# ─── 前端静态文件 ─────────────────────────────────────


async def index_handler(request: web.Request) -> web.Response:
    """根路径返回 client.html"""
    index_path = FRONTEND_DIR / "client.html"
    if not index_path.exists():
        return web.Response(status=404, text=f"Frontend not found at {index_path}")
    resp = web.FileResponse(index_path)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


async def admin_index_handler(request: web.Request) -> web.Response:
    """/admin 返回 admin.html。public 页面(无敏感数据),敏感操作走 API 鉴权。"""
    admin_path = FRONTEND_DIR / "admin.html"
    if not admin_path.exists():
        return web.Response(
            status=404,
            text=f"admin.html not found at {admin_path}",
        )
    resp = web.FileResponse(admin_path)
    # 防止浏览器缓存管理页
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def static_handler(request: web.Request) -> web.Response:
    """前端静态文件:/<filename>,仅允许白名单扩展名。"""
    filename = request.match_info["filename"]
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


# ─── Middleware ───────────────────────────────────────


@web.middleware
async def admin_auth_middleware(request: web.Request, handler):
    """/api/tokens 系列端点需要 master token 鉴权。"""
    if request.path.startswith(TOKENS_PATH):
        record = await check_token_async(request, required_role="master")
        if record is None:
            return web.json_response(
                {"ok": False, "error": "需要 master token"}, status=401
            )
        request["token_record"] = record
    return await handler(request)


# ─── 启动 ─────────────────────────────────────────────


async def main() -> None:
    global TOKEN_STORE
    TOKEN_STORE = TokenStore(TOKENS_FILE)
    TOKEN_STORE.load()

    app = web.Application(middlewares=[admin_auth_middleware])

    # 静态文件(更具体的路由先注册,避免被 catch-all 吞掉)
    app.router.add_get("/", index_handler)
    app.router.add_get("/admin", admin_index_handler)
    app.router.add_get("/{filename:.+}", static_handler)

    # API
    app.router.add_get(WS_PATH, websocket_handler)
    app.router.add_post(NOTIFY_PATH, notify_handler)
    app.router.add_get(HEALTH_PATH, health_handler)

    # Token 管理 API
    app.router.add_get(TOKENS_PATH, tokens_list_handler)
    app.router.add_post(TOKENS_PATH, tokens_create_handler)
    app.router.add_get(f"{TOKENS_PATH}/{{id}}", tokens_get_handler)
    app.router.add_delete(f"{TOKENS_PATH}/{{id}}", tokens_delete_handler)
    app.router.add_post(f"{TOKENS_PATH}/{{id}}/rotate", tokens_rotate_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    log(f"Server 已启动,监听 {HOST}:{PORT}(内部 HTTP,nginx 反代对外)")
    log(f"  前端入口:      http://{HOST}:{PORT}/")
    log(f"  Admin 页面:   http://{HOST}:{PORT}/admin")
    log(f"  WebSocket:     ws://{HOST}:{PORT}{WS_PATH}?token=***")
    log(f"  推送端点:      POST http://{HOST}:{PORT}{NOTIFY_PATH}?token=***")
    log(f"  健康检查:      GET  http://{HOST}:{PORT}{HEALTH_PATH}")
    log(f"  Token 管理:    {TOKENS_PATH}/(需 master)")
    log(f"  前端目录:      {FRONTEND_DIR}")
    log(f"  Token 存储:   {TOKENS_FILE}")
    log("")

    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Server 停止")
