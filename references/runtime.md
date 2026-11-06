# Standalone iTerm runtime contract

Use the bundled runner for every iTerm operation. It connects directly to iTerm2's Python API from local macOS execution; it does not start a server or depend on client tool discovery. The host agent still owns task decisions, monitoring, acceptance, and the Markdown audit ledger.

## Prepare and inspect

From the installed skill directory:

```sh
scripts/bootstrap.sh --check
scripts/bootstrap.sh --apply
scripts/itermctl capabilities --json
scripts/itermctl doctor --json --live-api-check
```

`--check` inspects preparation state; `--apply` prepares the supported Python 3.12 runtime and the locked minimal dependencies. `capabilities` reports the local operation and schema contract. `doctor` checks local prerequisites; `--live-api-check` additionally connects and lists sessions without reading terminal bodies. That opt-in check may require a manual API setting or macOS permission response. A successful bootstrap does not prove that iTerm is running, its Python API is enabled and authorized, or a Coding CLI is ready. Keep credentials out of requests and reports. The state paths below use their default locations; `XDG_STATE_HOME` and `XDG_DATA_HOME` relocate state and prepared environments when explicitly set.

No policy file means read-only operation. The fixed policy lives at `~/.local/state/goals-iterm-skill/policy.json`; invocation requests cannot override it. To opt into writes, the authorized user must explicitly configure a scope, for example:

```sh
scripts/itermctl policy configure --allow-writes --session-id SESSION_ID
scripts/itermctl policy configure --allow-writes --all-sessions
```

Choose the narrowest authorized scope. Preserve any existing MCP `read_only` or session allowlist deliberately during migration; an upgrade never widens policy automatically. In policy, `session_ids: null` means the full configured iTerm scope and `session_ids: []` means no sessions. The all-sessions policy still does not itself authorize a global cleanup request: that operation also needs explicit user authorization and `authorization_scope: "all_sessions"` at the top level of the request. This scope means all sessions visible within the configured policy, not an expansion beyond it. A `force` argument never grants authority.

## Invoke an operation

All 13 operation names remain available: `list_sessions`, `inspect_sessions`, `read_screen`, `read_history`, `send_text`, `send_keys`, `create_window`, `create_tab`, `rename_session`, `close_session`, `close_tab`, `close_window`, and `clean_all_sessions`. Read `capabilities --json` for the installed runtime's exact argument schemas. The operation meanings and safety invariants are summarized below.

Create a version-1 JSON request, save it in a private file readable by the local runner, then invoke it. Standard input is also supported with `--request-file -`:

```sh
scripts/itermctl invoke --request-file /private/path/request.json
```

```json
{
  "schema_version": 1,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "operation": "send_text",
  "arguments": {
    "session_id": "exact-session-id",
    "text": "Read the task instructions at /private/path/dispatch.md"
  },
  "expected_observation": {
    "sessions": [
      {"session_id": "exact-session-id", "tab_id": "exact-tab-id", "window_id": "exact-window-id"}
    ]
  },
  "task_context": {
    "task_id": "task-1",
    "coordinator_id": "C1",
    "generation": 1,
    "expected_revision": 7
  }
}
```

The request envelope is `{schema_version, request_id, operation, arguments, task_context?, expected_observation?, authorization_scope?}`. For `clean_all_sessions`, set `authorization_scope: "all_sessions"` at the top level only when the user authorized cleanup across the full configured scope. `expected_observation` has the shape `{sessions:[{session_id,tab_id,window_id}, ...]}`. Obtain it from `list_sessions.data.observation` and pass the snapshot with mutations to existing resources, including `create_tab`. It is not required for `create_window` or a dry run. The runner validates current IDs and relevant container membership; a missing, added, replaced, or moved member makes the observation stale. Single-session writes ignore unrelated topology changes. Ephemeral connection epochs are not cross-call identities.

Use a fresh UUID `request_id` for each operation. Mutation IDs are durably recorded before work may begin, and the runner never replays a mutation just because the caller retries. Requests are data, never shell code. Do not put secrets or long task instructions in argv; use private files or stdin. The runner validates the schema and arguments and returns one JSON envelope:

```json
{
  "schema_version": 1,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ok",
  "code": "OK",
  "data": {},
  "warnings": [],
  "side_effects": "none"
}
```

The result `status` is one of `ok`, `refused`, `unknown`, `partial`, or `error`. Process exit codes are `0` for `ok`, `2` for `refused`, `3` for `unknown` or `partial`, and `4` for `error`. These envelope statuses and exit codes apply only after the Python dispatcher starts. Earlier launcher prerequisite or prepared-runtime manifest failures write diagnostics to stderr, exit nonzero, and do not dispatch the request. `code` is a stable domain code such as `OK`, `READ_ONLY`, `TARGET_CHANGED`, or `TASK_CONTEXT_REQUIRED`, or a native closing code; it does not have to repeat `status`. `side_effects` is `none`, `confirmed`, or `unknown`. The `data` field preserves operation-specific results, including per-session close arrays, recovery record references, truncation indicators, and task-completion evidence. Read `status`, `code`, `warnings`, and `side_effects` together with `data`; a process error or missing response does not prove that no write occurred. A dry-run request that was evaluated successfully has envelope status `ok`, even when its domain `code` is `ACTIVITY_BLOCKED` and its preview says a target is ineligible.

If a mutation result is missing or its side effects are unknown, reconcile by request ID:

```sh
scripts/itermctl operation-status --request-id 550e8400-e29b-41d4-a716-446655440000
```

Then use fresh read-only observations and known recovery receipts to establish what happened. `operation-status` has its own envelope: `status: "ok"` means the lookup succeeded, while `data.status` describes a journal record (`completed` or `unknown`) and `data.result` contains the original operation envelope when available. `data: null` means no record for that request ID was found in the current runtime state location; it does not show that a possibly lost write never occurred. Verify the exact request ID and state location, then reconcile through read-only observations and known recovery receipts. Never infer task completion from a missing record or submit the same mutation again to “make sure.” If the outcome remains unknown, keep it unknown and hand it off with the evidence. Operation records prevent replay; they do not guarantee that an iTerm action completed exactly once.

When a targeted Session is already present in the shared session registry, include `task_context`; omitting it cannot bypass generation or revision checks. For one registered Session, provide `task_id`, `coordinator_id`, `generation`, and `expected_revision`. For container operations that touch multiple registered Sessions, use `task_context.sessions` as a per-Session map, for example `{"S1":{"generation":1,"expected_revision":7}}`, alongside the shared task/coordinator IDs. Unregistered direct/manual operations and resource creation may omit `task_context`.

## Operation guarantees

| Operation | Contract to preserve |
| --- | --- |
| `list_sessions` | Exact Session/Tab/Window identities, names, topology, and an observation snapshot; does not read terminal bodies. |
| `inspect_sessions` | Prompt, process, CLI, activity, blocker, remediation, and advisory readiness evidence; does not decide business acceptance or authorization. |
| `read_screen` | Rendered lines, geometry/cursor, capture time, and truncation state. |
| `read_history` | Retained history, position/wrapping/bounds, default 100 and maximum 2000 lines, transaction cancellation, and stale-read protection. |
| `send_text` | Exact 1–16384 UTF-8 bytes, no appended newline, broadcast suppression, and no automatic write retry. |
| `send_keys` | Explicit supported key enum and exact Session selection; meaning remains program-dependent. |
| `create_window` | Optional startup command, unique generated name, and returned identities. |
| `create_tab` | Exact Window, optional startup command, returned identities, and prohibition under a session allowlist. |
| `rename_session` | Optional generated name, trimmed length 1–64, no control characters or case-folded collisions. |
| `close_session` | Exact selector, fresh preflight, durable recovery receipt, verified exit, and independent closure result. |
| `close_tab` | Complete membership preflight; refuse when a member is outside scope; do not silently close a partially checked Tab. |
| `close_window` | The same membership and scope guarantees across every current Tab and pane. |
| `clean_all_sessions` | Explicit all-sessions authorization, configured policy scope, idle filtering, initial snapshot, per-session partial outcomes, and no new arrivals. |

The coordinator still performs normal CLI exit through verified CLI-specific commands, then verifies and exits an eligible idle shell, enumerates disappearance, and uses guarded close operations only for resources that remain. Preserve the difference between CLI exit, shell exit, terminal closure, and conversation recovery. The runner does not infer business acceptance or authorize a cleanup.

## State, privacy, and boundaries

The prepared runtime is keyed to the skill version and dependency lock and is stored outside the skill package. Private coordination state is stored under `~/.local/state/goals-iterm-skill/`, including the fixed policy, operation records, and detailed recovery receipts. Keep state private; do not copy credentials, raw environment, full command lines, or task instructions into operation records. Operation records and recovery receipts complement, but never replace, the host's human-readable audit ledger.

Use only the exact Session IDs and observations returned by the runtime. A session allowlist limits visible sessions; it does not confer ownership or user authorization. Container close operations must account for every current member. `clean_all_sessions` is global only within the configured policy scope and requires both the explicit request field and user authorization. Do not switch to another terminal channel to bypass policy, identity, ownership, process, or uncertain-outcome protections.

Process inspection also returns bounded `active_jobs`, `stopped_jobs`, and `ignored_ancestors` evidence with truncation flags. Only a verified stable same-TTY direct `login` parent is classified as an ignored ancestor. The projection omits raw commands, arguments and environments; missing process identities continue to block a positive readiness claim.
