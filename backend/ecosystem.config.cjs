/**
 * push-relay 后端 pm2 配置（内网 HTTP，由 nginx 反代对外）
 * 在 ycj 上跑：cd /root/push-relay/backend && pm2 start ecosystem.config.cjs
 *
 * 监听：127.0.0.1:8080（仅内网，nginx 转发）
 * TLS：由 nginx 处理（外部 HTTPS）
 *
 * 启动后：
 *   pm2 status              # 看状态
 *   pm2 logs push-relay-backend  # 看日志
 *   pm2 restart push-relay-backend  # 重启
 *   pm2 stop push-relay-backend    # 停止
 *   pm2 save && pm2 startup  # 开机自启（root 跑）
 */
module.exports = {
  apps: [
    {
      name: "push-relay-backend",
      cwd: __dirname,
      script: "server.py",
      interpreter: "python3",
      interpreter_args: "-u",
      // 单实例
      instances: 1,
      exec_mode: "fork",
      // 自动重启
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      // 日志
      out_file: __dirname + "/logs/out.log",
      error_file: __dirname + "/logs/error.log",
      merge_logs: true,
      // 环境变量
      env: {
        HOST: "127.0.0.1",
        PORT: 8080,
        // PUSH_TOKEN 优先级：环境变量 > token 文件；不写在这里，从文件读
      },
    },
  ],
};