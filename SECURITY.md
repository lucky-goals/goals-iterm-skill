# Security policy

## Scope

Security issues include instructions that cause unintended terminal input, cross-session actions, unauthorized approval, credential disclosure, or replay of non-idempotent work. The bundled runtime applies a fixed local policy and durable mutation records, but this skill does not isolate processes or create an operating-system security boundary. Host permissions and the CLI's own controls remain necessary. The local session registry uses private files, a file lock, and revision checks to coordinate participating agents; its assertions do not authorize terminal operations or prevent users and other clients from reusing a session. Keep records free of credentials, and verify live identity and authorization before acting.

Security fixes are applied to the current `main` branch. Older snapshots have no separate maintenance commitment. Check the skill/runtime revision and configured policy when reporting a problem.

## Reporting a vulnerability

Use GitHub's private [Report a vulnerability](https://github.com/lucky-goals/goals-iterm-skill/security/advisories/new) flow. Include the affected skill/runtime revision, host and CLI versions, relevant policy scope, minimal reproduction, expected and observed behavior, and likely impact. Use a dedicated test session and redact credentials and private data.

Do not disclose exploit details, real credentials, or private terminal logs in public issues or pull requests. If private reporting is unavailable, open a public issue requesting a private contact channel without including vulnerability details. There is no guaranteed response time.

For issues inherited from upstream iTerm runtime code, see the provenance and source details in [runtime/UPSTREAM.md](runtime/UPSTREAM.md).
