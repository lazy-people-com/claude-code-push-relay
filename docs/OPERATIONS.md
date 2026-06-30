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

## 一键重装

如果 ycj 上的环境全坏了,直接重跑 install.sh:

```bash
ssh ycj 'cd /root/push-relay && bash deploy/install.sh'
# 会重新装 nginx、复制前端文件、写 pm2 配置
```
