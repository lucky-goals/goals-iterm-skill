# goals-iterm-skill

Skill 版本: [v0.2.2](https://github.com/lucky-goals/goals-iterm-skill/releases/tag/v0.2.2)

[项目官网](https://lucky-goals.github.io/goals-iterm-skill/zh/)
[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

让支持 skill 的 coding agent 通过 [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp) 指挥 iTerm2 中的 Claude Code、Codex 等 CLI，持续监控进度、提供决策建议并验收任务。

内联监控时，协调者在每次等待前输出简短旁白：根据最新证据说明当前任务在做什么、本次等待什么、多久后再检查，以及后续待办。阶段变化或出现阻碍时及时汇报；没有新输出则如实说明，不编造百分比或完成时间。旁白发给用户，不发送给被控 CLI；后台监控无变化时仍保持安静。详见[进度旁白协议](references/monitoring.md#内联等待的进度旁白)。

## 必需的 MCP：goals-iterm-mcp

本 skill 使用 **[lucky-goals/goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp)** 操作 iTerm2。请先在**负责协调的 agent 客户端**中安装并连接该 MCP，再安装本 skill，最后使用下方任务提示词。仅安装 skill 不会提供终端工具。已有 MCP 连接时验证即可，不必重复安装。

准备顺序：

1. 在运行终端的 Mac 上安装并打开 iTerm2，在 **Settings → General → Magic → Python API** 中启用 API，并在出现授权弹窗时批准连接。
2. 将 goals-iterm-mcp 配置为协调客户端的本地 stdio 服务。客户端需要能访问该 Mac；纯云端聊天无法直接操作本机 iTerm2。
3. 在 iTerm2 中安装并完成 Claude Code、Codex 或其他目标 CLI 的认证，确认新标签页中也能正常启动。不要把凭据写进提示词。
4. 验证 MCP 工具发现及只读的 `list_sessions` 调用，再安装本 skill。执行任务需要写入工具；`--read-only` 服务只能观察。

完整步骤和版本更新见 [MCP 安装指南](https://github.com/lucky-goals/goals-iterm-mcp/blob/main/README.zh-CN.md)。以下示例固定使用其文档中的 `0.1.2`，不表示后续版本不兼容。

```text
请在本机 Mac 上为 [目标客户端] 安装 goals-iterm-mcp。
仓库地址：https://github.com/lucky-goals/goals-iterm-mcp

1. 阅读项目安装指南，检查 macOS、iTerm2 和 uv/uvx。
   如果缺少 uv，按照 uv 官方说明安装。
2. 使用 Python 3.12 验证包可运行：
   uvx --python 3.12 goals-iterm-mcp@0.1.2 --help
3. 备份客户端现有 MCP 配置，添加或更新一个名为 iterm 的本地 stdio 服务，
   保留无关设置并避免重复配置：
   command：本机 uvx 的绝对路径
   args：["--python", "3.12", "goals-iterm-mcp@0.1.2", "serve"]
   使用目标客户端支持的配置格式和位置。
4. 如有需要，指导我开启 iTerm2 Python API 并批准授权弹窗。
   按支持的方式重新加载 MCP；需要手动重启时说明具体步骤。
5. 验证握手、工具发现及 list_sessions 即可。安装期间不要读取终端正文、发送输入、
   创建或关闭窗口，也不要启动 coding 任务。
6. 报告配置位置、固定版本和连接结果，区分独立服务连通与目标客户端实际加载工具。
   如有阻碍，说明剩余步骤；准备完成后继续按下文安装 skill。
```

`serve` 是由客户端通过 stdio 启动的 MCP 服务入口，不是 coding CLI。安装 MCP 不会提供 monitor，也不会替目标 CLI 配置认证。

## 通过 coding agent 安装

将下面的提示词复制给可以访问本机文件系统的 coding agent，把 `[目标客户端]` 替换为需要安装 skill 的客户端。已有本地仓库时，也可以把仓库 URL 替换为本地绝对路径。

```text
请将 goals-iterm-skill 安装到 [目标客户端]。
仓库地址：https://github.com/lucky-goals/goals-iterm-skill

1. 检查目标客户端的现有配置和支持的 skill 安装机制，按照其文档确定安装位置
   与作用范围，不要猜测配置路径。
2. 获取仓库，或使用我指定的本地目录。检查 SKILL.md 及其引用文件；仓库根目录
   就是 skill 包。
3. 以 goals-iterm-skill 为目录名安装，保留 SKILL.md、references/、agents/ 和 scripts/，
   不要只复制 SKILL.md。已有安装时先比较差异、保留本地修改并在更新前备份，
   不影响其他 skill。
4. 检查目标客户端是否已连接 goals-iterm-mcp。安装 skill 不等于安装 MCP 服务；
   若缺失，说明前置条件并提供配置指引，不要改动无关 MCP 配置。
5. 校验 skill 元数据与相对引用。按客户端支持的方式重新加载，若需手动操作，
   明确告诉我具体步骤；能够检查时，确认目标客户端实际发现了该 skill。
6. MCP 可用时，验证工具发现并仅用 list_sessions 检查连接。安装期间不要读取
   终端正文、发送输入、创建窗口或启动 coding 任务。
7. 报告安装路径、skill 发现状态、MCP 就绪情况，以及可用的监控模式：宿主调度/
   唤醒，或 agent 当前执行中的轮询。没有实际唤醒机制时，不要宣称支持后台监控。
```

## 更新已安装的旧版本

已安装用户可以把下面的提示词交给 coding agent。“最新版本”默认指远程默认分支上最新的已提交内容；需要固定版本时，请指定 tag 或提交 SHA。更新本地源码仓库不会自动更新通过复制安装的 skill；升级 `goals-iterm-mcp` 的 PyPI 包也不会更新 skill。

```text
请将 [目标客户端] 中已安装的 goals-iterm-skill 更新到最新版本。
仓库地址：https://github.com/lucky-goals/goals-iterm-skill
（如需固定版本，在这里指定 tag 或提交 SHA。）

1. 找到目标客户端实际加载的 skill 路径和作用范围，确认它是 Git 仓库、符号链接、
   复制目录还是由客户端管理的安装。记录当前提交或文件状态；无法确定旧版本时标未知。
   检查本地修改与重复安装，不猜测路径，不另装一份导致覆盖优先级混乱。
2. 在客户端不会扫描为 skill 的位置，备份完整安装目录与本地修改，记录备份路径。
   符号链接需备份实际目标内容。保留审计台账、运行时记录、用户自定义文件和其他 skill。
3. 获取上游，确认远程默认分支及其最新提交；若我指定了 tag/SHA，以指定版本为准。
   记录目标提交 SHA，不把本地旧 checkout 或未提交改动称为上游最新版。
4. 对干净且跟踪目标分支的 Git 安装，仅做 fast-forward 更新。遇到本地修改、分叉、
   detached HEAD 或分支不符时，不 reset、不强行切分支或丢弃修改；在临时目录准备
   上游版本，比较并保留/合并自定义内容，无法兼容的冲突明确说明。
   符号链接更新其真实目标；复制安装同步完整包（SKILL.md、references/、agents/、scripts/ 等）；
   客户端管理的安装使用其支持的更新机制。不要只替换 SKILL.md；确认属于旧包且已废弃的
   文件在备份后移除，未知文件保留，避免新旧引用混用。
5. 校验元数据、相对引用及安装内容与目标版本的对应关系。按客户端支持的方式重新加载；
   需重启或新建会话时说明具体步骤。能够检查时确认客户端实际发现更新后的 skill，
   不把文件已复制等同于当前会话已经重新加载。
6. 单独检查 MCP 工具发现；必要时只用 list_sessions 验证连接。若缺少新工具，说明 MCP
   需要另行升级/重新加载，不擅自更改其固定版本或无关配置。更新 skill 期间不要读取
   终端正文、发送输入、创建/关闭会话或启动任务。
7. 报告安装与备份路径、更新前后版本/提交、保留的本地修改、验证结果、待完成的重新加载
   及回滚步骤。没有独立版本号时使用提交 SHA；无法确认已加载时如实说明。
```

手动更新时，先定位安装类型并备份。对干净且已跟踪目标分支的 Git 安装，在该目录先 `git fetch origin`，核对目标后执行 `git pull --ff-only`；若不能快进，先处理差异，不强制覆盖。复制安装则在临时目录获取目标提交，比较后同步整个 skill 包，核对旧包废弃文件，再重新加载客户端。通过符号链接安装时操作链接目标。需要回滚时，先保留更新后产生的修改，再恢复备份并重新加载；回滚 skill 不会回滚 MCP 或已执行的终端任务。

## 前置条件与手动安装

本仓库根目录就是一个 skill 包。通过宿主客户端支持的 skill 安装机制，将整个目录安装为 `goals-iterm-skill`，保留 `SKILL.md`、`references/`、`agents/` 和 `scripts/`，确保相对引用有效；`scripts/` 包含会话注册表使用的标准库辅助脚本。安装位置和重新加载步骤以目标客户端文档及现有配置为准。

本 skill 不会安装 MCP 或提供独立后台服务。使用前需在宿主中连接 goals-iterm-mcp，启用 iTerm2 Python API，并在目标终端准备好 CLI 及认证。所需工具至少覆盖会话枚举、屏幕/历史读取、文本/按键发送；新建终端还需对应创建工具。

持续监控依赖宿主提供的任务唤醒/调度，或 agent 当前执行中的轮询。没有后台唤醒能力的客户端不能在 agent 结束执行后继续自动监控。skill 会要求明确报告这一限制。

### 会话生命周期与持久协调状态

开始新 CLI 工作或交接任务前，请遵循[会话生命周期指南](references/session-lifecycle.md)。启动新的 CLI 进程或会话前，先检查已安装 MCP 实际提供的清理与恢复能力。CLI 启动后、派发新工作前，核对对话持久化状态以及当前 Session/Tab/Window 身份。如果 transcript 或历史记录被禁用，必须先通过该 CLI 支持且已验证的启动方式修复，再发送新工作；不要为了修改设置而重启已经活跃的会话。CLI 身份或恢复回执本身不证明历史已经持久化或可恢复。恢复状态未知时，要记录明确且可执行的人工后续步骤，绝不承诺自动关闭。

协调者在 `~/.local/state/goals-iterm-skill/session-registry.json` 维护持久化本地注册表。使用随包提供的标准库辅助脚本 `scripts/session_registry.py` 实现锁、revision 和 generation 防护。注册表记录的是宿主观察结果，不是 MCP 的权威，也不是对真实终端的锁。只有跨任务 handoff/复用才会使旧的完成状态失效；同一任务仅更换协调者时，保留已记录的业务和清理事实（包括 unknown 结果），同时由 generation 防护阻止过期写入。重命名 CLI 聊天不产生新的身份。每个会话的任务验收后，将其置为 `finalizing`：停止负责业务写入的 monitor，但继续运行清理协调，直到每个所属资源实际为 `closed`、明确 `retained`，或 `blocked` 且有可执行的处置方案。任何 `unknown` 清理结果都要保持可见，并先通过只读观察对账后再改变。子任务在没有消费者需要后，可以独立验收或回收。

清理复核必须有界，只有存在实际调度器且获得授权时才能重试。写操作结果未知时，只能通过只读观察进行对账。默认不得使用 `force` 或全局清扫。最终回复必须包含资源核算总数及原因、恢复证据和待处理后续事项。

## 显式清理会话

当前 MCP 源码已实现四个清理工具。只有当已安装的服务公开相应 schema 时才使用；运行时以实际安装工具的 schema 为准。本节说明当前实现，不表示某个软件包已发布，也不涉及版本变更。

- `close_session(session_id OR nickname, force=false, dry_run=false)` 关闭一个会话。
- `close_tab(tab_id OR session_id OR nickname, force=false, dry_run=false)` 关闭一个标签页。
- `close_window(window_id OR session_id OR nickname, force=false, dry_run=false)` 关闭一个窗口。
- `clean_all_sessions(force=false, dry_run=false)` 清理服务器授权范围内的会话。

前三个工具必须且只能提供一个定位参数。ID 必须精确匹配。昵称会先去除首尾空白并进行大小写折叠，再精确匹配一个 Session；对标签页/窗口工具，它选择该 Session 所在的容器，不会把昵称直接当作 Tab。匹配有歧义时拒绝。默认情况下，`clean_all_sessions` 只关闭已确认空闲的会话，跳过忙碌、等待、未知或其他无法确认安全的会话。它不会推断会话“无需保留”或是否有用；负责协调的 agent 必须遵守用户要求的保留策略和授权范围。`force=true` 会尝试初始授权范围内的所有会话（包括忙碌会话），但仍执行 ID、权限、目标变化和恢复安全检查。普通关闭在预检发现受影响的 Session/Tab/Window 中有忙碌或未知会话时，会整体拒绝，除非已授权 force。

任何中断、CLI 退出或原生关闭之前，服务都必须先持久化私有恢复回执，其中记录目标以及可获得的 CLI/chat UUID、cwd 和恢复元数据；初始回执写入失败会在终端写入前停止操作；后续回执更新失败时可能已有副作用，需核对逐会话结果。随后请求 CLI 优雅退出，并仅在确认退出后关闭目标。`dry_run=true` 真正只读：不发送终端输入、不保存恢复回执、不改名、不中断、不关闭。

每个会话结果都使用公开字段 `interruption`、`exit`、`closure_status` 和 `cli_sessions`；聊天记录可能包含 `cli`、`chat_uuid`、`cwd`、身份来源、持久化状态和恢复数据。有回执时，操作会返回 `recovery_record_id` 和 `recovery_record_path`。CLI 历史的 `persistence_status` 为空或未知本身不构成阻碍。UUID 身份证据和恢复回执安全保护，与历史是否实际持久化、能否恢复是不同层次；单有 ID 不保证可恢复。即使 MCP 响应的 `isError=true`，也要读取其中的 `status` 以及 `closed_sessions`、`skipped_sessions`、`failed_sessions`、`unknown_sessions` 数组。

### 自动回收任务拥有的资源

验收条件已经核实通过、监控已经停止后，默认自动回收专为本任务创建的资源。关闭工具内部会先持久化恢复回执，再退出 CLI 或关闭终端。CLI 声称“done”不等于验收证据。既有的借用会话和窗口默认保留，除非明确将其纳入本任务并取得清理授权。用户要求保持打开时，优先保留该资源。

在创建或明确采用资源时，记录来源、拥有该资源的任务，以及准确的 Session、Tab、Window ID。选择最大且安全、互不重叠的任务拥有容器：只有当窗口当前所有后代都属于本任务且已完成并符合回收条件时，才使用任务独占 Window；否则使用任务独占 Tab；再否则只关闭各个任务拥有且符合条件的 Session。仅为空或看起来独占，不能证明容器归属。保留未获清理授权的借用父级，以及共享或未知窗格。allowlist 不完整、无法证明容器归属时，使用精确的 Session。

自动回收先以 `dry_run=true` 预演，再复核成员，使用 `force=false` 调用 `close_window`、`close_tab` 或 `close_session`，绝不调用全局的 `clean_all_sessions`。预检发现目标忙碌或未知、身份缺失或初始恢复回执错误时，保留资源并报告。执行开始后的错误可能已有副作用，应核实实际结果，不能声称终端必然保留；不要自动使用 force，也不要盲目重试。用户明确授权 force 的流程仍单独按手动清理流程处理。

将业务任务完成与清理结果分开记录。审计记录应写入每个会话的 CLI/chat UUID、cwd、恢复元数据、恢复回执和清理结果。暂停、失败或取消的任务不自动回收。现有监控和审计流程继续有效，实际安装工具的 schema 仍是运行时依据。借用资源、全局清理和 force 清理仍需明确授权；复用已有授权，不要重复询问。`clean_all_sessions` 可能影响无关任务，因此只有在已授权范围与服务器范围一致时才调用（包括已配置的 allowlist）。详细流程见[自动回收与恢复指南](references/automatic-cleanup.md)和[关闭与恢复指南](references/closing-and-recovery.md)。

## 使用示例

```text
使用 goals-iterm-skill，在 iTerm 中让 Claude Code 修复 /path/to/project
的登录问题。先诊断再修复，只运行相关测试。每次发出指令后监控返回，
常规技术决策由你判断，确定网络错误已中断且不会自动续跑时恢复任务。
验收完成后停止负责业务写入的 monitor，并完成已授权的收尾，直到所属资源已关闭、明确保留，
或已阻塞并记录可执行的处置方案。汇总改动、测试、资源核算总数及原因、恢复证据和待处理后续事项。
不要发布。
```

也可以指定已有会话昵称接管任务。skill 将先枚举并绑定准确的 `session_id`，避免重复派发仍在运行的任务。

## 高级示例：使用 Goal 持续推进整个任务

对于多阶段任务，如果宿主支持 Goal，建议在负责协调的 Codex 聊天中设置 Goal。iTerm 内的执行 CLI 不必另设 Goal。Goal 记录整体目标，skill 指导协调流程，monitor 负责观察终端返回。Goal 不能替代 monitor，也不提供独立后台服务。参见 [官方 Goals 指南](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)。

替换下面的占位内容，将提示词发送给负责协调的 Codex。宿主不支持 Goal 时，可以删去创建和完成 Goal 的要求，保留监控与验收要求。

```text
请创建并启动一个 Codex Goal，使用 $goals-iterm-skill，
通过 iTerm MCP 持续指挥终端中的 Coding CLI，直到以下任务通过验收。

项目目录：[绝对路径]
执行 CLI：[Claude Code / Codex CLI]
目标会话：[已有会话昵称或 ID；没有则创建专用会话]

任务目标：
[描述最终需要实现的结果]

验收条件：
1. [可检查的功能或行为]
2. [需要通过的相关测试]
3. [需要交付的文件、结果或说明]

执行要求：
- 全程同步维护 Markdown 审计台账，记录委托、CLI 返回及待决策事项、你的决定与依据、
  实际动作和结果；附时间、外层/CLI 轮次及关联事件编号。开始时告知路径，最终附台账链接。
- 你负责协调、监控、决策和验收，让目标 CLI 执行具体开发工作。
- 先检查会话状态；已有任务正在执行时直接接管监控，不重复派发。
- 每次发送任务、补充指令、决策或恢复指令后，建立或更新同一个 monitor。
- 使用实际可用的宿主监控机制；没有后台唤醒能力时，在当前执行中持续轮询，
  并如实说明限制，不能只承诺“稍后检查”。
- 常规技术决策结合上下文和项目约定自主判断，像 advisor 一样指导 CLI 继续。
- CLI 正在运行或自动重试时继续观察，不重复发送任务。
- 只有确认任务已经中断且不会自动继续时，才核对已完成工作并有限恢复。
- 不要把阶段汇报、空闲输入框或 CLI 自称完成当成整个任务完成。
- 缺少验收证据时继续要求补充；满足全部验收条件后，停止负责业务写入的 monitor，
  只完成已授权的收尾：继续协调清理，并将每个所属资源记录为已关闭、明确保留、已阻塞且
  有可执行处置方案，或 unknown。unknown 必须通过只读观察对账，不能隐藏。只有在没有任何
  必要工作未完成时，才能将 Goal 标记为完成。如果必要工作或清理确实受阻，应如实报告宿主
  当前状态和所需动作，遵守宿主的状态转换规则；不要强行立即标记 blocked，也不要承诺无限期
  保持 Goal 开放。汇总改动、验证结果、资源核算总数及原因、恢复证据和待处理后续事项。没有
  消费者需要时，子任务可以独立验收或回收。

约束：
- 遵守项目 AGENTS.md。
- 只执行相关的定向测试，非必要不跑全量测试。
- 启动 Python 进程不使用 --reload。
- 本次不授权发布、推送或破坏性操作。
- 遇到必须由我决定的问题时，提供具体问题、建议和所需操作；
  保留上下文并停止相关自动写入。
```

## 任务审计台账

每个委托任务都会在执行过程中同步维护一份 Markdown 审计台账。协调者记录委托指令、CLI 返回（含待决策问题和选项）、决策及依据、投递证据、异常恢复、验收结果和监控清理。每条包含带 UTC 偏移的时间、外层对话轮次、各会话的 CLI 轮次，以及关联事件/决策编号。外层轮次是任务内的用户消息计数，不冒充宿主原生聊天 ID。

协调者在开始时告知台账绝对路径，结束时附链接。可指定保存路径；默认使用宿主私有状态目录，无此目录时使用 `~/.local/state/goals-iterm-skill/audits/`，不会自动提交到项目仓库。敏感内容先脱敏，无变化轮询可以合并，但关键反馈和决策必须保留。这是以追加为主的操作记录，不是防篡改日志或完整终端录制。

详见 [审计协议](references/audit.md) 和 [Markdown 模板](references/audit-template.md)。发送前记录意图，发送后追加真实投递结果。写账失败时会报告缺口并暂停新的自动工作指令，不能在没有审计记录的情况下静默继续。

## 维护与验证

入口是 [SKILL.md](SKILL.md)，工具语义见 [iterm-tools.md](references/iterm-tools.md)，监控、恢复及行为验收场景见 [monitoring.md](references/monitoring.md)，清理恢复细节见 [closing-and-recovery.md](references/closing-and-recovery.md)。这些指令文件目前使用简体中文。工具约定依据 cc-iterm-mcp 的 `src/goals_iterm_mcp/direct.py`；运行时以实际安装版本 schema 为准。

更改后校验 skill frontmatter 与相对引用，并推演监控协议末尾的场景。真实 CLI 验证应使用专用测试会话，确认任务派发、决策、恢复及监控清理；静态校验不代表后台调度或真实 CLI 集成已通过。

## 贡献与支持

欢迎提交问题报告、流程改进和翻译。提交 PR 前请阅读 [贡献指南](CONTRIBUTING.md)，可复现的问题和建议请通过 [Issues](https://github.com/lucky-goals/goals-iterm-skill/issues) 提交。安全漏洞请按照 [安全政策](SECURITY.md) 私下报告，不要公开终端日志。贡献与安全文档目前使用英文。

## 许可证

[MIT 许可证](LICENSE)，版权归 2026 lucky-goals 所有。
