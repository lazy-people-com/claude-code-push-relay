#!/bin/bash
# push-relay 一键部署脚本（nginx + push-relay）
# 在 ycj 上以 root 运行

set -e

# 配置
APP_DIR="${APP_DIR:-/root/push-relay}"
WEB_DIR="${WEB_DIR:-/var/www/push-relay}"
NGINX_CONF_SRC="$APP_DIR/deploy/nginx.conf"
NGINX_CONF_DST="/etc/nginx/conf.d/push-relay.conf"

echo "═══════════════════════════════════════════════════════"
echo "  push-relay 部署"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "应用目录: $APP_DIR"
echo "前端目录: $WEB_DIR"
echo ""

# 1. 装 nginx
echo "── 1. 装 nginx ──"
if ! command -v nginx >/dev/null 2>&1; then
    dnf install -y nginx
    echo "  ✓ nginx 装好"
else
    echo "  ✓ nginx 已装"
fi
echo ""

# 2. 创建前端目录并复制文件
echo "── 2. 部署前端静态文件 ──"
mkdir -p "$WEB_DIR"
cp "$APP_DIR/frontend/client.html" "$WEB_DIR/"
cp "$APP_DIR/frontend/client.py" "$WEB_DIR/" 2>/dev/null || true
cp "$APP_DIR/frontend/ycj-cert.pem" "$WEB_DIR/" 2>/dev/null || true
chmod 644 "$WEB_DIR"/*
echo "  ✓ 前端文件复制到 $WEB_DIR"
ls -la "$WEB_DIR"
echo ""

# 3. 复制 nginx 配置
echo "── 3. 配置 nginx ──"
cp "$NGINX_CONF_SRC" "$NGINX_CONF_DST"
nginx -t
echo ""

# 4. 启动 nginx
echo "── 4. 启动 nginx ──"
systemctl enable nginx
systemctl restart nginx
echo "  ✓ nginx 已启动"
sleep 1
systemctl is-active nginx
echo ""

# 5. 启动 push-relay（监听 8080）
echo "── 5. 重启 push-relay（监听 8080） ──"
export PORT=8080
export HOST=127.0.0.1
pm2 delete push-relay-backend 2>/dev/null || true
cd "$APP_DIR/backend"
pm2 start ecosystem.config.cjs --env production
pm2 save
sleep 2
pm2 status
echo ""

echo "═══════════════════════════════════════════════════════"
echo "  部署完成"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "访问入口："
echo "  浏览器: https://yangchenjie.com/  (经 Cloudflare)"
echo "  健康检查: curl http://127.0.0.1:8080/api/health"
echo ""
echo "端口状态："
echo "  80    → nginx（Cloudflare 入口）"
echo "  8080  → push-relay（仅内网）"
echo "  443   → 空（如果需要直接访问，可启用 nginx 配置里的 HTTPS server 段）"
echo ""
echo "调试命令："
echo "  pm2 logs push-relay-backend    # 后端日志"
echo "  tail -f /var/log/nginx/push-relay.error.log  # nginx 错误日志"
echo "  nginx -t                       # 测试配置"