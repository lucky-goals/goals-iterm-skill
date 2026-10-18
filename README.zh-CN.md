# goals-iterm-skill

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md)

让支持 skill 的 coding agent 通过 [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp) 指挥 iTerm2 中的 Claude Code、Codex 等 CLI，持续监控进度、提供决策建议并验收任务。

## 通过 coding agent 安装

将下面的提示词复制给可以访问本机文件系统的 coding agent，把 `[目标客户端]` 替换为需要安装 skill 的客户端。已有本地仓库时，也可以把仓库 URL 替换为本地绝对路径。

```text
请将 goals-iterm-skill 安装到 [目标客户端]。
仓库地址：https://github.com/lucky-goals/goals-iterm-skill

1. 检查目标客户端的现有配置和支持的 skill 安装机制，按照其文档确定安装位置
   与作用范围，不要猜测配置路径。
2. 获取仓库，或使用我指定的本地目录。检查 SKILL.md 及其引用文件；仓库根目录
   就是 skill 包。
3. 以 goals-iterm-skill 为目录名安装，保留 SKILL.md、references/ 和 agents/，
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

## 前置条件与手动安装

本仓库根目录就是一个 skill 包。通过宿主客户端支持的 skill 安装机制，将整个目录安装为 `goals-iterm-skill`，保留 `SKILL.md`、`references/` 和 `agents/`，确保相对引用有效。安装位置和重新加载步骤以目标客户端文档及现有配置为准。

本 skill 不会安装 MCP 或提供独立后台服务。使用前需在宿主中连接 goals-iterm-mcp，启用 iTerm2 Python API，并在目标终端准备好 CLI 及认证。所需工具至少覆盖会话枚举、屏幕/历史读取、文本/按键发送；新建终端还需对应创建工具。

持续监控依赖宿主提供的任务唤醒/调度，或 agent 当前执行中的轮询。没有后台唤醒能力的客户端不能在 agent 结束执行后继续自动监控。skill 会要求明确报告这一限制。

## 使用示例

```text
使用 goals-iterm-skill，在 iTerm 中让 Claude Code 修复 /path/to/project
的登录问题。先诊断再修复，只运行相关测试。每次发出指令后监控返回，
常规技术决策由你判断，确定网络错误已中断且不会自动续跑时恢复任务。
验收完成后停止监控并汇总改动、测试和剩余问题。不要发布。
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
- 你负责协调、监控、决策和验收，让目标 CLI 执行具体开发工作。
- 先检查会话状态；已有任务正在执行时直接接管监控，不重复派发。
- 每次发送任务、补充指令、决策或恢复指令后，建立或更新同一个 monitor。
- 使用实际可用的宿主监控机制；没有后台唤醒能力时，在当前执行中持续轮询，
  并如实说明限制，不能只承诺“稍后检查”。
- 常规技术决策结合上下文和项目约定自主判断，像 advisor 一样指导 CLI 继续。
- CLI 正在运行或自动重试时继续观察，不重复发送任务。
- 只有确认任务已经中断且不会自动继续时，才核对已完成工作并有限恢复。
- 不要把阶段汇报、空闲输入框或 CLI 自称完成当成整个任务完成。
- 缺少验收证据时继续要求补充；满足全部验收条件后，停止 monitor，
  将 Goal 标记为完成，并汇总改动、验证结果和剩余问题。

约束：
- 遵守项目 AGENTS.md。
- 只执行相关的定向测试，非必要不跑全量测试。
- 启动 Python 进程不使用 --reload。
- 本次不授权发布、推送或破坏性操作。
- 遇到必须由我决定的问题时，提供具体问题、建议和所需操作；
  保留上下文并停止相关自动写入。
```

## 维护与验证

入口是 [SKILL.md](SKILL.md)，工具语义见 [iterm-tools.md](references/iterm-tools.md)，监控、恢复及行为验收场景见 [monitoring.md](references/monitoring.md)。这些指令文件目前使用简体中文。工具约定依据 cc-iterm-mcp 的 `src/goals_iterm_mcp/direct.py`；运行时以实际安装版本 schema 为准。

更改后校验 skill frontmatter 与相对引用，并推演监控协议末尾的场景。真实 CLI 验证应使用专用测试会话，确认任务派发、决策、恢复及监控清理；静态校验不代表后台调度或真实 CLI 集成已通过。
