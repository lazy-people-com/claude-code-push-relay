// push-relay 公共脚本 — client.html / admin.html 共享
// escHtml: HTML 转义, 防 XSS; ?? "" 防御 null/undefined
// describeCloseCode: WSS 关闭码 → 用户可读的中文提示
// (4xxx 段是 IANA 留给应用层用的, server 端用 4401/4403/4400 表示鉴权错误)

function escHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[c]);
}

const WS_CLOSE_REASONS = {
  1000: "正常关闭",
  1006: "连接异常(证书未信任?服务器不可达?)",
  1008: "连接策略违规",
  4400: "服务器内部错误",
  4401: "未授权(缺少或无效的 Token)",
  4403: "权限不足(非 master)",
};
function describeCloseCode(code) {
  if (code === 1006) return WS_CLOSE_REASONS[1006];
  if (code >= 4000) return WS_CLOSE_REASONS[code] || `服务器拒绝 (HTTP ${code})`;
  return WS_CLOSE_REASONS[code] || `已断开 [${code}]`;
}
