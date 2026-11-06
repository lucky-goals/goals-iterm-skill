# Standalone iTerm control inside Goals iTerm Skill

Status: implemented for the v0.4.0-dev GitHub prerelease / runtime 0.4.0.dev0; validation evidence below.
Date: 2026-11-06 (Asia/Shanghai).

## Objective and scope

Ship the terminal-control implementation with this skill so an agent can operate iTerm directly through local commands, without installing goals-iterm-mcp, running an MCP server, registering MCP tools, or editing a client's MCP configuration. Preserve all 13 existing public operations and the skill's orchestration, audit, acceptance, recovery, and cleanup behavior.

The skill remains instructions plus executable resources. Markdown alone cannot connect to iTerm. The agent needs local macOS command execution; a cloud-only host cannot control this Mac without an existing authorized local execution channel. Removing MCP does not remove the iTerm Python API, its authorization, or CLI-specific authentication requirements.

The implementation now bundles the terminal runtime, dependency preparation, diagnostics, versioned request contract, policy, and durable operation journal. The released v0.3.3 tag remains unchanged. Existing MCP configuration is retained. The v0.4.0-dev prerelease packages this standalone implementation, with the validation limits recorded below.

## Evidence and planning constraints

Inspected baselines:

- Skill v0.3.3, commit `5553a5a0425c7dc1160e3195896073f8422953bc`.
- MCP source v0.2.2, commit `66f4d82dfed12bba974149a795dea266e243dfc1` in the local `cc-iterm-mcp` checkout.
- MCP declares Python `>=3.12,<3.13`, `iterm2==2.30`, and `mcp==1.30.0` in pyproject.toml.
- Installed SDK metadata lists `protobuf` and `websockets` as base iterm2 dependencies; `pyobjc` is only in its `full` extra. Do not copy the entire MCP dependency lock into the skill.
- Local read-only inventory: Darwin arm64, iTerm 3.7.7 installed, uv 0.9.26 and Python 3.12.10 available, ps/lsof available. claude, codex, agy, kiro, and agent resolve in the host PATH. This does not verify CLI authentication, terminal PATH, API connectivity, or consent.

Design constraints and assumptions:

| Dimension | Basis |
| --- | --- |
| Scale | Same-machine coordination of a small number of terminals, consistent with the existing registry design; no distributed service requirement |
| Consistency | Writes must use fresh exact identities and current membership; uncertain delivery must never trigger automatic replay |
| Platform/stack | Existing macOS/iTerm and Python implementation; use Python 3.12 initially rather than widening support during migration |
| Latency | Existing monitor cadence is 10–15 seconds growing to 30–60 seconds; no user-specified p50/p99 target. Measure connection overhead before accepting the one-shot design |
| Cost/deployment | Assume no paid infrastructure or always-on service; distribute through the existing skill archive. Dependency downloads require network access during setup only |

If scale, latency, or remote-execution requirements differ, revisit the invocation architecture. No product decision currently blocks this planning phase. Runtime/API behavior still needs the dedicated spike below.

## Capability inventory

### What the skill already owns

| Capability | Existing implementation | Integration action |
| --- | --- | --- |
| Goal decomposition, delegation, routine decisions | SKILL.md, references/orchestrator.md | Retain host-agent responsibility; switch the authorized terminal channel to the bundled runner |
| Long instructions and decision files | references/dispatch.md | Preserve immutable files, single-line entry instruction, separate submission, and read evidence |
| Inline monitoring, bounded recovery, progress updates | references/monitoring.md | Keep real host waits and one writer; runner must not claim to wake an idle agent |
| User-authorized background monitoring | Host scheduler, when available | No new scheduling capability implied by integration |
| Acceptance and default task-owned cleanup | references/automatic-cleanup.md, natural-exit.md | Preserve normal CLI exit, verified idle shell exit, and independent disappearance checks |
| Ownership, generation, revision, handoff | scripts/session_registry.py | Retain schema v1 initially; registry stays an assertion store, not a source of live truth |
| Daily audit and recovery references | references/audit.md and audit-template.md | Keep a human-readable ledger; add runtime operation receipts for transport outcomes without conflating the two |
| Installation guidance | README editions | Replace MCP configuration instructions with bootstrap, doctor, runtime location, and upgrade/rollback steps |

### Complete terminal-operation parity target

Keep operation names and payload semantics stable while replacing the MCP envelope with a local versioned JSON contract.

| Operation | Required preserved behavior |
| --- | --- |
| list_sessions | Exact Session/Tab/Window identities, names and topology; no terminal body reading |
| inspect_sessions | Prompt/process/CLI evidence, activity, blockers, remediation and advisory readiness; never business acceptance or authorization |
| read_screen | Rendered lines, geometry/cursor, capture time and truncation |
| read_history | Retained history, position/wrapping/bounds, default 100 and maximum 2000 lines; retain transaction and stale-read protections |
| send_text | Exact 1–16384 UTF-8 bytes, no appended newline; suppress broadcast, no write retry |
| send_keys | Existing explicit key enum and exact Session selection; preserve program-dependent key semantics |
| create_window | Optional startup command, automatic unique name, returned identities |
| create_tab | Exact Window, optional command and returned identities; creation prohibited under a session allowlist |
| rename_session | Optional generated name, trimmed 1–64 characters, no controls or case-folded collisions |
| close_session | Exactly one ID/nickname selector; preflight, receipts, exit and independent closure verification |
| close_tab | Complete membership preflight; refusal if any member is out of scope; no silent partial preflight closure |
| close_window | Same guarantees across every current Tab/pane |
| clean_all_sessions | Explicit global-cleanup scope only; idle filtering, initial snapshot, partial outcomes, no new arrivals |

Normal exit and conversation restoration are existing skill workflows over primitive operations and CLI-specific commands, not additional current public MCP tools. Preserve this distinction. The current recovery adapter recognizes Claude Code, Codex, Cursor Agent, and Kiro; generic agy terminal control does not establish an agy recovery adapter. Do not claim new adapter support as a migration side effect.

## Source extraction map

| Source module | Disposition |
| --- | --- |
| direct.py: DirectItermBackend | Extract naming/create overrides into a transport-independent module; it currently shares a file with MCP imports |
| direct.py: ItermTools | Extract invocation, exact targeting, read/send/create/inspect logic into a service returning plain dictionaries |
| direct.py: build_server/run | Remove FastMCP decorators, annotations, ToolError, CallToolResult, and stdio transport from the standalone runtime |
| __main__.py | Replace the `serve` entry point with a finite local command dispatcher |
| backends.py, backend_types.py | Reuse topology, captures, transport lifecycle, broadcast suppression and bounded cleanup; review state assumptions |
| screen_coordinates.py, transaction_reads.py, shutdown.py | Preserve history transaction cancellation, stale-read checks and bounded disconnect; these are not MCP-specific |
| closing.py | Reuse CloseService and durable recovery receipts; migrate state paths explicitly |
| closing_backend.py | Reuse fresh preflight, native close and exit verification; refactor shell handling identified below |
| process_inspection.py | Reuse PID/start/TTY checks and self-protection; repair verified login-ancestor classification |
| cli_recovery.py | Reuse process-bound conversation discovery and restoration metadata; keep limitations explicit |
| naming.py, errors.py | Retain normalization and domain error codes |
| tests/ | Port relevant domain/backend tests; replace MCP schema tests with runner-contract and parity tests |

Retain the upstream MIT copyright/license notice and record the imported source commit. Do not import goals_iterm_mcp as an installed dependency or dynamically fetch upstream source during an operation. The source has roughly nine thousand runtime lines: this is extraction and adaptation, not a small wrapper around a few SDK calls.

## Architecture options and decision

| Option | Benefits | Costs and gaps | Decision |
| --- | --- | --- | --- |
| A. Bundled one-shot Python runner connecting directly to iTerm | No server installation or daemon lifecycle; easy to call from local agent execution; finite operations and isolated failures | Reconnect overhead; current in-memory locks/epochs cannot span calls; requires durable coordination | Recommended default, subject to P0 measurements |
| B. Skill-owned persistent local helper with a Unix socket | Persistent connection, epochs, and serialization; avoids reconnect overhead | Introduces socket permissions, process ownership, startup/cleanup, protocol/versioning and stale-daemon management | Fallback only if P0 demonstrates a concrete blocker; not an automatic daemon requirement |
| C. AppleScript/UI automation | May simplify a few basic operations | Does not reuse the robust Python history/identity/receipt machinery; fragile UI state and different permission surface | Reject as the primary transport |

Proposed path:

```text
Host agent using SKILL.md
  -> bundled itermctl launcher (local execution)
  -> versioned request validation + policy + operation journal/lock
  -> transport-independent service
  -> iTerm2 Python SDK/API
  -> exact Session -> shell / Coding CLI

Host separately owns: goals, decisions, waits, acceptance and audit ledger.
```

Official iTerm documentation supports direct Python scripting and finite `run_until_complete` execution. This supports the architecture direction, not proof that the extracted backend is already safe across repeated one-shot calls. See the P0 gate and sources below.

## Proposed package and command surface

The command surface is implemented. Read [the runtime contract](../references/runtime.md) for exact current schemas and required mutation preconditions; the tree below records the original package design.

```text
SKILL.md
agents/openai.yaml
scripts/
  bootstrap.sh              # initial entry, usable before Python is available
  itermctl                  # small launcher; use prepared runtime, no implicit downloads
  session_registry.py       # preserve existing helper
runtime/
  pyproject.toml
  requirements.lock         # hash-locked minimal runtime dependencies
  goals_iterm/
    cli.py                  # finite request dispatcher
    service.py              # transport-independent operations
    backend.py
    closing.py
    closing_backend.py
    process_inspection.py
    cli_recovery.py
    transactions.py
    policy.py
    operation_store.py
    doctor.py
references/
tests/
```

Keep modules logically separate; the illustrative tree does not require renaming stable upstream modules without a reason.

Example proposed calls:

```sh
/path/to/skill/scripts/bootstrap.sh --check
/path/to/skill/scripts/bootstrap.sh --apply
/path/to/skill/scripts/itermctl doctor --json
/path/to/skill/scripts/itermctl capabilities --json
/path/to/skill/scripts/itermctl invoke --request-file /private/path/request.json
/path/to/skill/scripts/itermctl operation-status --request-id unique-request-id
```

Example request:

```json
{
  "schema_version": 1,
  "request_id": "unique-request-id",
  "operation": "send_text",
  "arguments": {"session_id": "exact-enumerated-id", "text": "/exit"},
  "expected_observation": {"sessions": [{"session_id": "exact-enumerated-id", "tab_id": "observed-tab-id", "window_id": "observed-window-id"}]},
  "task_context": {"task_id": "task-1", "coordinator_id": "C1", "generation": 1, "expected_revision": 7}
}
```

This example is valid only after normal-exit eligibility is established for the actual CLI. Request JSON is data, never shell-evaluated. Prefer private files/stdin to putting prompts or secret-bearing values into argv. Accept only enumerated operations/fields, reject invalid selectors, booleans-as-strings, duplicate JSON keys, oversized input, and unsupported schema versions. Stdout contains one machine-readable result; diagnostics and SDK authorization messages go to stderr. Do not log credentials, raw environment, or full CLI command lines.

Preserve operation-specific result fields, especially per-session closing arrays, recovery paths, truncation and api_acknowledged/task_completion. Add a versioned envelope with request_id, status, code, data, warnings, and side-effect certainty. Define stable exit codes for success, refusal, unknown/partial outcome, and runtime failure. A nonzero exit code or parseable JSON alone does not determine whether a write occurred. `capabilities` reports implemented operations, runtime version and supported schema without needing iTerm; `doctor` reports live availability separately.

## Hard correctness problems to solve before switching

### Cross-process ownership and locking

ItermTools currently has an asyncio.Lock scoped to one server process. Use an owner-private cross-process lock for standalone terminal operations, separate from the registry lock. Begin with serialized operations for the current local scale; never hold the registry lock during a network wait. Recheck coordinator/generation/revision after acquiring the operation lock and immediately before writing. Other users/apps and an existing MCP server do not share this lock: refresh topology/identity and stop on changes. Locking is coordination, not protection against an unrestricted local user.

Keep read-only and session-allowlist restrictions in an explicit policy selected for the installation/task. An invocation cannot silently widen configured restrictions. Migrate old MCP restrictions deliberately rather than treating lack of MCP configuration as full access. Preserve container-wide scope checks, exact selectors, self/ancestor protection and no force bypass. User authorization remains separate from a JSON `force` field or task record.

### Epochs and reconnects

The backend generates broker_epoch and session_epoch in memory; they are not durable iTerm birth identities. Do not persist them as if they survive a new invocation or simply reuse one broker UUID forever. Each invocation must obtain a fresh catalogue and revalidate its own target through execution. Between invocations, retain original iTerm IDs, ownership generation, container membership, and available process-start/TTY evidence; treat cached epochs as historical. Define an expected-observation precondition that rejects replacement/membership conflicts without treating a normal CLI-to-shell transition as task takeover. Mark missing identity evidence unknown. P0 must verify the guarantees actually available after reconnect and application restart; do not silently downgrade protection for one-shot convenience.

### Unknown writes and crash recovery

Before mutations, durably reserve request_id and record bounded intent metadata. After completion, persist actual outcomes. Repeated IDs must not resend writes; return the known result or unknown if execution may have begun. A crash between iTerm acknowledgment and recording is inherently ambiguous. Reconcile using fresh reads/receipts; do not claim exactly-once delivery. Create and send are especially important: a lost creation response must not create another Tab on retry. Do not store sensitive input bodies in the operation journal by default. Keep legacy detailed closing recovery receipts separate from lightweight operation records.

Use finite connection/operation/disconnect deadlines. Preserve independent multi-step close deadlines instead of squeezing them into the ordinary 15-second wrapper. A timeout may kill the helper connection, not the user's CLI. Never kill task processes merely to enforce a helper deadline. Cancellation must flush known partial/unknown outcomes where possible and never trigger automatic replay.

### Normal exit and the observed shell-cleanup defect

Preserve the v0.3.3 sequence: verified native CLI exit -> verified idle shell `exit` -> enumerate disappearance -> guarded native close only for remaining containers. Do not assume `/exit` is a shell command or that a shell exit always removes a Tab.

In the inspected process census, the shell itself is excluded but an observed same-TTY `login` ancestor can still be counted as an active job. Exclude only structurally verified benign ancestors with stable identity, not every process named login or every same-TTY process. Preserve nested shells, real background/stopped jobs, unknown process states and detached descendants as blockers when appropriate. Missing prompt integration alone is neither busy nor idle. The runtime should expose sanitized job identity/classification evidence so the coordinator need not infer a false positive from active_job_count=1.

Do not use force/SIGINT as the normal empty-shell closing path. Preserve the distinction between interrupted work, CLI exit, shell exit, terminal disappearance and chat recoverability. Extend tests to cover signal delivery followed by verification failure, since a default not_attempted field must not imply no side effects.

## Dependency checking and preparation

### Installation contract

The skill archive contains runtime source, pinned dependency specification, bootstrap and doctor. It must not depend on the sibling MCP repository or goals-iterm-mcp package. Store mutable runtime environments outside the skill directory, for example:

```text
~/.local/share/goals-iterm-skill/runtimes/<runtime-version>-<lock-hash>/
~/.local/state/goals-iterm-skill/runtime.json
~/.local/state/goals-iterm-skill/operations/
~/.local/state/goals-iterm-skill/recovery/
~/.local/state/goals-iterm-skill/session-registry.json
```

Use absolute paths, private permissions, atomic manifests, and an installation lock. Key environments by version/lock hash so skill upgrades cannot accidentally load a different dependency set. Do not bundle a machine-specific venv in release archives. Keep the previous working environment for rollback and do not delete it while an operation uses it.

### Doctor matrix

| Check | Classification and response |
| --- | --- |
| macOS and local GUI access | Required; report unsupported host clearly, including a cloud/container with no local iTerm access |
| iTerm installed/version | Required; detect app metadata, distinguish installed from running and from reachable |
| Python 3.12 | Initial supported interpreter; locate exact path or prepare it via uv during authorized setup |
| uv | Preferred installer, not required during prepared operation; allow explicit existing-Python/venv fallback |
| iterm2 + protobuf + websockets | Required runtime; resolve and hash-lock transitive versions in a clean minimal environment |
| MCP/FastMCP | Must be absent from the new runtime's dependency/import graph; do not retain pydantic merely for MCP StrictBool |
| Python API enabled/authorized | Required for control; distinguish API disabled, app stopped, permission pending, timeout and transport failure |
| Shell Integration/prompt evidence | Recommended for stronger activity checks, not a hard prerequisite for all listing/reads; classify per-capability degradation |
| ps and lsof | Required evidence providers for process/CLI recovery features; report those capabilities blocked/degraded when unavailable |
| Selected Coding CLI | Per-task prerequisite only; verify actual terminal environment, version/help, launch/resume/exit support |
| CLI login/configuration/history | Per-task readiness; executable existence is insufficient; never request secrets in prompts or dump credentials |
| Private state, locking, receipt persistence | Required before writes; detect permissions, corruption, disk failures and unsafe paths |
| Host execution/wait capability | Required for orchestration; scripts cannot supply an agent wakeup mechanism |

`bootstrap --check` is non-mutating. `--apply` prepares the supported interpreter/venv and installs locked dependencies under the existing installation authorization, then records exact paths/versions. If uv is absent, use a documented official installation or an existing compatible interpreter; do not silently change system Python, install broad extras, or curl-pipe unverified code. Resolve the chicken-and-egg case with the shell bootstrap before invoking Python doctor. Downloads/install failures preserve the last working environment; offline cache misses produce an actionable report. Later `itermctl` commands do not implicitly resolve latest packages or require a network sync.

Choose one supported lock-generation/install pipeline in P1. Use uv as preferred tooling with hash-verified locked dependencies and a verified pip fallback if needed. The MCP lock's macOS arm64 provenance is not proof of Intel compatibility; test architecture-specific environments before declaring support.

Report doctor checks as ok/degraded/blocked/manual_action_required, with reason, remediation, observed versions, and per-operation capability consequences. Opening an iTerm API connection may prompt for consent; do not present it as a completely invisible read. iTerm settings and authorization dialogs remain explicit user actions when required; do not auto-click approval or silently rewrite user preferences. Installation acceptance ends with connection and list_sessions, not screen/history reads or terminal creation/input/closure. Live mutation tests use a separately scoped disposable session.

## Migration and documentation

- Keep the skill name initially to avoid breaking discovery. Propose v0.4.0 for the completed transport change; do not change a published tag or claim the plan itself is a new runtime release.
- Rewrite all MCP-only execution constraints in SKILL.md and references to the bundled runner only after parity gates pass. Preserve the coordinator-versus-Coding-CLI project boundary: direct runtime invocation is terminal coordination, not permission to implement project work in the host shell.
- Replace tool discovery with capabilities/schema discovery; replace MCP result envelopes with the versioned runner contract. Document permissions, timeouts, operation-status and partial outcomes in English, with aligned multilingual README installation sections and website descriptions.
- Keep registry schema and existing daily ledgers compatible. Preserve original CLI chat UUIDs, iTerm IDs and unknown/closing states; do not reset pending cleanup at migration.
- Read old recovery records only through their exact known paths or an explicit migration input. Keep old files intact; new receipts go to the skill state directory. Do not pick the newest file or silently copy all private history.
- Existing MCP installations may remain available during development but must not act concurrently on the same managed task. Switching needs a handoff: stop the task's old writer, inspect actual resources, retain generation/outcome evidence, then activate the runner. Do not delete unrelated MCP entries or uninstall the old service before direct mode is verified.
- Preserve the user's installation choice: update TRAE when appropriate and do not recreate the removed Codex skill entry as part of integration.

## Phased delivery and acceptance gates

| Phase | Deliverables | Exit gate |
| --- | --- | --- |
| P0: direct-connect spike and contract baseline | Extract a minimal read-only SDK path; freeze all 13 operation schemas/results and safety cases; benchmark repeated connect/list/disconnect; test identity and authorization behavior | At least 20 bounded one-shot read-only cycles with measured connect/operation/disconnect times, no leaked helper/socket, and verified behavior across reconnect/restart; otherwise revisit option B before expanding |
| P1: runtime preparation and diagnostics | bootstrap, minimal lock, versioned environment, doctor, capabilities, structured CLI envelope | Fresh setup, repeated setup, offline failure, wrong Python, missing iTerm, denied/pending API consent and rollback cases are distinguishable; no MCP dependency/import or client registration |
| P2: discovery, reads, create/name/input | Port 9 non-closing operations and helper modules, cross-process locks and request journal | Targeted contracts pass; read-only/allowlist cannot be bypassed; Unicode/newlines/keys/broadcast/history cancellation correct; duplicate/unknown write requests do not replay |
| P3: closing and recovery parity | Port 4 closing operations, receipts and CLI adapters; fix verified login-ancestor counting | Normal and force paths, partial results, PID reuse, scope changes, persistence failure, drafts/background/stopped jobs, self-protection and uncertain delivery pass targeted tests |
| P4: orchestration migration | Switch skill/reference examples, preserve registry/audit/handoff, implement old-receipt reading and installation migration | Disposable task completes launch -> dispatch -> monitor -> acceptance -> CLI exit -> shell exit -> disappearance -> settled without MCP; retained and blocked cases remain correct |
| P5: packaging and release | Complete archives, locks, provenance/license, English release notes, README/website updates | Clean installation from extracted archive with no MCP installed/configured; assets/checksums verified, rollback documented, no residual helper processes |

P2 may expose four read operations first, then controlled create/name/input. P3 completion does not mean the runtime now guarantees every CLI's chat restoration; supported adapters and degraded cases must remain explicit. Do not announce full parity before all 13 operations and their failure semantics are accepted.

Tests should be targeted to migrated modules. Reuse upstream screen/history/transaction/shutdown/nickname/closing/CLI-identity tests, plus the existing registry tests when its integration changes. Add tests for cross-process serialization, crash-after-send, duplicate request IDs, host ancestors, no-MCP imports, setup rollback, and safe shell classification. No unnecessary full suites and never Python --reload. Live checks must use disposable owned resources; never close preexisting user terminals as an installation test.

## Outstanding implementation discovery

1. Repeated SDK authentication and connection costs under a stable installed launcher, including host permissions: P0.
2. Which identity preconditions survive one-shot reconnect and iTerm restart without weakening stale-target protection: P0.
3. Minimal supported SDK/transitive dependency lock on arm64 and Intel: P1; initial claim limited to verified platforms.
4. Process evidence for normal shell exit without Shell Integration, including login ancestors and nested/background jobs: P3.
5. Adapter-specific conversation identity and restore correctness on actual installed CLI versions: P3/P4; agy adapter expansion is separate from baseline parity.

These items defined implementation discovery. The executable surface and orchestration migration are now in the checkout; validation and remaining platform/live-CLI coverage are recorded below.

## Implementation and acceptance evidence

The standalone runtime includes all 13 operations and preserves upstream closing payloads, history transaction handling, broadcast suppression, recovery adapters, and MIT provenance. The new runner adds strict JSON validation, bounded authentication, private cross-process locks, durable non-replaying request IDs, observation preconditions, and ownership checks for registered sessions. A missing local policy defaults to read-only; configuring access is explicit and does not rewrite MCP configuration.

- [Read-only direct-connection evidence](direct-connection-acceptance.json): 20/20 independently spawned calls using the prepared minimal dependency environment, stable iTerm IDs/topology, new per-process broker/session epochs, no pending SDK tasks/sockets/helper children. No MCP distribution is installed in that environment.
- [Live operation acceptance](standalone-runtime-acceptance.json): all 13 operations passed against disposable task-owned resources. Five created sessions were removed, including a normal shell `exit`; original user sessions remained. Global cleanup was restricted to the single disposable allowlisted session. No forced interruption was used.
- Missing Shell Integration correctly withheld normal close readiness. Loading iTerm's bundled integration only inside a test shell enabled normal close preflight; user shell configuration was not changed. Missing process-to-session identity remains unknown rather than being inferred solely from zero job counts.
- Regression coverage includes the extracted backend/history/naming/closing/recovery suites and new runner, request, ownership, concurrency, replay, persistence-failure, and authentication tests. Full unrelated repository test suites were not run.
- Independent review identified and corrected working-directory/PYTHONPATH module shadowing, virtualenv interpreter symlink handling, and uv-only launcher discovery. Runtime packaging includes source, lock, bootstrap, launcher, and upstream license.

Remaining validation limits: live iTerm restart was not performed while user terminals were open; replacement/membership changes are covered by fixtures. Live platform coverage is macOS arm64. CLI-specific transcript discovery/restoration adapters retain fixture regression coverage, but this acceptance did not interrupt or restore a real user CLI conversation. These limits must accompany any release claim.

## Sources

Local source paths are relative to the sibling MCP checkout during implementation: `src/goals_iterm_mcp/direct.py`, `backends.py`, `closing.py`, `closing_backend.py`, `process_inspection.py`, `cli_recovery.py`, `transaction_reads.py`, and pyproject.toml. All claims about current code refer to the pinned source commit above, not an assumed newer installed service.

- [iTerm2 Python API](https://iterm2.com/python-api/): direct Python control and API surface.
- [iTerm2 connection API](https://iterm2.com/python-api/connection.html): connection and finite/continuous execution entry points.
- [iTerm2 general settings](https://iterm2.com/documentation-preferences-general.html): API and application settings; verify the actual installed UI during setup.
- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/): distinguish lock maintenance, environment synchronization and prepared execution.
