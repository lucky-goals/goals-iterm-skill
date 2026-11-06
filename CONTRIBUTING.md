# Contributing

Contributions to goals-iterm-skill are welcome: clearer instructions, reproducible behavior reports, translations, and improvements to CLI coordination. This repository includes the standalone iTerm runtime, but does not supply a background scheduler or a security boundary.

## Before making a change

For a bug, open an [issue](https://github.com/lucky-goals/goals-iterm-skill/issues) with the host agent, runtime/skill revision, target CLI, relevant policy scope, expected behavior, and a minimal redacted example. For a substantial change, explain the intended behavior in an issue first. Do not post terminal transcripts containing credentials or private project data. Follow [SECURITY.md](SECURITY.md) for vulnerabilities.

## Making a pull request

1. Fork the repository and create a branch for one focused change.
2. Edit `SKILL.md` for the core workflow, `references/` for detailed guidance, or `runtime/` for terminal operations. Keep operation names, arguments, request/results, policy, and preconditions consistent with the bundled runner contract. Do not invent host scheduling capabilities.
3. Keep all four README editions aligned when changing user-facing instructions. English is the default README and the language for SKILL.md, agent metadata, and references. Preserve the localized README editions; keep commands, state fields, authorization boundaries, and cross-reference anchors consistent when translating. If translation assistance is needed, say so in the PR.
4. Preserve the workflow invariants: exact session IDs, one write coordinator per session, monitoring after dispatch, no blind write retries, bounded recovery, evidence-based completion, and timely audit records that distinguish intent from delivery and completion.
5. Describe the problem, changed behavior, validation performed, and any limitations in the PR.

## Validation

For documentation changes, check relative links, code fences, and `git diff --check`. If the Codex skill-creator validator is available in your environment, run its `quick_validate.py` against this skill directory; it is optional and is not bundled here.

For behavior changes, walk through the scenarios at the end of [the monitoring protocol](references/monitoring.md). Record the observations supplied to the agent and the action it would take, especially after uncertain delivery, automatic retries, expired callbacks, or partial completion. Also exercise the [audit scenarios](references/audit.md): round and event continuity, pending decisions, redaction, and write failures. Also exercise the [closing and recovery scenarios](references/closing-and-recovery.md): exact nickname scope, selective cleanup, recovery persistence before exit, partial results, and monitor handoff. Exercise the [automatic cleanup scenarios](references/automatic-cleanup.md) for resource ownership, retained/borrowed parents, container membership changes, completion gating, and cleanup results independent of task completion. Exercise [session lifecycle scenarios](references/session-lifecycle.md) for startup gaps, task handoff, stale writers, finalizing, unscheduled follow-ups and resource accounting. Run `python3 -m unittest discover -s tests -p test_session_registry.py` for registry changes; use temporary state paths, never live user records. Static checks do not prove live integration.

For dispatch changes, also walk through the [file dispatch scenarios](references/dispatch.md): multiline instructions, conditional decisions, folded drafts, user-owned input, uncertain delivery, unreadable files, and superseded instructions. Check file preparation, submission, CLI reading, and execution as separate states.

Live testing must use a dedicated session and an authorized test task. Record the host, runtime and CLI versions, configured policy scope, tested behavior, and monitor/cleanup results. Avoid full test suites unless necessary. Do not start Python processes with `--reload`.

## Collaboration and licensing

Be respectful, explain disagreements with concrete examples, and avoid personal attacks. Submit only material you have the right to contribute. Contributions are provided under this repository's [MIT License](LICENSE).
