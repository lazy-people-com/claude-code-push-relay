# push-relay 运维命令

> 服务部署在 ycj 上,前端静态文件 nginx 直接 serve。改代码后需 rsync + pm2 restart(后端)/ 直接 rsync(前端,nginx 自动加载)。

## 服务启停

```bash
# 后端 (ycj)
ssh ycj 'pm2 start /root/push-relay/backend/ecosystem.config.cjs'   # 首次
ssh ycj 'pm2 stop    push-relay-backend'                              # 停
ssh ycj 'pm2 restart push-relay-backend'                             # 启
ssh ycj 'pm2 status'                                                  # 状态
```

## 改代码后重启

**后端** (改了 `backend/server.py`):
```bash
rsync -avz ~/Desktop/push-relay/backend/server.py ycj:/root/push-relay/backend/
ssh ycj 'pm2 restart push-relay-backend'
```

**前端** (改了 `frontend/client.html` / `admin.html` / `_common.css` / `_common.js`):
```bash
rsync -avz ~/Desktop/push-relay/frontend/client.html \
              ~/Desktop/push-relay/frontend/admin.html  \
              ~/Desktop/push-relay/frontend/_common.css \
              ~/Desktop/push-relay/frontend/_common.js  \
              ycj:/var/www/push-relay/
# nginx 静态文件自动加载,无需 reload
```

## 看日志

```bash
ssh ycj 'pm2 logs push-relay-backend'             # 实时
ssh ycj 'pm2 logs push-relay-backend --nostream'  # 一次性
ssh ycj 'pm2 logs push-relay-backend --nostream --lines 200 | tail -30'  # 最近 200 行末 30
```

## 持久化 (开机自启)

`pm2 startup` 生成的 init 单元会随系统启动拉起所有 pm2 进程。

```bash
# ycj (root 跑)
ssh ycj
pm2 save             # 把当前进程列表写到 ~/.pm2/dump.pm2
pm2 startup          # 会打印一条 sudo 命令,跟着跑
# 提示: [PM2] You have to run this command as root
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u root --hp /root

# 本机 (front-end serve 用)
pm2 save && pm2 startup
```

## 丢失 master token 怎么办

master token 是 admin 页面解锁的唯一凭证,丢了就只能从 `tokens.json` 里删掉 master 条目让 server 重新生成。

```bash
ssh ycj
vim /root/push-relay/backend/tokens.json
# 找到 "role": "master" 那条,整条删掉,保存
pm2 restart push-relay-backend
pm2 logs push-relay-backend --nostream | grep MASTER
# 日志里会打印新生成的 master token
```

## 健康检查

```bash
ssh ycj 'curl -s http://127.0.0.1:8080/api/health'
# 期望: {"ok":true,"clients":N,"proto":"http",...}
```

外部健康检查走 `https://yangchenjie.com/api/health`(经 nginx 443 → 8080)。

## 自动部署 (webhook)

`git push origin dev` 后, ycj 上的 webhook receiver 收到 github POST,自动跑 `pull-and-deploy.sh`。

### 链路

```
git push origin dev
    ↓ (github webhook POST /webhook)
ycj nginx 443 → 127.0.0.1:9000
    ↓
push-relay-webhook 进程 (aiohttp)
    ↓ HMAC SHA256 校验 (X-Hub-Signature-256)
    ↓ push event + refs/heads/dev 才接受
    ↓ 异步 exec
bin/pull-and-deploy.sh
```

### 接入步骤 (首次配, 一次性)

**1. ycj 上生成 secret**
```bash
ssh ycj 'openssl rand -hex 32 > /root/push-relay/bin/.webhook-secret && chmod 600 /root/push-relay/bin/.webhook-secret'
echo "记录 secret 内容: $(ssh ycj cat /root/push-relay/bin/.webhook-secret)"
```

**2. ycj 上拉起 webhook 进程** (`.gitignore` + ecosystem 已经配好)
```bash
ssh ycj 'cd /root/push-relay/backend && pm2 delete push-relay-backend 2>/dev/null; pm2 start ecosystem.config.cjs && pm2 save'
# pm2 status 应该看到两个进程: push-relay-backend + push-relay-webhook
```

**3. ycj 上 nginx reload** (新加 `location = /webhook`)
```bash
ssh ycj 'cp /root/push-relay/deploy/nginx.conf /etc/nginx/conf.d/push-relay.conf && nginx -t && nginx -s reload'
```

**4. github 配 webhook** (浏览器,一次性)
- 进 https://github.com/lazy-people-com/claude-code-push-relay/settings/webhooks
- **Add webhook**
- Payload URL: `https://yangchenjie.com/webhook`
- Content type: `application/json`
- Secret: 第 1 步生成的 secret 内容 (64 字符 hex)
- "Which events would you like to trigger this webhook?" → 选 **Just the push event.**
- Active: ☑
- **Add webhook**

### 验证

第一次配完后, 本地随便改个文档提交:
```bash
git commit --allow-empty -m "test: trigger webhook" && git push origin dev
```

几秒后看 ycj 上的 log:
```bash
ssh ycj 'pm2 logs push-relay-webhook --nostream --lines 10'
# 期望看到 [deploy] start: ... → [deploy] exit=0
```

github 上 webhook 页面也有 Redeliver 按钮可以手动重发 (调试用)。

### 失败排查

| 现象 | 排查 |
|------|------|
| 没收到 webhook 触发 | github webhook 页面 "Recent deliveries" 看返回码,401 = secret 错,500 = server 错 |
| `pm2 logs push-relay-webhook` 不见 deploy 输出 | receiver 没起 → 跑 `pm2 start backend/ecosystem.config.cjs` |
| nginx reload 后 502 | `nginx -t` 检查语法,看 nginx error log `/var/log/nginx/push-relay.error.log` |
| receiver 报 `SECRET_FILE not found` | `bin/.webhook-secret` 不存在或没读权限, 重新跑步骤 1 |

### 禁用回手动

如果 webhook 出问题想回手动:
```bash
# github webhook 页面取消 Active 勾
# ycj 上的 receiver 进程不用停, 不会触发 deploy 但继续接收请求 (HMAC 不对直接 401)
```

### 不要忘记 pm2 持久化

新加的 `push-relay-webhook` 进程如果机器重启不会自动起,需要:
```bash
ssh ycj 'pm2 save && pm2 startup'
```
(`pm2 save` 已经跑过了; `pm2 startup` 第一次会打印一条 systemd 命令,跟着跑)

---

## 一键重装

如果 ycj 上的环境全坏了,直接重跑 install.sh:

```bash
ssh ycj 'cd /root/push-relay && bash deploy/install.sh'
# 会重新装 nginx、复制前端文件、写 pm2 配置
```
