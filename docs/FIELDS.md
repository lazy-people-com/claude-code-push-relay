# push-relay 消息字段

> 描述 `notify.sh` 发的 payload + server 注入的 timestamp,以及每个字段在哪种事件下有值。
> 客户端解析顺序见 `frontend/client.html` 的 `showMessageDetail()` 函数。

## 完整 payload

WSS 接收端收到的字段 (server 端 `NOTIFY_FIELDS` 白名单 + server 注入 timestamp):

```json
{
  "timestamp":   "2026-06-29T18:30:15+08:00",
  "source":      "claude-code",
  "type":        "tool-use",
  "content":     "工具调用: Bash",
  "host":        "my-mac.local",
  "tool":        "Bash",
  "tool_input":  "{\"command\":\"ls -la\"}",
  "task":        "",
  "stop_reason": ""
}
```

## 字段说明

字段顺序与 `client.html` 详情弹窗一致。

### `timestamp` (server 注入)
- **类型**: string (ISO 8601,带时区偏移)
- **谁填**: server 端,推送时用 `datetime.now().astimezone().isoformat(timespec="seconds")` 生成
- **客户端**: 浏览器用 `new Date().toLocaleString("zh-CN")` 转本地时区;Python 终端用 `datetime.fromisoformat(...).astimezone()` 转本地

### `source`
- **类型**: string
- **当前值**: 固定 `"claude-code"`
- **用途**: 区分多触发源 (例如未来如果加其他 hook 来源,可以加 `"source": "github-action"` 等)
- **谁填**: notify.sh 写死

### `type` (决定触发哪些 UI 行为)
- **类型**: enum string
- **值**: `"tool-use"` | `"stop"` | `"notification"`
- **谁填**: notify.sh 根据 `hook_event_name` 映射:
  - `PostToolUse` / `PreToolUse` → `tool-use`
  - `Stop` → `stop`
  - `Notification` → `notification`
  - 未知事件 → `notification` (兜底)
- **客户端**: `client.html` 设置弹窗按 type 选是否触发声音/桌面通知/标题闪烁

### `content`
- **类型**: string
- **谁填**:
  - `tool-use` → `"工具调用: <tool>"` 或 `"即将使用: <tool>"`
  - `stop` → `"Claude Code 已停止"`
  - `notification` → `payload.message` 原文 (空时为 `"通知"`)
- **客户端**: 消息列表正文,详情弹窗第一行

### `host`
- **类型**: string
- **谁填**: notify.sh 跑 `hostname -s` 取本机短名 (取不到时用 `hostname`,再不行用 `"unknown"`)
- **客户端**: 消息列表加 `🖥 <host>` 徽章;详情弹窗独立一行

### `tool`
- **类型**: string
- **谁填**: notify.sh 从 Claude Code `tool_name` 字段取 (PostToolUse/PreToolUse 事件有值)
- **其他事件**: 空字符串
- **客户端**: 消息列表加 `🔧 <tool>` 徽章;详情弹窗独立一行

### `tool_input`
- **类型**: string
- **谁填**: notify.sh 把 Claude Code `tool_input` 字段 (string 或 object) 用 `jq -c` 统一转字符串,再 `head -c 200` 截断到 200 字符
- **其他事件**: 空字符串
- **客户端**: 消息列表加 `⚙️ <tool_input>` 行;详情弹窗**完整**显示 (不被 200 字符截断)
- **注意**: 消息列表里的 200 字符截断是 `notify.sh` 行为,详情弹窗里看的是 server 透传的原文 (可能更长),因为 server 转发的是 `notify.sh` 截断后的字符串

### `task`
- **类型**: string
- **谁填**: **仅 `notification` 事件** (从 `payload.message` 取,与 `content` 同值)
- **其他事件**: 空字符串 (`PostToolUse` / `PreToolUse` / `Stop` 都不会填)
- **客户端**: 消息列表加 `📋 <task>` 行 (与 content 重复时不显示);详情弹窗独立一行
- **历史说明**: 早期 USAGE.md 写"task 仅 Notification 事件非空"是对的,但描述里说"详细任务 (Notification 事件)"容易让人误以为 PostToolUse 也会填 task。**没有,只有 Notification 会填。**

### `stop_reason`
- **类型**: enum string
- **值**: `"completed"` | `"interrupted"`
- **谁填**: notify.sh 在 `Stop` 事件时判断 `stop_hook_active`:
  - `true` → `"interrupted"` (用户在交互模式,可视为中断)
  - `false` 或缺失 → `"completed"`
- **其他事件**: 空字符串
- **客户端**: 消息列表加 `⟶ <stop_reason>` 徽章 (completed = 绿 / interrupted = 灰 / 未来 error = 红);详情弹窗独立一行
- **历史说明**: USAGE.md 写"stop_reason (completed / error / interrupted)" — **error 当前不会由 notify.sh 产生**。`error` 只在 server 端 _TEST_SCENARIOS 测试场景里有。要让 notify.sh 发 `error` 需要扩展 (例如 hook 失败时)。

## 调试

测试时可以直接 `curl` 模拟:

```bash
curl -X POST "https://yangchenjie.com/api/notify?token=$PUSH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source":      "claude-code",
    "type":        "tool-use",
    "content":     "工具调用: Bash",
    "host":        "my-mac",
    "tool":        "Bash",
    "tool_input":  "ls -la",
    "task":        "",
    "stop_reason": ""
  }'
```

server 端会注入 timestamp,按 token 路由给目标客户端。

## 字段表 vs 代码

| 字段 | server 端白名单 (NOTIFY_FIELDS) | notify.sh 发送 | client.html 读取 | client.py 读取 |
|------|-------------------------------|----------------|-----------------|----------------|
| timestamp | (server 注入) | ❌ | ✅ | ✅ |
| source | ✅ | ✅ | ✅ | ✅ |
| type | ✅ | ✅ | ✅ | ✅ |
| content | ✅ | ✅ | ✅ | ✅ |
| host | ✅ | ✅ | ✅ | ✅ |
| tool | ✅ | ✅ | ✅ | ✅ |
| tool_input | ✅ | ✅ | ✅ | ✅ |
| task | ✅ | ✅ (仅 notification) | ✅ | ✅ |
| stop_reason | ✅ | ✅ (仅 stop) | ✅ | ✅ |

任何一处加了新字段都需要更新其他三处 + 这份文档。
