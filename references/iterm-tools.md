# MCP 操作约定

基于 goals-iterm-mcp 源码的 `src/goals_iterm_mcp/direct.py`。宿主工具名可带不同命名空间，按以下短名匹配；若已安装版本的 schema 不同，先检查差异再调用。

| 工具 | 参数 | 用途 |
| --- | --- | --- |
| list_sessions | 无 | 返回 sessions，绑定准确 session_id；window/tab 信息可能位于 target |
| read_screen | session_id | 当前渲染屏幕、光标、captured_at、truncated |
| read_history | session_id, lines（默认 100，1–2000） | 最近保留历史，含 position/text/wrapped、source_bounds、truncated |
| send_text | session_id, text | 原样发送 1–16384 UTF-8 字节，不补换行 |
| send_keys | session_id, key | 发送一个控制键 |
| create_window | command（可选） | 新窗口，返回 session_id、tab_id、window_id、name |
| create_tab | window_id, command（可选） | 在准确窗口创建标签页，返回新目标 ID |
| rename_session | session_id, name（可选） | 设置昵称；省略时分配随机昵称 |

可用 key：`enter`、`tab`、`escape`、`backspace`、`up`、`down`、`left`、`right`、`ctrl_c`、`ctrl_d`、`ctrl_u`、`ctrl_l`。

## 输入和投递语义

- `send_text` 中的换行可能直接触发执行。简短单段 prompt 优先一次发送，再读取确认输入状态，必要时单独发送 `enter`。对于多行文本，根据目标 CLI 实际编辑器行为处理，不假设支持粘贴模式。
- 输入框中已有用户草稿时不要追加、清空或覆盖。先确认归属；任务尚未提交时，记录“待提交”，不要把其文本回显当成运行证据。
- 菜单按当前屏幕选项选择。只有界面明确接受文字时才用文字，否则按实际按键操作，每步核对；不盲目默认按 Enter。
- 工具返回 `api_acknowledged: true` / `task_completion: unknown` 仅代表 iTerm API 确认，不证明 CLI 收到、开始或完成任务。
- 超时和错误之后投递可能已经发生。先读屏幕/历史核对，只有确认未提交才重新发送。无法确定时保持观察或报告不确定性，尤其不能重复发布、付款、删除等动作。
- 服务内部已使用抑制广播的发送方式；公开工具没有 `suppress_broadcast` 参数，不向调用添加不存在的字段。

## 读取局限

屏幕/历史是渲染文本，不是原始 PTY、CLI 内部消息或进程状态。TUI 可能只更新屏幕而不新增历史；提示符可能在工作中持续显示。综合当前屏幕、历史和前后变化判断，不能用单一词语或“有输入框”判定空闲。

先读屏幕，缺上下文时读最近 100–300 行，必要时最多 2000 行。`truncated` 表示证据不完整；历史坐标可能随会话重置或保留窗口改变，不当作永久事件 ID。去重可以结合历史位置和文本摘要，但不要把动画变化视为实质进度。

## 会话及连接异常

`SESSION_NOT_FOUND` 时重新枚举，不能按相同昵称自动绑定一个新会话。会话消失不等于任务完成；新建或恢复前检查已产生的结果及任务归属。

MCP 连接错误不同于 CLI 网络错误。连接中断时先恢复只读观察，不重建终端或重放指令。`--read-only` 没有写工具；`--session-id` 限定访问时禁止创建新窗口/标签页。服务只在单个 MCP 进程内串行操作，不会锁住用户或其他 agent 的输入。
