# push-relay 全新环境部署

适用：在新 Linux 服务器上从零装 push-relay，不依赖 ycj。
`deploy/install.sh` 会处理 80% 工作，本清单只覆盖不能自动化的部分。

---

## 1. 服务器前置条件

| 项 | 要求 |
|----|------|
| OS | Rocky / RHEL / CentOS（install.sh 用 `dnf`）；Ubuntu 需把 `dnf` 换成 `apt` 再跑 |
| Python | 3.9+（`python3 -V`） |
| Git | 任意版本 |
| 权限 | root（要装 nginx + 起 pm2） |
| 域名 | 一个域名解析到本机（无域名直连 IP + 自签证书见 nginx.conf 443 段） |
| 端口 | 80（和/或 443）+ 8080（仅内网）放行 firewall |

---

## 2. 一行部署

```bash
ssh root@your-server 'bash -s' <<'SH'
set -e
APP=/root/push-relay                       # 或 /opt/push-relay
git clone https://github.com/lazy-people-com/claude-code-push-relay.git $APP
cd $APP

# ⚠️ 唯一必须改的地方:把 yangchenjie.com 换成你的域名（nginx.conf + install.sh echo 各一处）
sed -i 's/yangchenjie.com/your-domain.com/g' deploy/nginx.conf

bash deploy/install.sh
SH
```

install.sh 自动做：装 nginx → 复制前端 → 配置 nginx → 启 nginx → 装 Python 依赖 → 起 pm2。

---

## 3. 取 master token（首次启动生成）

```bash
ssh root@your-server 'pm2 logs push-relay-backend --nostream | grep MASTER'
# 输出形如: master token: pr_master_xxxxxxxxxxxxxxxxxxxxx
```

立即删一次性文件（防止一直保留明文）：
```bash
ssh root@your-server 'rm /root/push-relay/backend/.master-once'
```

---

## 4. 创建 user token

浏览器打开 `https://your-domain.com/admin`，输入 master token 解锁：

1. 点「+ 新建 Token」
2. Name：`home-mac-terminal`（任意）
3. Role：选 `user`
4. 提交后**立即复制显示的明文**（只显示一次！）

---

## 5. 本机配置

```bash
echo 'export PUSH_TOKEN="pr_user_xxxxxxxxxxxxxxxxxxxxx"' >> ~/.zshrc
source ~/.zshrc
```

（其他机器也可，把这个 user token 填到对应机器的 shell rc）

---

## 6. 验证

**服务器端健康检查**：
```bash
ssh root@your-server 'curl -s http://127.0.0.1:8080/api/health'
# 期望: {"ok":true, "clients":0, ...}
```

**本机接收端**：
- 网页：`open https://your-domain.com/`，Token 框填 `PUSH_TOKEN`，点"连接"
- 终端：`python3 ~/Desktop/push-relay/frontend/client.py`

跑一个 Claude Code 任务验证推送正常（在 claude 里随便执行一个 bash 命令，会触发 PostToolUse → notify.sh → 推到你刚连的客户端）。

---

## 7. 后续维护

| 场景 | 命令 |
|------|------|
| 改了后端代码 | 本地 `git push origin dev` 后 `ssh your-server 'cd /root/push-relay && bin/pull-and-deploy.sh'` |
| 改了前端代码 | 同上（脚本会同步到 nginx serve 目录） |
| 加 webhook 自动部署 | 见 [docs/OPERATIONS.md](OPERATIONS.md#自动部署-webhook)（一次性配置） |
| 启停 / 查日志 / 丢 master 怎么办 | 见 [docs/OPERATIONS.md](OPERATIONS.md) |

---

## 常见坑

| 现象 | 排查 |
|------|------|
| 浏览器 502 / 连接被拒 | 防火墙放行 80/443；nginx 是否在线（`ssh your-server 'systemctl status nginx'`） |
| `curl /api/health` 返回空 | push-relay-backend 没起（`pm2 status` 看，restart：`pm2 restart push-relay-backend`） |
| 浏览器 token 错 | 重新生成 / 用 admin 页面 rotate |
| 自签证书浏览器警告 | 装证书到本机钥匙串；或用 Cloudflare 在前面终结 TLS |
| Ubuntu 装 nginx 失败 | 把 install.sh 里的 `dnf install -y nginx` 换成 `apt install -y nginx` |

---

## 部署时长

- 网络快 + 新机器：~10 分钟（含 pip install + pm2 download）
- 慢机器：~20 分钟
