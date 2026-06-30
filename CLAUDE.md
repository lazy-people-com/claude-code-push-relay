# push-relay — 项目级指令

在该目录下进入 Claude Code 时自动加载。全局指令（中文优先 / 工作流 5 步法 / 删除确认 / Mermaid 绘图规范）见 `~/.claude/CLAUDE.md`，不重复。

---

## 项目一句话

通过长连接 (WSS + Token) 把 Claude Code 的事件实时推送到本地终端/浏览器。
链路：`frontend/notify.sh`（Claude Code hook）→ `backend/server.py`（ycj:8080）→ `frontend/{client.html, client.py}`（浏览器/终端）。

## 文档索引

| 想做 | 看 |
|------|-----|
| 全新环境从零部署 | `docs/INSTALL.md` |
| 整体架构 / WSS 协议 / Token 系统 | `docs/README.md` |
| 日常运维（启停 / 改代码后重启 / 丢 master 怎么办） | `docs/OPERATIONS.md` |
| 消息字段语义（每字段谁填 / 例子） | `docs/FIELDS.md` |
| 速查（3 步用起来） | `docs/USAGE.md` |
| 当前部署状态表 | 主 `README.md` |

## 目录速记

```
backend/server.py              # aiohttp + WebSocket, 127.0.0.1:8080
backend/ecosystem.config.cjs   # pm2 进程定义 (backend + 可选 webhook)
frontend/_common.css / _common.js   # 两 HTML 共享 (escHtml + WS_CLOSE_REASONS)
frontend/client.html           # 网页接收端 (含设置弹窗 / 按 type 过滤 / 内联消息测试)
frontend/admin.html            # Token 管理页面 (master 鉴权)
frontend/client.py             # 终端接收端
frontend/notify.sh             # Claude Code 钩子 (Pre/PostToolUse / Stop / Notification)
bin/pull-and-deploy.sh         # ycj 一键拉码 + 同步前端 + restart backend
deploy/install.sh              # 全新环境初始化 (装 nginx + 复制前端 + 起 pm2)
deploy/nginx.conf              # nginx 反代 + 限流 + 静态文件
```

## 部署流

```bash
# 本机
git commit -m "..." && git push origin dev

# ycj (git 仓库,origin = git@github.com:lazy-people-com/claude-code-push-relay.git)
ssh ycj 'cd /root/push-relay && bin/pull-and-deploy.sh'
```

ycj deploy key 在 `~/.ssh/github_deploy`（read-only）。**不要手动 rsync**（会被 git 跟踪文件覆盖）。

## 加新字段（高发变更 — 必做 5 处）

通知 payload 加一项必须改：
1. `frontend/notify.sh` — jq 提取 + 加到 `--arg` + JSON 模板
2. `backend/server.py:NOTIFY_FIELDS` — 白名单元组
3. `frontend/client.html` — 详情弹窗 `fields` 数组 + 消息列表徽章（若有颜色）
4. `frontend/client.py` — 终端 `data.get("...")` + badge 输出
5. `docs/FIELDS.md` — 字段说明 + 「字段表 vs 代码」表加一行

漏一处即数据不一致或 silent drop。

## WSS 关闭码

server 端定义（`backend/server.py:WS_CLOSE_*`），客户端映射：
- `4401` 鉴权失败 / `4403` 非 master / `4400` 内部错误
- `1006` 协议升级失败 / `1008` 策略违规

客户端映射在两处，**改一处必须同步另一处**：
- 浏览器：`frontend/_common.js:WS_CLOSE_REASONS`
- 终端：`frontend/client.py:WS_CLOSE_REASONS`

## commit 风格

`feat(scope): xxx` / `fix(scope): xxx` / `refactor(scope): xxx` / `docs: xxx` /
`deploy: xxx` / `chore: xxx`

中文描述，scope 在括号内。不写「fix bug」「update code」这种空描述。

---

## 不要做

- 不要把 `tokens.json` / `*.pem` / `.webhook-secret` / `id_rsa*` / `.env*` 加进 git（`.gitignore` DANGER 块已列；**删行即泄密**）
- 不要在 ycj 上手动 vi 改 server.py 等被 git 跟踪的文件（下次 `pull-and-deploy.sh` 会覆盖）
- 不要在新代码里写 `escapeHtml` / `esc` — 一律用 `_common.js:escHtml`
- 不要把流程图画横向 (`flowchart LR`) — 倾向 TB（节点 ≥4 必 TB）
- 不要在用户没要求时主动 `git revert` / 删文件 / 删 commit（先确认）
- 不要给后端进程用 systemd unit（项目走 pm2，参见 `backend/ecosystem.config.cjs`）
