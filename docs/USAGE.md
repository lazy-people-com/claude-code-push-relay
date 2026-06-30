# push-relay 使用说明

## 一句话
Claude Code 跑任务时，事件通过 HTTPS 加密推到 ycj 服务器（443），本机客户端实时接收通知。

## 3 步使用

### 1. 启动客户端

```bash
source ~/.zshrc   # 第一次或新终端，让 PUSH_TOKEN 生效
python3 ~/Desktop/push-relay/frontend/client.py
```

终端会显示：
```
连接 wss://yangchenjie.com/api/ws?token=***
✓ 已连接，等待通知 ...
```

留着别关。

### 2. 跑 Claude Code

正常用就行。跑任务时，上面的客户端窗口会实时弹出：

```
🔔 [2026-06-29 18:30:15 +0800] [claude-code/tool-use] [🖥my-mac 🔧Bash] 工具调用: Bash
   ⚙️  {"command":"ls -la"}
🔔 [2026-06-29 18:30:18 +0800] [claude-code/stop] [🖥my-mac ⟶completed] Claude Code 已停止
🔔 [2026-06-29 18:30:25 +0800] [claude-code/notification] [🖥my-mac] 权限确认
   📋 权限确认
```

每条消息字段详细说明见 [docs/FIELDS.md](FIELDS.md) (type / host / tool / tool_input / task / stop_reason / timestamp 等)。

### 3. 手动推消息（可选，调试用）

```bash
curl -k -X POST "https://yangchenjie.com/api/notify?token=$PUSH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content":"自定义消息",
    "type":"tool-use",
    "host":"my-mac",
    "tool":"Bash",
    "tool_input":"ls -la",
    "task":"查看目录",
    "stop_reason":""
  }'
```

`-k` 是因为部分路径用了自签证书。

## 集成到 Claude Code Hook

把 `~/.claude/settings.json` 的 hooks 指向 notify.sh：

```json
{
  "hooks": {
    "PreToolUse":   [{ "matcher": "*", "hooks": [{ "type": "command", "command": "/Users/unkowny/Desktop/push-relay/frontend/notify.sh" }] }],
    "PostToolUse":  [{ "matcher": "*", "hooks": [{ "type": "command", "command": "/Users/unkowny/Desktop/push-relay/frontend/notify.sh" }] }],
    "Stop":         [{ "hooks":         [{ "type": "command", "command": "/Users/unkowny/Desktop/push-relay/frontend/notify.sh" }] }],
    "Notification": [{ "matcher": "*", "hooks": [{ "type": "command", "command": "/Users/unkowny/Desktop/push-relay/frontend/notify.sh" }] }]
  }
}
```

notify.sh 从 stdin 读 Claude Code 传的 JSON，自动提取 `hook_event_name` / `tool_name` / `tool_input` / `message` / `stop_hook_active` 等字段，并加上本机 `hostname`，组装成 push-relay payload 推给 server。

所需依赖：`bash`, `jq`, `curl`（macOS 默认可用；Linux 用包管理器装 `jq`）。

## 管理 Token

**首次部署后**：
1. 查看 server 启动日志里的 master token：
   ```bash
   ssh ycj 'cat /root/push-relay/backend/.master-once'  # 一次性文件
   # 或
   ssh ycj 'pm2 logs push-relay-backend --nostream | grep MASTER'
   ```
2. 打开 https://yangchenjie.com/admin
3. 输入 master token 解锁
4. 点「+ 新建 Token」→ 输入名称（如 `home-mac-terminal`）→ 选 role=user → 提交
5. **复制显示的明文**（只显示一次！）
6. 把这个 token 填到本机 `~/.zshrc` 的 `PUSH_TOKEN=...`
7. 删掉 server 上的 `.master-once` 文件

**日常管理**（创建 / 吊销 / 轮换）：
- 浏览器访问 https://yangchenjie.com/admin
- 输入 master token 解锁
- 列表里可以「轮换」（生成新明文，旧明文立即失效）或「吊销」（永久失效）
- sessionStorage 存储 master token，关闭 tab 自动清除

## 文件说明

| 文件 | 干什么的 |
|------|---------|
| `backend/server.py` | 跑在 ycj 上的 relay 服务（监听 8080，nginx 反代对外） |
| `backend/tokens.json` | Token 持久化（Argon2id 摘要，无明文） |
| `backend/requirements.txt` | Python 依赖：`aiohttp`, `websockets`, `argon2-cffi` |
| `frontend/client.html` | 本机接收端（网页版，单文件） |
| `frontend/client.py` | 本机接收端（终端版） |
| `frontend/admin.html` | Token 管理页面（需 master token） |
| `frontend/notify.sh` | Claude Code hook 脚本 |
| `deploy/nginx.conf` | nginx 反代 + 限流 + 静态文件 |
| `deploy/install.sh` | ycj 一键部署脚本 |
| `docs/README.md` | 完整文档 (部署 / Claude Code 集成 / Token 系统) |
| `docs/OPERATIONS.md` | 运维命令速查 (pm2 / git pull / 丢 master 怎么办) |
| `docs/USAGE.md` | 本文件，速查 |

## 常见问题

**客户端连不上？**
```bash
echo $PUSH_TOKEN     # 应该输出 token，没值就 source ~/.zshrc
ssh ycj 'curl -s http://127.0.0.1:8080/api/health'   # 应该返回 {"ok":true,...}
```

**WebSocket 频繁断开？**
- 确认 server 启用了心跳（`pm2 logs push-relay-backend` 应看到每 30s 的连接保持）
- 浏览器 client.html 现在有自动重连 + Page Visibility 处理
- 终端 client.py 默认 `ping_interval=20s`

**想换 token？**
不要直接编辑 `tokens.json`（那里只有摘要），用 admin 页面创建/轮换。

**想停 server？**
```bash
ssh ycj 'pm2 stop push-relay-backend'
```

**想重启 server？**
```bash
ssh ycj 'pm2 restart push-relay-backend && pm2 logs push-relay-backend --nostream | tail -20'
```

**server 日志在哪？**
```bash
ssh ycj 'pm2 logs push-relay-backend'
```

**丢了 master token 怎么办？**
```bash
# 1. ssh 进 ycj,直接编辑 tokens.json,删掉 master 那条
ssh ycj
vim /root/push-relay/backend/tokens.json
# 2. 重启 server,会自动重新生成 master 并在日志里打印
pm2 restart push-relay-backend
pm2 logs push-relay-backend --nostream | grep MASTER
```

## 信息

- **前端入口**：https://yangchenjie.com/
- **Admin 入口**：https://yangchenjie.com/admin
- **Token 来源**：`~/.zshrc` 里的 `PUSH_TOKEN`（用 admin 页面创建）
- **协议**：WSS（WebSocket over TLS）+ HTTPS POST

## 网页版（推荐）

不想开终端？浏览器打开 `client.html` 就行：

```bash
open ~/Desktop/push-relay/frontend/client.html
```

**功能**：实时消息流 + 浏览器原生通知 + 提示音 + 标题闪烁 + 自动重连 + 时区本地化 + 新字段徽章。

**首次使用**：
1. 浏览器打开后会请求通知权限，点"允许"
2. 在 Token 输入框填 token（从 `~/.zshrc` 的 `PUSH_TOKEN` 复制）
3. 点"连接"

之后配置自动保存到浏览器 localStorage，下次开自动恢复。连接断开会自动重连（指数退避 1s → 30s）。

**注意**：ycj 自签证书已装到本机钥匙串（一次性操作），浏览器会信任。