#!/usr/bin/env bash
# pull-and-deploy.sh — ycj 一键拉最新代码并部署
#
# 适用: ycj (/root/push-relay) 已 git init + remote add origin
# 用法: ssh ycj 'cd /root/push-relay && bin/pull-and-deploy.sh'
#
# 做的事:
#   1. git pull origin dev (拉最新代码)
#   2. sync 前端静态文件到 nginx serve 目录 (/var/www/push-relay/)
#   3. pm2 restart push-relay-backend (后端)
#
# 安全: deploy key 是只读的(用户在 github 仓库设置时勾了 read-only),
#      这里也只 pull,不会推送。

set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/push-relay}"
WEB_DIR="${WEB_DIR:-/var/www/push-relay}"
BACKEND_DIR="$REPO_DIR/backend"
FRONTEND_DIR="$REPO_DIR/frontend"
BRANCH="${BRANCH:-dev}"

cd "$REPO_DIR"

# 1. 拉最新
echo "── git pull origin $BRANCH ──"
git pull --ff-only origin "$BRANCH"

# 2. 同步前端到 nginx serve 目录
#    只同步 client.html / admin.html / _common.css / _common.js,
#    notify.sh / client.py 留在 $REPO_DIR/frontend/ 即可(本机客户端用)
echo "── sync frontend → $WEB_DIR ──"
mkdir -p "$WEB_DIR"
for f in client.html admin.html _common.css _common.js; do
  if [[ -f "$FRONTEND_DIR/$f" ]]; then
    cp "$FRONTEND_DIR/$f" "$WEB_DIR/$f"
  fi
done

# 3. 重启后端(若 backend/server.py 改了)
#    ecosystem.config.cjs 通常不需要 reload, 直接 restart 即可
echo "── pm2 restart push-relay-backend ──"
pm2 restart push-relay-backend

echo ""
echo "✓ 部署完成"
echo "  最近 5 行 server log:"
pm2 logs push-relay-backend --nostream --lines 5 2>&1 | tail -5
