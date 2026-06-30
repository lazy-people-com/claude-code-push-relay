#!/usr/bin/env python3
"""
push-relay GitHub webhook receiver
- Listen 127.0.0.1:9000 (loopback only — 反代由 ycj nginx 负责)
- POST /webhook   HMAC SHA256 校验 (X-Hub-Signature-256)
                  push event 且 branch=refs/heads/dev 时
                  异步 exec bin/pull-and-deploy.sh,立即返 200
- GET  /healthz   存活探针

依赖: aiohttp (项目已有, server.py 用)
配置: bin/.webhook-secret  (gitignore, 含 shared secret)

部署方式: ycj 上用 pm2 跑 (ecosystem.config.cjs 新加一条)
不依赖具体路径,通过环境变量覆盖: WEBHOOK_HOST / WEBHOOK_PORT / REPO_DIR
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

from aiohttp import web

HOST = os.environ.get("WEBHOOK_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
SECRET_FILE = Path(__file__).parent / ".webhook-secret"
REPO_DIR = Path(os.environ.get("REPO_DIR", "/root/push-relay"))
DEPLOY_SCRIPT = REPO_DIR / "bin" / "pull-and-deploy.sh"


def verify_signature(payload_bytes: bytes, signature: str) -> bool:
    """校验 github HMAC SHA256: secret 来自 SECRET_FILE。"""
    try:
        secret = SECRET_FILE.read_text().strip()
    except FileNotFoundError:
        return False
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def handle_webhook(request: web.Request) -> web.Response:
    payload = await request.read()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(payload, sig):
        return web.Response(status=401, text="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return web.json_response({"ok": True, "skipped": f"event={event}"})

    try:
        data = json.loads(payload)
    except Exception:
        return web.Response(status=400, text="invalid json")

    if data.get("ref") != "refs/heads/dev":
        return web.json_response({"ok": True, "skipped": data.get("ref")})

    # Fire-and-forget: deploy 异步跑,这里立即返 200 让 github 不超时
    asyncio.create_task(run_deploy(event_data=data))
    return web.json_response({"ok": True, "deploying": True})


async def run_deploy(event_data: dict) -> None:
    """异步 exec deploy 脚本, 2 分钟超时。"""
    head = event_data.get("after", "")[:7]
    pusher = event_data.get("pusher", {}).get("name", "?")
    print(f"[deploy] start: {pusher} pushed {head} → refs/heads/dev", flush=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            str(DEPLOY_SCRIPT),
            cwd=str(REPO_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        print(f"[deploy] exit={proc.returncode}", flush=True)
        if stdout:
            print(f"[deploy stdout]\n{stdout.decode()}", flush=True)
        if stderr:
            print(f"[deploy stderr]\n{stderr.decode()}", flush=True)
    except asyncio.TimeoutError:
        print("[deploy] TIMEOUT (>120s)", flush=True)
    except Exception as e:
        print(f"[deploy] error: {type(e).__name__}: {e}", flush=True)


async def healthz(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "push-relay-webhook"})


def main() -> None:
    if not SECRET_FILE.exists():
        print(f"ERROR: {SECRET_FILE} not found", file=sys.stderr)
        print(f"生成: openssl rand -hex 32 > {SECRET_FILE} && chmod 600 {SECRET_FILE}",
              file=sys.stderr)
        sys.exit(1)
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/healthz", healthz)
    print(f"[webhook] listening on http://{HOST}:{PORT}", flush=True)
    web.run_app(app, host=HOST, port=PORT, access_log=None)


if __name__ == "__main__":
    main()
