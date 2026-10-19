# Contributing

Contributions to goals-iterm-skill are welcome: clearer instructions, reproducible behavior reports, translations, and improvements to CLI coordination. This repository contains a skill, not an MCP server or a background scheduler. MCP implementation changes belong in [goals-iterm-mcp](https://github.com/lucky-goals/goals-iterm-mcp).

## Before making a change

For a bug, open an [issue](https://github.com/lucky-goals/goals-iterm-skill/issues) with the host agent, CLI, MCP version, relevant skill revision, expected behavior, and a minimal redacted example. For a substantial change, explain the intended behavior in an issue first. Do not post terminal transcripts containing credentials or private project data. Follow [SECURITY.md](SECURITY.md) for vulnerabilities.

## Making a pull request

1. Fork the repository and create a branch for one focused change.
2. Edit `SKILL.md` for the core workflow or `references/` for detailed guidance. Keep tool names and parameters consistent with the actual MCP schema. Do not invent host scheduling capabilities.
3. Keep all four README editions aligned when changing user-facing instructions. English is the default README; skill instructions currently use Simplified Chinese. If translation assistance is needed, say so in the PR.
4. Preserve the workflow invariants: exact session IDs, one write coordinator per session, monitoring after dispatch, no blind write retries, bounded recovery, evidence-based completion, and timely audit records that distinguish intent from delivery and completion.
5. Describe the problem, changed behavior, validation performed, and any limitations in the PR.

## Validation

For documentation changes, check relative links, code fences, and `git diff --check`. If the Codex skill-creator validator is available in your environment, run its `quick_validate.py` against this skill directory; it is optional and is not bundled here.

For behavior changes, walk through the scenarios at the end of [the monitoring protocol](references/monitoring.md). Record the observations supplied to the agent and the action it would take, especially after uncertain delivery, automatic retries, expired callbacks, or partial completion. Also exercise the [audit scenarios](references/audit.md): round and event continuity, pending decisions, redaction, and write failures. Static checks do not prove live integration.

Live testing must use a dedicated session and an authorized test task. Record the host, CLI and MCP versions, the tested behavior, and monitor cleanup results. Avoid full test suites unless necessary. Do not start Python processes with `--reload`.

## Collaboration and licensing

Be respectful, explain disagreements with concrete examples, and avoid personal attacks. Submit only material you have the right to contribute. Contributions are provided under this repository's [MIT License](LICENSE).
