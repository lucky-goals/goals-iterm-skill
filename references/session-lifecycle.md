# 会话登记、启动检查与收尾责任

在创建、接管、复用会话以及完成任务时读取本协议。终端操作仍由 MCP 执行；登记文件描述宿主掌握的事实，不赋予关闭权限，也不替代 MCP 的实时预检。

## 先检查能否恢复和收尾

创建前确认关闭/诊断工具、当前客户端权限和真实监控方式，记录实际 MCP/CLI/Skill 版本。优先使用已安装服务提供的 `inspect_sessions` 只读诊断（见 [工具约定](iterm-tools.md)）；缺少专用诊断时对准确 Session 使用关闭工具的 `dry_run=true, force=false`，不能把全局清理当成本任务探测。尚未创建的目标不编造预检结果。

新 CLI 启动后、派发前检查：

- 启动环境是否允许对话历史持久化；如果界面明确提示 transcript saving off，先按该 CLI 的本地帮助修复新会话的启动方式，再派发。不要统一删除环境变量或套用未验证参数；已有活跃会话保持运行，记录限制并等待合适的交接点。
- 当前对话 UUID 的来源是否绑定到实际进程实例；区分当前证据、仅启动参数和未知。新建空对话在首轮前没有 UUID 时可暂记 unknown，在首轮实际响应后补核，不能为取 UUID 编造工作或探测忙碌 CLI。
- MCP 是否能判断当前活动、保存恢复回执并安全退出；进程存活、shell 命令运行、CLI 等待输入与业务验收是四种不同事实。

未具备条件时记录 `recovery_status=degraded/unknown` 和具体原因，告知自动回收尚不可保证。未知不自动取消用户已授权的工作，但不得将明确关闭历史保存的启动方式当成合格默认配置。已知阻碍尽早处置，不积累到最终退出时才发现。

`recovery_status=ready` 也只是最近一次观察：不等于当前可关闭，不保证已经实际恢复过。最终仍复核进程、对话身份、持久化与工具返回。

## 统一登记和交接

本机不同协调者使用同一个状态位置，默认 `~/.local/state/goals-iterm-skill/session-registry.json`。使用随技能提供的 `scripts/session_registry.py` 更新；通过 `--help` 查看实际参数。Python 标准库即可运行，不需安装服务。状态放在私有目录，不进入仓库或技能安装目录。

登记至少包含准确 Session ID、owner_task_id、coordinator_id、generation、当前 revision、来源、保留策略和审计台账绝对路径。常规工作默认由当前协调者在本轮内联复查，记录 `monitor_mode=inline`；只有用户明确授权且宿主确有调度能力时才用 `background`。`none` 表示明确没有监控，旧记录缺少该字段时按 `unknown` 处理。`monitor_mode` 说明复查计划在哪里进行，不代表 monitor 当前存活；`monitor_status` 是独立的状态断言。根据可见证据补充 `owned_container`（仅 tab_id/window_id/basis）和 cleanup_authorization、Tab/Window ID、session/broker epoch、进程实例、CLI/chat UUID、活动和恢复状态、验收依据、monitor 状态、回收原因及后续待办。不把昵称、目录、PID 单独用作身份。

- 创建成功立即 register；登记失败时不继续派发新工作。遗留会话只有来源证据时才填 created/adopted，否则记 unknown 并保留。
- 每次投递结果、验收、复用、移动 Tab、更换 CLI、关闭预演和实际结果都同步登记，并按 [审计协议](audit.md) 追加事件。
- 更新携带 coordinator_id、generation 和 expected_revision。文件锁保护登记写入，版本冲突时重新读取、核对现场，不把旧 patch 强行重放。
- 同任务换协调者时 handoff 保留业务及回收结果，尤其保留 closing/unknown，不能借交接重置未知副作用。将同一终端交给新任务时执行明确 handoff，递增 generation，清除旧验收与关闭资格；新任务关联自己的台账。改名不会创建新任务，旧会话的完成消息不能关闭新任务。
- 身份或拓扑变化时按帮助要求重新绑定、递增代次并复核，尤其不能沿用旧窗口独占结论。协调者失联或记录过期只触发调查，不自动取得使用权。

常用命令如下（先把 `/absolute/path/to/skill` 和示例 ID/代次替换为实际值；record/patch 文件只包含已观察且脱敏的字段）：

```sh
python3 /absolute/path/to/skill/scripts/session_registry.py register --record /private/path/record.json
python3 /absolute/path/to/skill/scripts/session_registry.py list --task-id task-1
python3 /absolute/path/to/skill/scripts/session_registry.py update --session-id S1 --coordinator-id C1 --generation 1 --expected-revision 1 --patch /private/path/patch.json
python3 /absolute/path/to/skill/scripts/session_registry.py handoff --session-id S1 --coordinator-id C1 --generation 1 --expected-revision 2 --new-coordinator-id C2 --new-task-id task-2 --audit-path /private/path/task-2.md --reason "explicit task handoff"
python3 /absolute/path/to/skill/scripts/session_registry.py report --task-id task-2 --require-settled
```

最小 register 文件结构如下；这里只展示格式，不代表任何真实授权或目标：

```json
{"session_id":"S1","owner_task_id":"task-1","coordinator_id":"C1","origin":"created","cleanup_policy":"auto_owned","audit_path":"/private/path/task-1.md","monitor_mode":"inline"}
```

registry schema 仍为 v1；旧 v1 记录缺少 `monitor_mode` 时读取为 `unknown`，不抹除或重置已有字段。同任务 handoff 将 mode 置为 `unknown` 并保留旧的真实 `schedule_handle`/`next_check_at` 供新协调者核实或停用；跨任务 handoff 和身份代次变化会使旧 mode 失效。旧版已安装的 registry 脚本会拒绝新字段；开始写入 `monitor_mode` 前先升级协调者使用的脚本。

generation 标识身份/交接代次，普通派发、观察和 finalizing 通过 update 增加 revision，不为停止 monitor 而 handoff 或重置业务。旧回调核对这两个版本及当前阶段，finalizing 禁止业务写入。closing/unknown 必须先只读核实并记录结果，才能切换任务或身份。更新使用返回的新 revision/generation，不机械沿用示例数字。身份/拓扑更新会重置旧完成与恢复资格；另一次现场核验后才更新完成状态。跨任务交接默认恢复为 borrowed/retain，并清除旧授权依据；新任务如已有明确回收授权，另一次带版本校验的 update 必须同时提交 `cleanup_policy=auto_owned` 和非空 `cleanup_authorization`（描述已有授权来源，登记本身不授予权限）。同任务换协调者将 monitor status/mode 标为 unknown，并保留旧 schedule_handle/next_check_at 供接管核实或停用；保留句柄不是证明它仍在运行。时间字段使用 UTC ISO 8601；仅写 next_check_at 不等于已调度，需要实际 schedule_handle。`report` 展示 `monitor_mode` 与 `schedule_status`：inline 不会伪装成 scheduled；只有真实非空 schedule_handle 才使 `schedule_status=scheduled`。`report --require-settled` 对未收尾资源或零匹配均返回非零，不能将空报表当成成功。

登记工具不会联系 iTerm、发送按键、退出 CLI 或创建后台任务，也无法阻止未参与协议的用户/客户端操作。调用终端写工具前仍须核对现场及最新登记；记录中的状态不是终端锁或授权证明。

## 业务完成后仍有收尾阶段

逐会话记录 `execution_status`、`coordinator_phase`、`cleanup_status`，不能用一个 completed 掩盖资源残留。

1. 子任务成果已被协调者接收、验收证据齐全且没有后续消费者需要该 CLI 上下文时，可以独立进入 finalizing，不必等待所有并行任务结束。尚需复用时保留并记录用途和复查条件。
2. 将业务记 completed、协调阶段记 finalizing；停止该目标的业务写入 monitor 并核对成功。唯一收尾协调者继续负责 [自动回收](automatic-cleanup.md)，不能在此处结束整个协调流程。停止业务 monitor 不会中断 `monitor_mode=inline` 的本轮 finalizer；finalizer 可按退避等待、只读检查并有界复查收尾条件。
3. 明确用户保留或借用资源时记 retained，并写 retention_reason；需要限时保留时记录 retain_until。到期只是复核触发点，不是关闭授权。
4. 对本任务可回收资源刷新现场、预演、记意图、调用关闭，再逐项核实。实际关闭确证后才记 closed。保留对象仍须说明原因，不能把 blocked 改写成 retained 来隐藏失败。
5. 汇报前运行登记工具 report（按任务筛选），核对所有登记资源及当前观察。`--require-settled` 用于检查是否仍有未收尾记录；通过也只证明登记内容满足要求，不证明现场已关闭。

业务失败、暂停、取消或等待用户不会自动取得关闭权限；它们同样必须有资源去向说明。不能静默遗留，也不能只为让报表通过而强关终端。

## 有界复查与结果未知

回收遇到阻碍时保留原目标及精确原因，区分：

| 情况 | 后续行动 |
| --- | --- |
| 已确认未产生副作用，且属于暂时条件 | 当前轮内由 inline finalizer 按退避有界复查；如需本轮之后继续，记录下一次检查，并使用真实后台 schedule_handle |
| UUID 缺失、只有启动身份、历史未保存、归属不明 | 记录需要补齐的证据或人工处理；条件没有变化时不反复调用关闭 |
| 关闭响应丢失、执行中报错、状态 closing/unknown | 只读核对拓扑与准确回执，不自动重发，也不让旧 monitor 重建 CLI |
| 无可用调度或当前执行即将结束 | 当前轮内 inline finalizer 仍可睡眠后只读检查并有界复查；若需要本轮结束后继续，必须有用户授权、宿主能力和真实后台 schedule_handle，否则明确 unscheduled、下一动作与责任方 |

对同一未变化的收尾阻碍，默认最多复查两次并遵守更长服务退避；两次后仍未变化就停止重复尝试，记录阻碍、下一动作与责任方，不能用持续轮询掩盖未知结果或第一次未确认的副作用。此上限只约束重复的收尾尝试，不限制健康运行期间按业务需要进行的常规观察。复查只观察/收尾，不恢复业务写入 monitor，不扩大到新 Session，不升级 force。需要本轮之后继续复查时，未来调度须符合宿主能力与用户授权，记录真实创建结果；不要仅保存 `monitor_mode=background` 或时间字段就宣称已安排。

## 最终资源账单

最终回答除业务结果外列出：本任务登记/本次观察资源数、已关闭、明确保留、回收受阻、结果未知；分别说明原因、已停止或仍存活的 CLI/monitor、恢复回执与台账链接、下一步和是否确有调度。未经读取不能估计内存收益。多会话每项可用 Tab ID 与昵称便于识别，真实绑定保留准确 ID。

结束协调前，所有资源都必须有明确去向。有真实阻碍时可以向用户交接并结束本轮；业务已验收而回收仍受阻时保留 finalizing 和 cleanup blocked/unknown，业务验收前的阻碍保留真实执行阶段。不要宣称全部完成，也不把未执行的后续动作写成已调度。

## 设计取舍

仅增加 Markdown 规则不能检测旧协调者覆盖新任务；常驻自动清理服务会增加权限与部署负担。因此使用带文件锁和版本校验的轻量登记文件，保留 Markdown 作为人类可读的过程证据，实际动作继续受 MCP 保护。该实现针对同机少量并行终端；跨机器使用独立状态目录并明确交接，不把本地文件锁当成分布式锁。

## 定向行为验证

| 场景 | 应有行动 |
| --- | --- |
| 新 Claude 明确提示不保存 transcript | 修复新启动流程后再派发，不留到关闭时处理 |
| 新建空对话暂无 UUID | 记 unknown，首轮响应后补核，不伪造 UUID 或额外任务 |
| 上个任务已验收，同 Session 开始新任务 | handoff/新代次，旧回调不能关闭或覆写新任务 |
| 多任务共享窗口，某子任务已验收 | 只处理该任务符合条件的 Session/Tab，不关闭共享窗口 |
| 业务 completed、cleanup pending | 继续 finalizing，资源账单暴露未收尾，不提前全成功 |
| 无新证据且连续身份预检失败 | 有界停止，留下具体阻碍与处理方式，不自动 force |
| 关闭结果未知，协调者恢复 | 只读核实，不能根据超时或 pending 再次关闭 |
| 保留期限已到但用户正在使用 | 保留并更新记录，不因期限到达关闭 |
| 状态文件更新冲突或损坏 | 停止新写入，核对/恢复记录，不覆盖原文件 |
