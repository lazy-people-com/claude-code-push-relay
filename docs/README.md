# push-relay

通过长连接（WSS，TLS 加密 + Token 认证）把 Claude Code 的事件实时推送到其他终端 / 设备。

## 架构

```
[Claude Code / 任意来源]
    │  HTTPS POST /notify?token=***
    ▼
[Server @ ycj:443 (TLS)] ──WSS 广播──▶ [Client 接收端]
                                          ├─ Client A
                                          └─ Client B
```

- **Server**：监听 443（WSS/HTTPS），自签证书，token 认证；广播给所有已连接 client
- **Client**：任意多个，WSS 连接 server
- **触发方**：能发 HTTPS POST 的进程（curl、Claude Code hook 等）

## 部署

### 1. 在 ycj 上安装并启动 server

```bash
ssh ycj
mkdir -p /opt/push-relay && cd /opt/push-relay
python3 -m pip install aiohttp
# 生成自签证书（365 天）
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout key.pem -out cert.pem \
  -subj "/CN=push-relay"
# 启动（监听 443 需要 root，server 默认用 root 跑）
nohup python3 /opt/push-relay/server.py > server.log 2>&1 &
```

首次启动会自动生成 token 并写入 `/opt/push-relay/token` 文件，日志里也会打印。

### 2. 把 token 同步到本机

```bash
ssh ycj 'cat /opt/push-relay/token'   # 记下这个 token
```

写到本机 shell rc：

```bash
echo 'export PUSH_TOKEN="<上面那个 token>"' >> ~/.zshrc
source ~/.zshrc
```

### 3. 启动 client

```bash
python3 ~/Desktop/push-relay/client.py
```

可以多开几个，全部接收。Ctrl+C 退出。

### 4. 触发推送

```bash
curl -k -X POST "https://47.120.30.150:443/notify?token=$PUSH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"任务完成","type":"task-done"}'
```

`-k` 跳过自签证书校验。

## 与 Claude Code 集成

`~/.claude/settings.json` 的 hook 命令（参考已合并的版本）：

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "curl -k -s -X POST 'https://47.120.30.150:443/notify?token=YOUR_TOKEN' -H 'Content-Type: application/json' -d '{\"content\":\"工具调用\",\"type\":\"tool-use\",\"source\":\"claude-code\"}'"
      }]
    }],
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "curl -k -s -X POST 'https://47.120.30.150:443/notify?token=YOUR_TOKEN' -H 'Content-Type: application/json' -d '{\"content\":\"Claude Code 已停止\",\"type\":\"stop\",\"source\":\"claude-code\"}'"
      }]
    }],
    "Notification": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "curl -k -s -X POST 'https://47.120.30.150:443/notify?token=YOUR_TOKEN' -H 'Content-Type: application/json' -d '{\"content\":\"Claude Code 通知\",\"type\":\"notification\",\"source\":\"claude-code\"}'"
      }]
    }]
  }
}
```

记得把 `YOUR_TOKEN` 替换成 server 端实际生成的 token。

## 配置项（环境变量）

**Server**:
- `PORT` 默认 `443`
- `SSL_CERT` 默认 `./cert.pem`
- `SSL_KEY` 默认 `./key.pem`
- `PUSH_TOKEN` 默认从 `./token` 文件读，未设则自动生成

**Client**:
- `WS_URI` 默认 `wss://47.120.30.150:443/ws`
- `PUSH_TOKEN` 必填（从 server 同步过来）

## 消息格式

**Server 接收**（POST /api/notify）：
```json
{
  "source":      "claude-code",
  "type":        "tool-use" | "stop" | "notification",
  "content":     "...",
  "host":        "my-mac.local",       // 来源主机
  "tool":        "Bash",               // 工具名
  "tool_input":  "ls -la",             // 工具入参（≤200 字符）
  "task":        "重构 token 系统",     // 详细任务
  "stop_reason": "completed"           // completed | error | interrupted
}
```

**Server 推送**（WebSocket，自动加 timestamp）：
```json
{
  "timestamp":   "2026-06-29T18:30:15+08:00",  // ISO 8601 带时区
  "source":      "claude-code",
  "type":        "tool-use",
  "content":     "工具调用: Bash",
  "host":        "my-mac.local",
  "tool":        "Bash",
  "tool_input":  "ls -la",
  "task":        "",
  "stop_reason": ""
}
```

## Token 系统

### 角色
- **master** — 全局唯一,管理 token(创建/吊销/轮换)、访问 /admin 页面
- **user** — 多个,可推送通知、可作为 WebSocket 接收端

### 存储
- 文件：`backend/tokens.json`（chmod 600，原子写入）
- 摘要算法：**Argon2id**（`argon2-cffi`，默认参数 m=65536, t=3, p=4）
- 明文**永不落盘** — 创建时只在响应里返回一次

### Token 格式
`pr_<role>_<24 字节 url-safe base64>`，例如：
- `pr_master_cDhyxsA2IYFHL3GcKK6tzlvxBsC0yVYG`
- `pr_user_a8f3b2c1d4e5f6g7h8j9k0l1m2n3p4q5r6s7t8`

### 管理 API（均需 master token）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tokens` | 列出所有 token（无明文/无摘要） |
| POST | `/api/tokens` | 创建 token，响应里**唯一一次**返回明文 |
| GET | `/api/tokens/{id}` | 单条详情 |
| DELETE | `/api/tokens/{id}` | 吊销（最后 1 个 master 不可吊销 → 409） |
| POST | `/api/tokens/{id}/rotate` | 轮换，响应里返回新明文 |

所有 admin 端点经 nginx `limit_req` 限流（5 r/s, burst 10）。

### 兼容性
- 老 `backend/token` 单文件首次启动时自动迁移为 `user` role
- `PUSH_TOKEN` 环境变量作为 `user` 注入（不落盘，重启仍有效）

## WebSocket 心跳

- server 端：`WebSocketResponse(heartbeat=30.0)` — 每 30s 自动发 ping
- browser 端：自动重连（指数退避 1s → 30s 上限）+ `visibilitychange` 处理
- Python 端：`ping_interval=20, ping_timeout=20`

这样保证 Cloudflare 100s 空闲超时永远不触发。

## 持久化运行（systemd）

`/etc/systemd/system/push-relay.service`：

```ini
[Unit]
Description=push-relay WebSocket relay
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/push-relay
ExecStart=/usr/bin/python3 /opt/push-relay/server.py
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now push-relay
```

## 防火墙

ycj 是阿里云，安全组要放行入站 443。Rocky 本机防火墙：

```bash
firewall-cmd --permanent --add-service=https
firewall-cmd --reload
```
