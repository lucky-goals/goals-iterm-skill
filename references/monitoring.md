# Monitoring and advisor decision protocol

## Choose a monitor that can actually run

A monitor is a loop of persisted task state, timed terminal reads, decisions, and dispatches when needed. A shell sleep, background log collector, or plan file alone does not wake an agent to make decisions.

Delegated, taken-over, and resumed tasks default to an inline monitor in the current execution. Create a background monitor only when the user explicitly requests it and the host has a real wakeup mechanism that can restore task context and reach the same machine's iTerm MCP. Check actual tool schemas and scheduling granularity before calling, then verify and record the returned handle. Do not invent `iterm.monitor`, switch to background merely because a task is long, or assume every coding agent has automation tools. Do not install daemons or change global configuration for this skill.

If requested background monitoring is unsupported, do not claim it is scheduled or silently record an unsupported monitor as background. Explicitly explain and continue inline only when that still fits the user's request. If the user asks to end or return now, save a checkpoint and honestly mark unscheduled/needs handoff instead of forcing a foreground loop. Context growth alone is not a stopping condition: continue using checkpoints and normal host continuation when possible. End active progress only for an unavoidable host limit, an explicit stop request, required user input/authorization, or an unrecoverable blocker, and hand off honestly.

Use the host's real interruptible sleep/wait for inline polling. Do not run sleep in the target iTerm shell to simulate a host wait. Start around 10–15 seconds and gradually widen to 30–60 seconds without substantive change. Each actual wait segment is at most 60 seconds. Split longer intervals into interruptible segments; after each return, read state and decide whether action is needed before waiting again.

Record `monitor_mode=inline|background|none|unknown`. Missing legacy fields mean unknown. Same-task coordinator handoff resets mode to unknown while preserving old handles for verification/disabling. Cross-task handoff and identity-generation changes clear old mode/handles. Before such resets, preserve original handles in the ledger/checkpoint and verify deactivation. Clearing a field does not prove the scheduler stopped. Mode does not prove liveness; schedule_status only reflects a recorded real nonempty handle under registry conventions, not whether it remains alive. Query the real handle separately to report scheduler status. Do not infer active background work from monitor_mode=background, next_check_at, or a task record alone.

Background callbacks and resumable checkpoints preserve: task-record location, absolute ledger path and latest E event, outer U-round mapping, per-session CLI C rounds, unresolved D decisions, coordinator/generation/revision per Session, target session_id and acceptance criteria, recovery and read-only recheck counts, summaries and delivery states for unconfirmed dispatches, all valid deadlines, and monitor mode/real handles. Follow the [audit protocol](audit.md). On recovery/context continuation, reread current user instructions, registry, ledger tail, and live target state. Reconcile rounds and delivery before acting. Do not reset numbering, replay uncertain instructions, or blindly act on expired deadlines. Callbacks follow these rules:

> First check that the task is still valid and not completed, canceled, waiting for the user, finalizing, closing, or closed. Disable this business monitor for terminal/finalizing states; do not write or automatically restore terminals. For waiting_user, clear check deadlines, stop polling, and await the user's reply. Confirm that the Session still belongs to the same task before reading new output. Stay quiet without meaningful change. When action is needed, follow this skill's authorization and recovery rules, updating the original monitor after every send. Notify only for completion, failure, significant changes, or required user decisions. Do not create a concurrent writer.

If the host cannot guarantee serialized callbacks or sole ownership, background monitors only observe and notify; the sole foreground coordinator sends. A state field is not a cross-process lock. If scheduler creation/update is uncertain, query existing records before creating anything else.

Split the ledger by processing date in the task timezone. Checkpoints keep the stable index path, current daily-file absolute path, and latest E. On resumption, read the index and latest tail first. Date rollover changes only the event file; retain C/D numbers, delivery states, and monitor. Reconcile continuity under the [audit protocol](audit.md#daily-files-and-date-rollover); never replay because the date changed.

## Polling multiple sessions and selecting a wait

Runnable targets include finalizing sessions with authorized cleanup actions or due read-only rechecks. Business `monitor_status=stopped` does not remove them from finalization. Remove targets from timed polling when recheck limits are reached or user intervention is required.

In each cycle, handle every runnable/due Session first: read live state and registry, decide, perform authorized decisions/dispatches, and update ledger and monitor. Mark sessions needing user input `waiting_user` (recording pending `D` IDs in `unresolved_decisions`), clear their next check times, and check whether any parallel sibling subtask depends on that unresolved contract: keep advancing unaffected siblings, while holding new dispatches that depend on the unresolved choice so siblings do not write conflicting throwaway code. After processing everything due, enter one inline wait until the nearest valid future deadline, capped at 60 seconds per segment. Do not sleep separately for every Session or sleep before processing other due sessions.

If next_check_at is already in the past, process that Session immediately without waiting, then set only an evidence-based next deadline. Waiting_user, canceled, and blocked sessions without a retry condition must not retain stale deadlines or use polling/sleep to simulate awaiting a user reply or nonexistent event. If other sessions remain active, handle them and wait only for their nearest valid deadline. If none remain, save state and return control to the user/responsible party rather than busy-waiting. Never invent a user reply time, host goal, or background handle.

## Progress narration before inline waits

During inline execution, before every wait (sleep, a tool result, or the next poll), post an update through the host's user-visible progress channel, such as commentary. Do not only call a wait tool, or end still-running inline monitoring with a final response. The coordinator speaks to the user; do not write narration to the controlled terminal or interrupt CLI work to obtain it.

Cover these points in 1–3 sentences, or a short list for multiple tasks:

- **Current work:** identify task/CLI, stage, and latest actual observation. Separate CLI claims from verified outcomes. With no new output, say what was last observed and that no update is available; do not pretend editing/testing continues without evidence.
- **This wait:** name the result/event awaited, such as a test summary, reconnection, command exit, or decision prompt, and the next check interval. That interval is a check plan, not an estimated completion time; state unknown duration when appropriate.
- **Remaining work:** state key unfinished steps in dependency order, such as reading tests, inspecting changes, acceptance, then recovery-data capture and cleanup. Remove completed steps. Make conditions explicit (“after it passes,” “if it fails”) rather than claiming future success. Distinguish multiple tasks by short names and their separate waits.

Send this factual narration before every real wait, including each segment of at most 60 seconds. For multiple sessions, explain what was processed, latest evidence, nearest deadline, and remaining work. Give all three points before the first wait, then brief updates; unchanged observations can be one sentence rather than a repeated plan. Keep the 10–15 second initial cadence, widening to 30–60 seconds without change; do not poll more often just to produce narration. For long tools that can yield, use segmented waiting and reassess/report on each return without restarting the call. If a tool cannot be interrupted or segmented, explain that visibility limit before calling and update promptly afterward. Do not promise timed messages without a real mechanism. Do not call waits or send repetitive “waiting for the user” updates for waiting_user, canceled, or blocked states without actionable rechecks.

Report stage changes, key results, blockers, required choices, and acceptance/cleanup transitions immediately rather than waiting for the next cycle. Use the host's question channel alongside self-contained context (options, affected scope, recommendation, and reasons) for user choices; never drop context just to fit short option labels, and keep progress narration only for explaining what is pending. Respect user preferences for frequency or quiet operation while preserving necessary blocker/result notifications. Background monitors still stay quiet without changes; inline narration must not turn into repetitive background notifications.

Keep the latest narration time, reported stage, wait target, and remaining work in host task records. Recheck evidence before continuing after handoff; these are not MCP parameters. Narration includes only verifiable progress and next steps, never credentials, full logs, invented percentages/ETAs, or private reasoning. It does not replace the ledger. Record key events under the audit protocol; repeated unchanged updates need not each become separate audit events.

Examples, only when supported by actual observations:

> Codex has started the targeted parser tests; the terminal has not shown a summary yet. I will check for results in 15 seconds, then inspect the changes, verify acceptance, and reclaim the terminal according to ownership.

> No new output this cycle; the last visible state was the test runner. I will check for the summary in 30 seconds. Change review, acceptance, and cleanup remain.

> The CLI says it will reconnect in 20 seconds. I will check the reconnection result in about 20 seconds; testing and acceptance remain before terminal cleanup.

## Observe and act each round

1. Read current user requirements, task records, and coordinator/generation/revision in the [shared registry](session-lifecycle.md). Stale writers cannot act. Investigate conflicts first; registry locks do not replace live checks. Cancellation, pause, closure, and user takeover override old callbacks.
2. Verify session_id, read the screen, and add history if needed. Save time and concise evidence, avoiding full logs with credentials.
3. Distinguish running, automatic retry, pending decision, confirmed interruption, candidate completion, and uncertainty.
4. Before writing, reread the screen to confirm interaction state has not changed. Stop automatic writes on human input or another coordinator's takeover.
5. Append key observations and pending questions to the Markdown ledger. Make only the currently necessary decision: record intent, decision maker, and rationale, send, and append delivery outcome. Update the monitor immediately after sending. Update registry revision, monitor checkpoint, and next check. Keep per-session rounds separate but linked to the same task ledger.

## Advisor decisions and escalating to the user

Keep routine engineering flow moving without unnecessary interruptions, while ensuring every major decision escalated to the user is crystal clear, contextualized, and backed by concrete advice:

| Situation | Action |
| --- | --- |
| CLI asks a routine implementation or repository-style choice (e.g., local module layout, reusing existing helpers vs small inline code, adding a minor repo-compatible utility, local API/error-code compatibility) | Decide directly using the goal, existing repository conventions, compatibility, and change size; briefly state the rationale, record it in the ledger, and continue |
| CLI proposes read-only diagnosis or targeted tests | Allow within existing authorization while preserving project testing constraints |
| CLI requests execution permission | Inspect the exact action; approve only within user and host permissions, without enabling a global permission-bypass mode |
| CLI raises an uninferable product/UX tradeoff, major cross-module/heavy-dependency shift, destructive/irreversible change, extra cost, or out-of-scope publication/push | Perform any needed read-only inspection first (including whether any parallel sibling subtask is coupled to this choice), mark the blocked session `waiting_user` with `unresolved_decisions` recorded, stop automatic writes (and hold dependent sibling dispatches if coupled), and escalate to the user under the self-contained escalation rules below; do not repeatedly ask the same question |
| Login, verification code, missing credential, or account quota blocker | Report which session/CLI hit the blocker, the exact step affected, and the needed user action; wait without soliciting or forwarding credentials |

Be specific when deciding directly — for example: “Follow the existing repository pattern in `auth/errors.py` rather than introducing a new wrapper class, run targeted auth tests, and return the diff and results.” Never send an ambiguous “continue.” Put multiline or multi-condition decisions in a [decision file](dispatch.md) and send only a single-line reference. Observe reading and execution evidence; a failed read is not an implemented decision.

### Self-contained escalation requirements (no over-compression)

Assume the user is **not watching the iTerm terminal screen** and must understand and decide purely from your message. Every escalated decision item must satisfy all four rules:

1. **No context-free shorthands or raw forwarding:** Never copy a vague CLI question (`"Use A or B?"`, `"Proceed with cleanup?"`, `"Delete old branch?"`) verbatim or compress items so heavily that the target or stakes disappear. In user-facing prose, lead with the session's memorable **`nickname`** (`[D01 · ember]`), adding `session_id` inline only when needed to disambiguate while always recording the exact `session_id` in the ledger and registry. State what step was running, concrete target objects (exact file paths, modules, commands, data, or APIs), any coupled parallel sibling sessions, and why user authorization is required.
2. **Always synthesize concrete options:** Expand each choice from a label into what it actually does and its impact/risk. If the CLI failed to lay out clear alternatives, inspect the relevant code/state read-only first and construct the viable options yourself.
3. **Always give a recommendation and concrete reasons:** Unless the choice is strictly subjective with no technical/product preference (in which case explicitly state why either option is equally valid), select one **recommended option**, mark it clearly (e.g., `(Recommended)`), and explain:
   - **Why this option fits best** (alignment with goal, repo conventions, compatibility, reversibility, scope/risk control); and
   - **Tradeoffs vs alternatives** (what concrete drawback or risk makes the other option less preferred).
4. **Preserve distinct numbered items, question-tool clarity, & sibling isolation:** When multiple decisions require user input (e.g., across parallel sessions), list each decision separately by ID (`D01`, `D02`, …) with its own context, options, and recommendation — never collapse distinct decisions into one vague summary. Check cross-subtask coupling: advance unaffected parallel sessions normally, but if a running/pending sibling subtask depends on `D01`'s contract or schema, note that impact in `D01` and hold dependent sibling dispatches until `D01` is resolved. If using a host multiple-choice card/question tool whose option labels must stay concise, put the full context, tradeoff details, and rationale in the message/prompt body above the options, keep option labels self-explanatory with the recommended option first, and avoid bare `"Option A / Option B"` labels.

### Tiered presentation format

Match verbosity to decision complexity without ever omitting target objects, recommendation, or reason:

- **Concise form (for simple, bounded decisions)** — e.g., a single straightforward yes/no authorization, retention check, or low-complexity two-way fork whose facts fit in 2–4 lines:
  - Lead with **`[D<nn> · <nickname>]`** + **subtask/step & concrete target**, state the **explicit options**, and mark the **recommended option** with its **brief reason / consequence** (exact `session_id` recorded in the ledger).
  - *Example:*
    > **[D01 · ember]** Auth cleanup finished, and the CLI asks whether to delete the obsolete local fixture `tests/fixtures/legacy_oauth_v1.json` (no remaining code references found).
    > Options: **(1) Delete `legacy_oauth_v1.json` now (Recommended)** — removes dead fixture debt while keeping git history reversible; **(2) Keep the file** — zero deletion risk, leaves unused fixture on disk.
- **Full 4-part brief (required for complex, multi-file, architectural, high-risk, or non-obvious tradeoffs):**
  1. **Context & blocker:** Which session (`nickname`, plus `session_id` if disambiguating) and step hit this point, verified terminal/code facts, and why it cannot be decided automatically.
  2. **Decision point & affected scope:** Exact question to decide, concrete files/modules/behaviors/branches/external effects involved, and whether any sibling parallel session is coupled.
  3. **Option comparison:** Each viable option (concrete action, pros, cons/risks, reversibility).
  4. **Recommended option & rationale:** Explicit recommended choice + why it wins over the alternatives under current constraints.
  - *Example:*
    > **[D02 · beacon] Token refresh storage contract**
    > 1. **Context & blocker:** While implementing refresh-token rotation in `src/auth/refresh.py`, Codex found that concurrent multi-tab requests race on the current file-backed store; resolving this changes external storage behavior beyond routine local edits.
    > 2. **Decision point & affected scope:** Choose where rotated refresh tokens are persisted across `src/auth/refresh.py` and `src/config/settings.py`. Sibling session `frost` (API middleware tests) depends on this error/header contract and is held before its integration step; `cedar` (CLI docs) continues unaffected.
    > 3. **Option comparison:**
    >    - **Option A — SQLite WAL table in existing app DB (`Recommended`):** Atomic row-level rotation with zero new external services; adds one migration (`migrations/004_refresh_tokens.sql`), reversible via rollback.
    >    - **Option B — Require Redis lock + TTL store:** Best horizontal scale, but introduces a new mandatory runtime service and config dependency not present in `pyproject.toml`.
    > 4. **Recommended option & rationale:** **Option A (SQLite WAL)** — matches the repository's existing single-node SQLite architecture, avoids adding operational infrastructure mid-task, and unblocks `frost` with minimal scope expansion.

## Network errors and bounded recovery

Text such as timeout, connection reset, or 429 does not alone prove interruption. First check for retry/backoff, a countdown, working state, or continuing output. If automatic recovery is visible, wait according to the displayed retry interval without duplicate instructions.

Treat a round as interrupted only after an explicit failure returns to input/a retry menu and a later observation shows no automatic continuation. Two unchanged observations are supporting evidence only; without explicit failure/stoppage, the state remains uncertain. For long silence, gather context and report a stall rather than automatically sending Ctrl-C.

After confirmed interruption:

1. Check progress and any external side effects before the failure. Verify actual results to avoid duplicate submission/publication.
2. Prefer an explicit retry/resume control in the current interface. Otherwise, once CLI input is confirmed ready, send a contextual continuation: “Continue after completed X; first check whether Y already finished and do not repeat it. Remaining acceptance criteria are Z.”
3. If the CLI exited to a shell, verify exit and project directory before using a verified resume method. Never send natural-language continuation to the shell. Read local help when recovery arguments are unclear; do not guess historical conversation IDs.
4. Reenter monitoring after every recovery and wait for real progress. Default to at most two automatic recovery attempts for the same blocker, with at least 30 seconds of backoff or a longer service-specified delay. Reset that counter only for clear progress or a changed blocker; user budgets/deadlines take precedence.
5. At the retry limit, authentication failure, quota exhaustion, or insufficient evidence, mark intervention required, pause active retries, and report latest evidence, attempted actions, and needed help. Do not restart indefinitely.

## Completion, waiting for the user, and stopping

A CLI returning to input may only mark a phase boundary. Check each acceptance criterion: request missing targeted tests or final outputs. Failed tests or partial work are not success.

After acceptance, enter finalizing per Session, persist business terminal state and pending cleanup separately, then disable all associated business monitor handles and verify it so late callbacks cannot dispatch more work. Stopping the business monitor does not stop the finalizer. The sole coordinator still owns [automatic cleanup](automatic-cleanup.md) and [resource accounting/bounded rechecks](session-lifecycle.md). The inline finalizer may submit verified [normal-exit](natural-exit.md) commands and observe outcomes without restarting business monitoring. It continues authorized resource finalization. While waiting for resource-state changes, use only necessary read-only checks, interruptible host sleeps, and further read-only checks; no business dispatches or monitor restoration. For unknown close responses, do not close again. Default to at most two separate read-only state/receipt checks, then hand off if still unknown. Retry closure only when no side effects are confirmed, a temporary blocker has changed, and permission still holds, at most twice. Count these retries separately from ordinary polling. Do not continue polling waiting_user, canceled, or blocked sessions without an actionable next step; keep processing other active sessions. After the user replies, reobserve the screen before resuming and updating monitoring.

“Stop monitoring” stops monitoring only. If work is already accepted, account for the independent finalizer responsibility honestly. To stop a running task, verify the exact Session, interrupt according to the CLI's current semantics, and observe. Do not substitute Ctrl-D, which may exit the session, for task cancellation.

## Monitor handoff for closing and restoration

On a cleanup request or [automatic cleanup](automatic-cleanup.md) eligibility, follow [closing and recovery](closing-and-recovery.md): persist closing and a new revision through a version-checked update, then disable associated writing monitors to block late callbacks. Record disable failures honestly; do not claim a handle is stopped. Old generations cannot write even if triggered again. Manage only monitors owned by this task.

Record verified closure as closed. Preserve per-session partial failures/unknowns and pause writes for read-only reconciliation. Restore monitoring on skipped/refused sessions only after fresh observation and only if the user still wants the original task continued. Restoration requires binding the new iTerm Session ID, verifying the original CLI chat UUID, increasing generation, and enforcing one writer. Original Session disappearance is not automatic recreation permission. Reusing the same Session for a new task requires explicit handoff and clearing old acceptance/cleanup eligibility. Stopping business monitoring does not end finalization responsibility.

## Focused validation scenarios

After changing the skill, walk through these terminal excerpts/events and inspect the actions, not just keywords:

| Observation / event | Expected action |
| --- | --- |
| “Reconnecting… retry in 20s,” followed by normal output | Wait and observe; do not resend |
| “Request failed,” stable return to input, still stopped at recheck | Verify results, recover once, and update the monitor |
| send_text timeout, followed by running work | Treat delivery as possible; do not resend |
| Unsent multiline decision and unknown paste behavior | Write a decision file, record intent, send/verify/submit a single-line path instruction; apply [dispatch scenarios](dispatch.md#focused-validation-scenarios) |
| `[Pasted text #1]` with unverifiable contents | Do not infer failure/submission; check ownership and submission state. Clear only this coordinator's confirmed unsubmitted draft using known semantics before switching to a file |
| CLI cannot find/read the file | Record failure and check environment/readable paths; no guessing from filenames, permission expansion, or multiline paste fallback |
| CLI asks whether to reuse a parser, pick local helper naming, or maintain local error-code compatibility matching repo style | Decide directly from repository conventions and goal without asking the user; record a brief rationale and continue |
| CLI asks a bare “Option A or B?” without explaining code impact or recommending one | Inspect relevant files/terminal read-only first; build self-contained options, pick a recommended choice with concrete reasons (using concise or 4-part format by complexity), and mark the session `waiting_user` |
| Two parallel sessions each raise a major tradeoff or destructive push request | Present numbered `D01` and `D02` leading with each session's `nickname`, scope (including any coupled sibling session), options, recommendation, and reasons (expanding complex items to 4 parts); pause `waiting_user` sessions and hold any dependent sibling dispatches while advancing unaffected active siblings |
| Host question card has short option buttons | Write full context, affected scope, option tradeoffs, and rationale in the message/question body; make option labels descriptive and list `(Recommended)` first |
| CLI wants production-data deletion or out-of-scope publication | Escalate with full target/consequence context, safe default recommendation, and rationale; pause automatic writes |
| “Done,” but required tests have not run | Request missing validation and keep monitoring |
| Only a prompt, no explicit result | Read more context; do not declare completion |
| Session disappears and a new same-nickname session_id appears | Do not automatically rebind or replay |
| Old-generation callback fires after completion | No terminal writes; disable the old monitor |
| Context grows or ordinary continuation is possible | Save a checkpoint and continue; do not claim monitoring was interrupted |
| Hard host limit prevents continuation with no real background wakeup | Save a checkpoint and honestly hand off unfinished/unscheduled work |
| User requests background monitoring without resumable host wakeup | Explain the limitation; do not fabricate a background monitor or handle |
| Same network blocker still fails after two recoveries | Pause recovery, summarize evidence, and request necessary intervention |
| Old monitor sees CLI exit during closure | Do not restore or continue; reconcile closing read-only |
| Conversation restored into a new Session | Verify original chat UUID, update binding/generation, and block stale callbacks |
| Work accepted but terminal cleanup blocked | Keep business completed and monitor stopped; record cleanup blocked/unknown without restarting work |
| Work completes in borrowed/retain resources | Stop this task's monitor, retain terminal, and report retained |
| Targeted tests just started before a 15-second inline wait | Tell user the stage, awaited summary, next check, and remaining acceptance/cleanup, then wait without CLI input |
| No output in the second cycle; next check widened to 30 seconds | Briefly report latest observation, lack of new evidence, wait target, and remaining work; no invented progress/ETA |
| CLI claims done but evidence is not yet verified | Report acceptance checks and unresolved items, not completion or immediate cleanup |
| Long-running tool can yield partial control | Wait in segments up to 60 seconds; reassess/report and wait on the same call, without restarting it |
| Background monitor observes no change twice | Stay quiet; update observations without inline narration |
| Two CLIs are testing and automatically reconnecting | Distinguish each task, evidence, wait target, and remaining work |
| Two sessions are due for checks | Process both before one host wait of at most 60 seconds until the nearest next deadline; no per-session sleeps |
| One session waits for the user while another runs | Clear the first deadline and stop polling it; advance the active Session and wait for its deadline |
| All sessions wait for the user, are canceled, or have no recheck action | Clear stale deadlines, do not sleep/poll, save state, and return control |
| next_check_at has expired | Observe immediately; do not sleep first or treat the stale deadline as real background scheduling |
| CLI accepted, business monitor stopped, resources still pending | Keep finalizing; perform only authorized cleanup and necessary read-only waits/checks without restarting business monitoring |
| Close response unknown | At most two read-only topology/receipt checks; no repeated close, and hand off if still unknown |
| Explicit temporary close failure with confirmed no side effects | After conditions change, retry closure at most twice; ordinary read polling does not consume this retry budget |
| All sessions enter waiting_user | Clear deadlines and await new user messages directly; no sleep or repeated background polling |
