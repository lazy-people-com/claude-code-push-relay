/**
 * push-relay pm2 配置（ycj 上跑）
 *   cd /root/push-relay/backend && pm2 start ecosystem.config.cjs
 *
 * 包含两个进程：
 *   push-relay-backend  — aiohttp WebSocket relay, 内网 127.0.0.1:8080
 *   push-relay-webhook  — 收 github webhook, 触发自动部署 (内网 127.0.0.1:9000)
 *
 * nginx: 外部 443 进来, /api/* → 8080, /webhook → 9000
 *
 * 启动后：
 *   pm2 status
 *   pm2 logs push-relay-backend
 *   pm2 logs push-relay-webhook
 *   pm2 restart all
 *   pm2 save && pm2 startup  # 开机自启
 */
module.exports = {
  apps: [
    {
      name: "push-relay-backend",
      cwd: __dirname,
      script: "server.py",
      interpreter: "python3",
      interpreter_args: "-u",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      out_file: __dirname + "/logs/out.log",
      error_file: __dirname + "/logs/error.log",
      merge_logs: true,
      env: {
        HOST: "127.0.0.1",
        PORT: 8080,
      },
    },
    {
      name: "push-relay-webhook",
      cwd: __dirname + "/..",  // 项目根 (/root/push-relay)
      script: "bin/webhook-receiver.py",
      interpreter: "python3",
      interpreter_args: "-u",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      out_file: __dirname + "/logs/webhook-out.log",
      error_file: __dirname + "/logs/webhook-error.log",
      merge_logs: true,
      env: {
        WEBHOOK_HOST: "127.0.0.1",
        WEBHOOK_PORT: 9000,
        REPO_DIR: __dirname + "/..",
      },
    },
  ],
};