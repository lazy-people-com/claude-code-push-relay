#!/usr/bin/env bash
# push-relay SessionStart 钩子
#
# 从 Claude Code SessionStart stdin 读 JSON,提取 session_title 字段
# (用户用 `claude --name "xxx"` 或 `/rename` 设置的),通过 env 字段
# 注入到后续 hook 的环境变量 (PUSHRELAY_SESSION)。
#
# PreToolUse/PostToolUse/Stop/Notification 都不会传 session_title,
# 必须靠这个 SessionStart 钩子捕获,后续 notify.sh 才能拿到。
#
# 用法: 在 ~/.claude/settings.json 的 hooks 里加一条 SessionStart:
#   {
#     "hooks": [{
#       "type": "command",
#       "command": "bash /path/to/push-relay/frontend/capture-session.sh"
#     }]
#   }
#
# 用户没配这个钩子, PUSHRELAY_SESSION 永远为空, notify.sh 发的
# session 字段就是空字符串, 不影响现有功能。

set -uo pipefail

PAYLOAD=$(cat)
TITLE=$(printf '%s' "$PAYLOAD" | jq -r '.session_title // ""')

# 空 title 不输出 env,避免污染
if [[ -z "$TITLE" ]]; then
  exit 0
fi

# SessionStart 钩子的特殊输出格式: hookSpecificOutput.env 会注入到后续 hook
# 参考: https://code.claude.com/docs/en/hooks
jq -n --arg title "$TITLE" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    env: { PUSHRELAY_SESSION: $title }
  }
}'
