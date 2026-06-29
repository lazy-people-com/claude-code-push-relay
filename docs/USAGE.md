# push-relay 使用说明

## 一句话
Claude Code 跑任务时，事件通过 HTTPS 加密推到 ycj 服务器（443），本机客户端实时接收通知。

## 3 步使用

### 1. 启动客户端

```bash
source ~/.zshrc   # 第一次或新终端，让 PUSH_TOKEN 生效
python3 ~/Desktop/push-relay/client.py
```

终端会显示：
```
连接 wss://47.120.30.150:443/ws?token=***
✓ 已连接，等待通知 ...
```

留着别关。

### 2. 跑 Claude Code

正常用就行。跑任务时，上面的客户端窗口会实时弹出：

```
🔔 [2026-06-29T10:30:15] [claude-code/tool-use] 工具调用
🔔 [2026-06-29T10:30:18] [claude-code/stop]    Claude Code 已停止
```

### 3. 手动推消息（可选，调试用）

```bash
curl -k -X POST "https://47.120.30.150:443/notify?token=$PUSH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"自定义消息","type":"any"}'
```

`-k` 是因为用了自签证书。

## 文件说明

| 文件 | 干什么的 |
|------|---------|
| `server.py` | 跑在 ycj 上的 relay 服务（监听 443，TLS + token） |
| `client.py` | 本机接收端（终端版） |
| `client.html` | 本机接收端（网页版，单文件） |
| `ycj-cert.pem` | ycj 自签证书，已装到本机钥匙串 |
| `requirements.txt` | Python 依赖：`aiohttp`、`websockets` |
| `README.md` | 详细文档（部署、systemd、防火墙等），需要时翻 |
| `USAGE.md` | 本文件，速查 |

## 常见问题

**客户端连不上？**
```bash
echo $PUSH_TOKEN     # 应该输出 token，没值就 source ~/.zshrc
ssh ycj 'curl -k -s https://localhost:443/'   # 应该返回 {"ok":true,...}
```

**想换 token？**
```bash
ssh ycj 'rm /opt/push-relay/token && pkill -f "python3 server.py" && cd /opt/push-relay && nohup python3 server.py > server.log 2>&1 &'
ssh ycj 'cat /opt/push-relay/token'   # 新 token
```
然后更新本机 `~/.zshrc` 和 `~/.claude/settings.json` 里的 token。

**想停 server？**
```bash
ssh ycj 'pkill -f "python3 server.py"'
```

**想重启 server？**
```bash
ssh ycj 'cd /opt/push-relay && nohup python3 server.py > server.log 2>&1 &'
```

**server 日志在哪？**
```bash
ssh ycj 'tail -f /opt/push-relay/server.log'
```

## 信息

- 服务器：`47.120.30.150:443`（ycj）
- Token：`~/.zshrc` 里的 `PUSH_TOKEN`
- 协议：WSS（WebSocket over TLS）+ HTTPS POST

## 网页版（可选）

不想开终端？浏览器打开 `client.html` 就行：

```bash
open ~/Desktop/push-relay/client.html
```

**功能**：实时消息流 + 浏览器原生通知 + 提示音 + 标题闪烁。

**首次使用**：
1. 浏览器打开后会请求通知权限，点"允许"
2. 在 Token 输入框填 token（从 `~/.zshrc` 的 `PUSH_TOKEN` 复制）
3. 点"连接"

之后配置自动保存到浏览器 localStorage，下次开自动恢复。

**注意**：ycj 自签证书已装到本机钥匙串（一次性操作），浏览器会信任。