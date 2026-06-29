# push-relay

通过长连接（WSS，TLS 加密 + Token 认证）把 Claude Code 的事件实时推送到本地终端/浏览器。

## 架构

```
┌─────────────────────┐   HTTPS POST /notify    ┌────────────────────┐
│  Claude Code (hook) │ ───────────────────────▶│                    │
└─────────────────────┘                          │  ycj  (后端)       │
                                                │  push-relay-server │
┌─────────────────────┐   WSS (TLS + Token)     │  WSS 监听 443      │
│  本机终端 (client)  │ ◀───────────────────────│                    │
│  本机浏览器 (网页)  │                          └────────────────────┘
└─────────────────────┘
```

## 目录结构

```
push-relay/
├── backend/                    # 后端（部署到 ycj）
│   ├── server.py               # aiohttp WebSocket relay
│   ├── requirements.txt        # Python 依赖
│   ├── ecosystem.config.cjs    # pm2 配置
│   ├── cert.pem                # 自签证书（含 SAN IP）
│   ├── key.pem                 # 证书私钥
│   ├── token                   # 认证 token（自动生成）
│   └── logs/                   # pm2 日志
├── frontend/                   # 前端（跑在本机）
│   ├── client.html             # 网页版（含浏览器通知）
│   ├── client.py               # 终端版
│   ├── serve.js                # Node 静态服务（pm2 跑）
│   ├── ecosystem.config.cjs    # pm2 配置
│   ├── ycj-cert.pem            # ycj 证书副本（已装到本机钥匙串）
│   └── logs/                   # pm2 日志
└── docs/                       # 文档
    ├── README.md               # 详细文档（部署/配置/systemd）
    └── USAGE.md                # 速查（3 步使用）
```

## 部署状态

| 组件 | 位置 | 端口 | 进程管理 |
|------|------|------|---------|
| 后端 server | `ycj:/root/push-relay/backend/` | 443 (WSS/HTTPS) | pm2 (push-relay-backend) |
| 前端 serve | 本机 `frontend/` | 8080 (HTTP) | pm2 (push-relay-frontend) |
| 网页入口 | 本机浏览器 | - | - |

## 快速使用

```bash
# 1. 看后端是否活着
ssh ycj 'pm2 status'

# 2. 看前端是否活着
pm2 status

# 3. 浏览器打开
open http://localhost:8080

# 4. 或终端版
python3 ~/Desktop/push-relay/frontend/client.py
```

详细文档看 `docs/USAGE.md`（速查）和 `docs/README.md`（完整）。

## pm2 常用命令

```bash
# 后端
ssh ycj 'pm2 status && pm2 logs push-relay-backend --nostream'
ssh ycj 'pm2 restart push-relay-backend'
ssh ycj 'pm2 reload ecosystem.config.cjs'   # 改完代码后

# 前端
pm2 status
pm2 logs push-relay-frontend --nostream
pm2 restart push-relay-frontend

# 持久化（开机自启，root 跑）
ssh ycj 'pm2 save && pm2 startup'    # 跟着提示跑最后那条 sudo 命令
pm2 save && pm2 startup               # 本机
```

## 修改后重启

改了 `backend/server.py`：
```bash
rsync -avz ~/Desktop/push-relay/backend/server.py ycj:/root/push-relay/backend/
ssh ycj 'pm2 restart push-relay-backend'
```

改了 `frontend/serve.js` 或 `frontend/client.html`：
```bash
pm2 restart push-relay-frontend
```