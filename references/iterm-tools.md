# MCP 操作约定

本约定已按 goals-iterm-mcp 当前源码 `direct.py`、`closing.py`、`closing_backend.py` 和 `cli_recovery.py` 校对（2026-10-26；对应 MCP 0.2.2）。源码实现不代表已安装服务已更新。宿主工具名可带不同命名空间，按以下短名匹配；若已安装版本的 schema 不同，先检查差异再调用。

| 工具 | 参数 | 用途 |
| --- | --- | --- |
| list_sessions | 无 | 返回 `sessions[]`；每行有 `session_id`、`name`、`window_id`、`tab_id` 和内部 `target`，不读取终端正文 |
| inspect_sessions | session_id OR nickname（可选，均省略则全部授权可见） | 只读回收能力诊断；仅实际服务公开此工具时使用 |
| read_screen | session_id | 返回 `screen`（含 lines/光标等）、`captured_at`、`truncated` |
| read_history | session_id, lines（默认 100，1–2000） | 最近保留历史，含 position/text/wrapped、source_bounds、truncated |
| send_text | session_id, text | 原样发送 1–16384 UTF-8 字节，不补换行 |
| send_keys | session_id, key | 发送一个控制键 |
| create_window | command（可选） | 新窗口，自动分配昵称，返回 session_id、tab_id、window_id、name |
| create_tab | window_id, command（可选） | 在准确窗口创建标签页，自动分配昵称，返回新目标 ID/name |
| rename_session | session_id, name（可选） | 设置昵称；省略时分配随机昵称 |

### 关闭工具（按能力启用）

先发现实际 schema；以下是当前源码的公开接口。`OR` 表示只能传一个定位参数，不是参数名称。`force`、`dry_run` 只接受 JSON 布尔值 `true/false`，不能传字符串或 0/1。未用到的定位字段省略。缺少工具或安全能力时报告具体阻碍，不用 shell/AppleScript 或发送退出键绕过。

| 工具 | 参数 | 范围与默认行为 |
| --- | --- | --- |
| close_session | session_id OR nickname, force=false, dry_run=false | 单个 Session；忙碌或未知时拒绝 |
| close_tab | tab_id OR session_id OR nickname, force=false, dry_run=false | 整个 Tab 的全部分屏；任一忙碌或未知时整体拒绝 |
| close_window | window_id OR session_id OR nickname, force=false, dry_run=false | 整个 Window 的全部 Tab/分屏；任一忙碌或未知时整体拒绝 |
| clean_all_sessions | force=false, dry_run=false | 默认选择可安全清理的空闲会话，逐个跳过忙碌/未知；force 尝试授权范围内全部会话 |

昵称去除首尾空白并忽略大小写后，匹配目录中的 `name`，必须唯一对应一个 Session；不模糊匹配，不定位 Tab 名称。ID 必须原样来自枚举，不能传 `active/current/focused/all/*`，也不会按昵称回退。长流程绑定稳定 ID，不按昵称重试。`force` 不绕过定位、权限和恢复信息保护。实际参数、返回字段及限制以运行中服务为准；差异影响范围或安全时先解决差异，不能把缺失能力当成已满足。调用前读取 [关闭与恢复](closing-and-recovery.md)。

可用 key：`enter`、`tab`、`escape`、`backspace`、`up`、`down`、`left`、`right`、`ctrl_c`、`ctrl_d`、`ctrl_u`、`ctrl_l`。

## 准确调用与返回解析

- 四个关闭工具和新 `inspect_sessions` 接受 `nickname`；读取、发送、改名仍需 `session_id`。`rename_session` 使用 `name`，不是 `nickname`。创建工具没有 `name` 参数；需要固定昵称时创建成功后用返回的 ID 改名。显式名称去除首尾空白后为 1–64 字符，禁止控制字符且须无大小写重名。
- `command` 是可选的启动命令，提供时必须为 1–16384 UTF-8 字节，不能用空字符串表示省略。不要向公开工具传内部的 `target`、PID、chat UUID、`resume`、`session_ids` 或 `suppress_broadcast` 字段。
- `list_sessions` 的 `sessions` 只有服务 allowlist 内的会话；看不到兄弟分屏不代表整个 Tab/Window 均获授权。容器预演/关闭仍可能返回 `OUT_OF_SCOPE`。allowlist 模式禁止创建窗口/标签页。
- 关闭工具返回 MCP `CallToolResult`：优先读取 `structuredContent`，宿主未暴露时解析 `content` 的 JSON 文本；也检查 `isError`。参数验证可能直接报工具错误而没有关闭结果；连接失败等早期错误也可能省略 `target/blocking_sessions`，按可选字段读取。普通读写工具的错误不能按关闭结果结构强行解析。

关闭结果的字段和判断：

| 字段 | 含义与处理 |
| --- | --- |
| `status` | `closed/partial/refused/noop/dry_run/unknown`；`partial` 也可能没有任何成功关闭，必须查数组 |
| `closed_sessions` | 已执行并验证终端消失的会话；有成功关闭和跳过项时顶层为 `partial`；只有跳过且无候选时通常为 `noop`，均不等于全部关闭 |
| `skipped_sessions`, `failed_sessions`, `unknown_sessions` | 逐项报告保留、失败、未知；`isError=true` 时仍可能有已成功关闭项，不能整批重试 |
| `would_close_sessions`, `would_skip_sessions` | 预演候选及排除项；`status=dry_run` 不表示全部预检通过，检查两数组、`blocking_sessions` 和 `code` |
| `target.session_ids` | 本次调用选中的原始范围；不是传给下一次调用的锁或批准令牌 |
| `recovery_record_id`, `recovery_record_path` | 实际恢复回执；预演、无候选或退出前拒绝时可为 null，不编造路径 |
| 每项 `state/reason/skip_code` | 活动状态和阻碍（字段可能缺省）；读取实际值，不把 prompt 当作 idle 证据 |
| 每项 `interruption/exit/closure_status` | 实际中断、退出、关闭状态；公开结果不使用内部 `task_interrupted` / `cli_exit_status` 字段 |
| 每项 `cli_sessions[]` | `cli/chat_uuid/cwd/identity_source/persistence_status/resume`；`resume` 是 `executable` + `argv` 数组，不是可直接拼接执行的 shell 字符串 |

退出后目标自动消失时可返回 `closure_method=auto_closed_after_exit`，不再调用原生关闭；以已核验消失为准，不要求每个成功结果都有原生关闭调用。当前 public `force` 也会原样传给 iTerm 原生 `async_close(force=...)`，不是另一个可独立设置的参数。

`isError` 在 `refused/unknown` 或存在 failed/unknown 项时为真；仅跳过不是错误。预演的候选为空、甚至 `isError=false` 时也要查 `would_skip_sessions`。`dry_run=true` 不发送输入、不保存回执、不改名、不关闭；实际执行重新采样，不复用预演计划。

常见关闭错误：`INVALID_SELECTOR/AMBIGUOUS_SELECTOR/SELECTOR_NOT_FOUND` 要重新核对准确目标；`ACTIVITY_BLOCKED` 不自动升级 force；`OUT_OF_SCOPE/SELF_PROTECTION` 不绕过；`CLI_IDENTITY_MISSING/CLI_IDENTITY_AMBIGUOUS/CLI_IDENTITY_STARTUP_ONLY`（最后一种只有启动 UUID，缺当前对话证据）、进程身份相关错误需保留目标并报告证据不足；`RECOVERY_PERSISTENCE_FAILED` 若发生在初始回执/首条执行日志阶段会阻止退出；若发生在退出或关闭后的日志更新阶段，可能已有副作用，须结合结果数组及实际拓扑核对。`TARGET_CHANGED`、退出/关闭失败、`TIMEOUT/CANCELLED` 等按逐会话结果只读核实，不盲目重试。普通读写的 `SESSION_NOT_FOUND` 与关闭的 `SELECTOR_NOT_FOUND` 不同。

## 调用示例（JSON 参数）

以下 ID/昵称是示例，运行时替换为实际枚举值。每段包含工具短名和参数；已有准确 ID 时优先绑定它，不为复用示例改用昵称。

```json
{"tool":"close_session","arguments":{"nickname":"api-worker","dry_run":true}}
```

```json
{"tool":"close_tab","arguments":{"session_id":"session-1","dry_run":true}}
```

```json
{"tool":"close_window","arguments":{"window_id":"window-1","dry_run":true}}
```

```json
{"tool":"clean_all_sessions","arguments":{"dry_run":true}}
```

预演后，在授权与范围仍一致时使用同一工具执行（省略 `dry_run` 或设为 `false`）。只有已授权中断才传 `force:true`；新调用会重新采样，全局清理不会固定在前一次预演的列表。需要固定具体会话集合时改按已核对的 Session ID 逐个关闭，并在每次调用前核对状态。

## 只读回收能力诊断

MCP 0.2.1 提供 `inspect_sessions`，read-only 模式也可使用；先发现工具再调用。准确 ID 与昵称互斥，均省略时只诊断 allowlist 可见会话；单任务优先指定已绑定 ID。返回 `sessions[]`，分列 prompt 可用性、process 身份/TTY/作业数量、CLI 当前身份/持久化/活动证据、terminal_activity、business_acceptance 和 close_readiness。`business_acceptance=not_observed`：MCP 不替协调者验收业务。

`close_readiness.status=eligible_if_unchanged` 只是当次证据下的条件性候选，`authorization=not_granted`，不替代归属、用户授权、dry_run 或关闭前复核。检查具体 `reason`、`remediation` 与 CLI `evidence_gap`；不将单个 ready 布尔值作为关闭指令。该工具不写恢复回执，不退出/关闭/发按键，不返回原始命令参数、环境或日志；它仍会读取必要的进程和 CLI 元数据。

缺 prompt 与缺进程信息分别报告；明确活动/停止作业可判 busy，但未观察到作业不单独证明 idle。CLI 身份可已验证而活动仍未知：普通登记只是线索，缺当次进程实例与当前对话证据不能视为 verified；旧缓存和启动 UUID 不能证明当前对话。当前源码尚未提供可用于所有 CLI 的可信实时 lifecycle hook，也没有公开任意 PID/UUID 注册入口；诊断不能补造该能力。已安装旧版没有工具时按 [启动检查](session-lifecycle.md) 降级到准确目标的关闭预演。

```json
{"tool":"inspect_sessions","arguments":{"session_id":"session-1"}}
```

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
