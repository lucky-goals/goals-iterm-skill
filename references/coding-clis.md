# Coding CLI Playbooks

Use this reference when launching, continuing, resuming, falling back, or normally exiting a Coding CLI in iTerm2 through `goals-iterm-mcp`. It maps user or host scenario rules (such as `<cli-or-alias> + <model> + <effort> + <permission/bypass>`) onto each CLI's actual flags, environment variables, session-persistence behavior, and clean-exit commands so user rules stay concise without repeating per-CLI startup boilerplate.

## 1. Scenario shorthand, shell wrappers, quoting, and fallbacks

1. **Translate shorthand per CLI family—never invent cross-CLI flags:** Host rules and user prompts commonly express scenario routing as `<cli-or-alias> + <model> + <effort> + <permission/bypass>` (plus optional fallback chains). Look up the target CLI family below instead of passing `--model`, `--effort`, or `--dangerously-skip-permissions` blindly to CLIs that do not accept them.
2. **Launch inside a login shell so aliases and wrappers resolve:** Always omit `command` on `create_window` / `create_tab` so `~/.zshrc` loads before launching the CLI. Shell aliases or provider wrappers (for example `ccds` or `ccgw` wrapping Claude Code with custom endpoints/models) then work natively. If an unfamiliar wrapper is requested, verify its CLI family read-only (`<alias> --help`, never printing secret environment variables or tokens) before constructing flags; `goals-iterm-mcp` process inspection will report the underlying executable (for example `"claude"`).
3. **Single-quote bracketed or parameterized model specs in `zsh`:** Square brackets in model specs (such as `'deepseek-flash[1m]'` or `'claude-opus-4-8[context=1m,effort=high]'`) trigger `zsh: no matches found` globbing failures when unquoted. Always single-quote them, and normalize human-readable shorthand (for example `sonnet 5.5` or `opus 5.5`) to a single quoted slug/alias supported by that CLI (checking `--list-models` / `--help` / `/model` read-only if needed) so spaces never split into unexpected prompt arguments.
4. **Apply permission / `bypass` flags only within active authorization:** Map `bypass` to a CLI's unattended/full-permission flags **only** when the user prompt or active host/project rules explicitly authorize `bypass`. Otherwise use workspace-scoped or interactive approval modes. Never paste API keys or credentials into terminal commands, decision files, registry state, or audit ledgers.
5. **Execute declared fallback chains (`fallback to ...` / `故障可降级为 ...`) cleanly:** Switch to a fallback CLI + model only after observing a concrete startup, authentication, quota/rate-limit, model-availability, or unrecoverable transport failure. Before starting the fallback CLI in the same pane, confirm the failed CLI has exited back to the shell, update `session_registry.py` with a generation advance (`cli`, cleared stale `chat_uuid`) per [session-lifecycle.md](session-lifecycle.md), and record both the failure evidence and fallback target in the audit ledger.

## 2. Quick comparison across supported Coding CLIs

| CLI family | Launch command | Model selection | Reasoning effort | Authorized `bypass` mapping | Canonical MCP resume | Passive MCP identity (`cli_recovery`) | Normal exit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **[Claude Code](#claude-code)** (`claude`, plus wrappers e.g. `ccds`, `ccgw`) | `claude` (or wrapper alias) | `--model '<model>'` | `--effort <low\|medium\|high\|xhigh\|max>` | `--dangerously-skip-permissions` (or `--permission-mode bypassPermissions`) | `claude --resume <uuid>` (or `<alias> --resume <uuid>`) | Open `~/.claude/projects/.../<uuid>.jsonl` | `/exit` or `/quit`, then shell `exit` |
| **[Codex CLI](#codex-cli)** (`codex`) | `codex` (TUI) or `codex exec` (one-shot) | `-m '<model>'` (`--model`) | `-c 'model_reasoning_effort="<low\|medium\|high\|xhigh>"'` (or `/effort` in TUI) | `--dangerously-bypass-approvals-and-sandbox` (or `-s workspace-write -a never`) | `codex resume <uuid>` | Open `~/.codex/sessions/.../rollout-<uuid>.jsonl[.zst]` | `/exit` or `/quit` (TUI); `codex exec` returns to shell |
| **[Cursor Agent](#cursor-agent)** (`cursor-agent` / `agent`; rule shorthand `cursor`) | `cursor-agent` (never bare GUI `cursor`) | `--model '<model>'` (supports `'slug[effort=high,...]'`) | Encoded in `--model` slug (e.g. `...-xhigh`) or bracket override (`effort=...`); no `--effort` flag | `--yolo` (or `-f`) + `--trust` (`--approve-mcps` if MCP needed) | `cursor-agent --resume <uuid>` | Open `cursor-agent-logs-.../session-*.log` (`conversationClassification.init`) | `/exit` or `/quit`, then shell `exit` |
| **[Kiro CLI](#kiro-cli)** (`kiro-cli` / `kiro`) | `kiro-cli chat` | `--model '<model>'` | `--effort <low\|medium\|high\|xhigh\|max>` | `-a` (`--trust-all-tools`) + `--trust-workspace` | `kiro-cli chat --resume-id <uuid>` | No passive foreground PID-to-UUID proof (`CLI_IDENTITY_MISSING` unless registered) | `/quit` or `/exit`, then shell `exit` |
| **[DSH TUI](#dsh-and-dsh-tui)** (`dsh-tui` / `dst` / `dsh --profile dsh-tui`) | `dsh-tui` or `dst` | `--patch <overlay.yml>` (`agent-default-model`) or `/model` in TUI (no `--model` flag) | `--patch <overlay.yml>` (`off\|low\|high\|max`) or `/effort` in TUI (no `--effort` flag) | Prefix `DSH_PERMISSION_MODE=danger-full-access` | `dsh-tui --resume <id>` (or `dsh --profile <p> --resume <id>`) | Open root `$DSH_HOME/sessions/<proj>/<id>/session.lock` (subagent locks excluded) | `/exit`, `/quit`, or `/q`, then shell `exit` |
| **[DSH Headless](#dsh-and-dsh-tui)** (`dsh headless`) | `dsh headless --json ...` | `--patch <overlay.yml>` (`agent-default-model`; no `--model` flag) | `--patch <overlay.yml>` (`off\|low\|high\|max`; no `--effort` flag) | `--permission-mode danger-full-access --approval-policy never` (`--add-dir <dir>`) | `dsh headless --session-id <id>` (same `cwd`) | Line-1 JSON `sessionId` + open root `session.lock` while running | Returns directly to shell; run shell `exit` |

---

## 3. Per-CLI operational playbooks

<a id="claude-code"></a>
### 3.1 Claude Code (`claude` and wrappers such as `ccds`, `ccgw`)

- **Startup & flags:**
  - Interactive launch template: `<claude-or-alias> --model '<model>' --effort <low|medium|high|xhigh|max> [--dangerously-skip-permissions] [--add-dir <dir>]`.
  - When narrower permissions are authorized instead of full `bypass`, prefer `--permission-mode acceptEdits` or `--permission-mode auto`.
  - Do **not** pass `--no-session-persistence` (disables history saving) or `--bare` (skips `CLAUDE.md` discovery, keychain/OAuth, hooks, and MCP sync) unless the user explicitly requests an isolated ephemeral run.
  - Always single-quote bracketed model names such as `'deepseek-flash[1m]'`.
- **Continuation, identity & recovery:**
  - Interactive TUI stays open across rounds; send complex prompts via [file dispatch](dispatch.md) (granting `--add-dir` if the decision file sits outside allowed roots under strict sandbox settings).
  - `goals-iterm-mcp` verifies the active UUID from the open `~/.claude/projects/.../<uuid>.jsonl` file; a fresh empty session has no transcript until its first turn (`CLI_IDENTITY_MISSING`), and `--resume` / `--session-id` on argv alone before file open reports `CLI_IDENTITY_STARTUP_ONLY`.
  - When restoring a session originally launched via a provider wrapper alias (such as `ccds` or `ccgw`), preserve that wrapper name in the audit ledger so resumption uses the matching provider environment (`<alias> --resume <uuid>`), while noting that MCP receipts record `resume.executable = "claude"`.
- **Normal exit:** Send `/exit` or `/quit`, confirm return to the idle shell, then run shell `exit` when terminal cleanup is authorized.

<a id="codex-cli"></a>
### 3.2 Codex CLI (`codex`)

- **Startup & flags:**
  - Interactive TUI template: `codex -m '<model>' [-c 'model_reasoning_effort="<low|medium|high|xhigh>"'] [--dangerously-bypass-approvals-and-sandbox] [--add-dir <dir>]`.
  - If full sandbox bypass is **not** authorized, use `-s workspace-write -a on-request` (or `-s workspace-write -a never` for unattended workspace-bounded execution).
  - Non-interactive one-shot mode (`codex exec ...`) prints output and exits back to the shell after the turn; prefer interactive `codex` when coordinating multi-round tasks unless one-shot execution was requested.
- **Continuation, identity & recovery:**
  - `goals-iterm-mcp` verifies the active UUID from an open `rollout-<uuid>.jsonl` / `rollout-<uuid>.jsonl.zst` file under `~/.codex/sessions/...`.
  - Resume a closed session in the project `cwd` via `codex resume <uuid>`.
- **Normal exit:** Send `/exit` or `/quit` in interactive TUI mode, confirm shell return, then exit the authorized idle shell (`exit`). For `codex exec`, verify shell return directly without sending slash commands to zsh/bash.

<a id="cursor-agent"></a>
### 3.3 Cursor Agent (`cursor-agent` / `agent`, rule shorthand `cursor`)

- **Critical binary disambiguation (`cursor-agent` vs `cursor`):**
  - When user or IDE rules specify `cursor` for a terminal task (for example `cursor + grok-4.7-xhigh + xhigh effort + bypass`), launch **`cursor-agent`** (or `cursor agent` / `agent`). Never run bare `cursor <flags>`, which targets the desktop GUI editor and either opens a GUI window or exits with `No Cursor IDE installation found. Use 'cursor agent' or 'agent' to run the agent`.
- **Startup, model, effort & `bypass` flags:**
  - Interactive launch template: `cursor-agent --model '<model>' [--yolo] [--trust] [--approve-mcps] [--add-dir <dir>]`.
  - **No standalone `--effort` flag:** Cursor Agent encodes effort either in the model slug itself (for example `grok-4.7-xhigh`, `sonnet-4-thinking`) or via quoted bracket overrides on `--model` (for example `--model 'claude-opus-4-8[context=1m,effort=high,fast=false]'`). If a requested model + effort combination is uncertain, run `cursor-agent --list-models` read-only in the ready shell first.
  - **Authorized `bypass` mapping:** Pass `--yolo` (alias of `-f` / `--force`) plus `--trust` so unattended runs do not stall on workspace-trust prompts; add `--approve-mcps` when MCP servers in that project are authorized for unattended use.
  - For read-only research/planning subtasks where edits are forbidden, consider `--plan` (`--mode plan`) or `--mode ask`.
- **Continuation, identity & recovery:**
  - `goals-iterm-mcp` passively verifies the active conversation UUID only when the PID holds an open log file under `cursor-agent-logs-.../session-*.log` containing `conversationClassification.init`; `--resume <uuid>` on argv alone stays `CLI_IDENTITY_STARTUP_ONLY`.
  - Resume a closed conversation via `cursor-agent --resume <uuid>`.
- **Normal exit:** Send `/exit` or `/quit`, confirm return to the shell, then run shell `exit` when authorized.

<a id="kiro-cli"></a>
### 3.4 Kiro CLI (`kiro-cli` / `kiro`)

- **Startup, model, effort & `bypass` flags:**
  - Interactive launch template: `kiro-cli chat --model '<model>' --effort <low|medium|high|xhigh|max> [-a] [--trust-workspace]`.
  - Normalize multi-word model descriptions in user rules (such as `sonnet 5.5` or `opus 5.5`) to the exact model identifier accepted by the installed `kiro-cli` (check `/model` or `kiro-cli chat --help` read-only if rejected; never pass unquoted spaces after `--model`, or the second word becomes an unintended initial prompt!).
  - **Authorized `bypass` mapping:** Pass `-a` (`--trust-all-tools`) together with `--trust-workspace` (skips the V3 `"Trust this workspace?"` interactive gate for this launch). When narrower tool permissions apply, use `--trust-tools=<tool1,tool2>`.
- **Continuation, identity & recovery limitations:**
  - Kiro's `kiro-cli chat --list-sessions` output and `--resume-id` launch flags do **not** passively bind a current conversation UUID to a live foreground PID (`goals-iterm-mcp` reports `CLI_IDENTITY_MISSING` or `CLI_IDENTITY_STARTUP_ONLY` and refuses signal-based `close_session` even with `force=true` when unbound).
  - Do **not** treat `CLI_IDENTITY_MISSING` on Kiro as an inability to finalize: after acceptance, always use [normal exit](natural-exit.md) (`/quit` or `/exit`), record any observed session ID/cwd in the ledger with `recovery_status=degraded` (or `unknown`), and then reclaim the idle shell normally (`exit`).
  - When a known session UUID is available for restoration, resume via `kiro-cli chat --resume-id <uuid>`.

<a id="dsh-and-dsh-tui"></a>
### 3.5 DeepSeek Harness (`dsh-tui` / `dst` and `dsh headless`)

- **Packages & modes:**
  - `dsh-tui` / `dst` (from `@deepseek-harness-tui/dsh-tui`, distinct from the unrelated unscoped `dsh-tui` web-client package; also bootable via `dsh --profile dsh-tui` once initialized): persistent interactive TUI in the pane.
  - `dsh headless` (from `@deepseek-ai/dsh`): one-shot execution per turn that prints output/events and exits back to the login shell upon completion.
  - `dsh web`, `dsh sdk`, `dsh sdk-minimal`, `dsh plugin`, `dsh setup`: server or utility subcommands—never drive or close them as single interactive chat sessions.
- **Startup, auth, model, effort & `bypass` mapping:**
  - **Forbidden flags:** Neither interactive `dsh-tui` nor `dsh headless` accepts `--model`, `--effort`, or `--dangerously-skip-permissions` on the command line (note: only `dst run` supports `--provider ID --model ID`). Never pass unsupported flags.
  - **Auth readiness:** Shipped `dsh headless` disables interactive OAuth/keyring auth plugins (`credentials`, `authorization`, `deepseek-account`) by default; verify `DEEPSEEK_API_KEY` (via shell environment, project `.env`, or `$DSH_HOME/.env`) or customized profile auth works before dispatching. Interactive `dsh-tui` additionally supports `/auth` and `/provider`.
  - **Authorized `bypass` mapping:**
    - For `dsh-tui` / `dst`: prefix the launch command in the login shell with `DSH_PERMISSION_MODE=danger-full-access` (inherited by `dsh-base` to set `sandbox-policy` to `danger-full-access` and `approval` to `never`), e.g. `DSH_PERMISSION_MODE=danger-full-access dsh-tui --patch <overlay.yml>`.
    - For `dsh headless`: pass `--permission-mode danger-full-access --approval-policy never` (or `--permission-mode workspace-write --approval-policy never` for workspace-only writes), plus `--add-dir <dir>` whenever the task must read host state files (such as decision files under `~/.local/state/goals-iterm-skill/`) or extra directories outside `cwd`.
  - **Model & `reasoningEffort` mapping:**
    - Built-in official DeepSeek model IDs are `deepseek-flash` (1M context, default) and `deepseek-v4-pro` (1M context); valid `reasoningEffort` values are `off`, `low`, `high`, and `max` (`dsh-tui` already defaults DeepSeek `thinking: enabled` + `reasoningEffort: max`).
    - When a rule or user prompt specifies a model and/or effort, write a small YAML overlay in private host state (never inside the project repository) and pass `--patch <overlay.yml>` at launch (`dsh-tui --patch <overlay.yml>` or `dsh headless --patch <overlay.yml> ...`), or switch inside a live `dsh-tui` session via `/model` and `/effort`:
      ```yaml
      - id: agent-default-model
        config:
          provider: deepseek-official
          model: deepseek-flash
          reasoningEffort: max
      ```
  - **Workspace instruction note:** DSH `@deepseek-ai/dsh-agent-instructions` automatically loads `$DSH_HOME/AGENTS.md`, `~/.agents/AGENTS.md`, and `AGENTS.md` / `CLAUDE.md` (plus `.local.md` overlays) along the project directory chain; it ignores paths containing `/` (such as `.trae/rules/...`).
- **Launching, capturing `sessionId`, and continuing rounds:**
  - **`dsh-tui` / `dst`:** Launch in the login shell, wait for the TUI input box (or Launchpad input) to settle, and dispatch multi-condition tasks via [file dispatch](dispatch.md). Only default DSH storage writes `$DSH_HOME/sessions/` (starting with `--backend claude` or `--backend codex` uses external backends).
  - **`dsh headless`:**
    - Always pass `--json` so line 1 deterministically emits `{"type":"session","sessionId":"..."}` (`session-<uuid>`, `<uuid>`, or safe custom ID). Immediately record `sessionId`, exact `cwd`, `cli="dsh"`, and resume spec (`dsh headless --session-id <id>`) in `session_registry.py` and the audit ledger.
    - Wait until `dsh headless` finishes and returns to an idle shell prompt before evaluating completion or sending `C02+`; never send bare follow-up prose to zsh/bash.
    - On round `C02+`, re-invoke `dsh headless --patch <overlay.yml> --session-id <sessionId> --json --permission-mode ... --approval-policy ...` from the **exact same `cwd`** (DSH scopes `--session-id` lookup by project `cwd` bucket and does not carry CLI policy flags across process invocations).
- **Recovery metadata, subagent locks & normal exit:**
  - `goals-iterm-mcp` detects Node-launched `dsh` / `dsh-tui` / `dst` without exposing command arguments, collapses single linear `dsh-tui` → `dsh` wrapper chains while keeping all wrapper PIDs in exit verification scope, and reads only line 1 of `$DSH_HOME/sessions/<proj>/<id>/session[.vN].jsonl[.zstd]` to ignore `origin: "subagent"` child locks while failing closed (`CLI_IDENTITY_AMBIGUOUS`) if multiple root sessions are open.
  - Between `dsh headless` turns, the pane hosts an idle shell (`cli_sessions=[]` in MCP diagnostics); rely on the `sessionId` and `cwd` recorded in the registry and ledger.
  - **Normal exit:** For `dsh-tui` / `dst`, send `/exit`, `/quit`, or `/q`, confirm return to the shell, then run shell `exit` when authorized. For `dsh headless`, the CLI has already returned to the shell—**never** send `/exit` to zsh/bash; verify no stray jobs remain and run shell `exit`.
