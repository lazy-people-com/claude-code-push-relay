#!/usr/bin/env bash
# push-relay Claude Code hook 脚本
#
# 从 Claude Code hook stdin 读 JSON,组装 push-relay payload,curl 推送。
# 提取 host / tool_name / tool_input / stop_reason / 详细 message。
#
# stdin 格式参考 Claude Code hook 协议:
#   PreToolUse / PostToolUse: { session_id, transcript_path, cwd, hook_event_name,
#                                tool_name, tool_input, ... }
#   Stop:                     { session_id, ..., stop_hook_active }
#   Notification:             { session_id, ..., message, notification_type }
#
# 用法: 在 ~/.claude/settings.json 的 hooks 里指向本脚本:
#   "command": "/path/to/push-relay/frontend/notify.sh"
# 所需依赖: bash, jq, curl (jq 用于解析 Claude Code 传过来的 JSON)
# 环境变量:
#   PUSH_URL    - 推送地址,默认 https://yangchenjie.com/api/notify
#   PUSH_TOKEN  - token,从 ~/.zshrc 读取

set -uo pipefail

# ── 读 stdin ──
PAYLOAD=$(cat)

PUSH_URL="${PUSH_URL:-https://yangchenjie.com/api/notify}"
PUSH_TOKEN="${PUSH_TOKEN:-}"

if [[ -z "$PUSH_TOKEN" ]]; then
  echo "notify.sh: PUSH_TOKEN 未设置,跳过推送" >&2
  exit 0
fi

# ── 解析 host ──
HOST=$(hostname -s 2>/dev/null || hostname)
[[ -z "$HOST" ]] && HOST="unknown"

# ── 解析事件类型 ──
EVENT=$(printf '%s' "$PAYLOAD" | jq -r '.hook_event_name // "Notification"')

# ── 解析工具相关字段(若存在) ──
TOOL=$(printf '%s' "$PAYLOAD" | jq -r '.tool_name // ""')
# tool_input 可能是 string 或 object,统一转字符串并 truncate 到 200 字符
TOOL_INPUT=$(printf '%s' "$PAYLOAD" | jq -c '.tool_input // ""' 2>/dev/null | head -c 200)

# ── 事件分类处理 ──
case "$EVENT" in
  PostToolUse)
    TYPE="tool-use"
    CONTENT="工具调用: $TOOL"
    STOP_REASON=""
    TASK=""
    ;;
  PreToolUse)
    TYPE="tool-use"
    CONTENT="即将使用: $TOOL"
    STOP_REASON=""
    TASK=""
    ;;
  Stop)
    TYPE="stop"
    # stop_hook_active=true 表示用户在交互模式,可视为 interrupted
    # 简化判定: stop_hook_active=true → interrupted,否则 completed
    STOP_REASON=$(printf '%s' "$PAYLOAD" | jq -r 'if .stop_hook_active == true then "interrupted" else "completed" end')
    CONTENT="Claude Code 已停止"
    TASK=""
    ;;
  Notification)
    TYPE="notification"
    CONTENT=$(printf '%s' "$PAYLOAD" | jq -r '.message // "通知"')
    TASK="$CONTENT"
    STOP_REASON=""
    ;;
  *)
    TYPE="notification"
    CONTENT="$EVENT"
    STOP_REASON=""
    TASK=""
    ;;
esac

# ── 拼装最终 JSON ──
JSON=$(jq -n \
  --arg source      "claude-code" \
  --arg type        "$TYPE" \
  --arg content     "$CONTENT" \
  --arg host        "$HOST" \
  --arg tool        "$TOOL" \
  --arg tool_input  "$TOOL_INPUT" \
  --arg task        "$TASK" \
  --arg stop_reason "$STOP_REASON" \
  '{source:$source, type:$type, content:$content, host:$host, tool:$tool, tool_input:$tool_input, task:$task, stop_reason:$stop_reason}')

# ── 推送(失败不中断 hook) ──
curl -k -s -X POST "$PUSH_URL?token=$PUSH_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$JSON" >/dev/null 2>&1 || true

exit 0
