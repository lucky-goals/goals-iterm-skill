# Security policy

## Scope

Security issues include instructions that cause unintended terminal input, cross-session actions, unauthorized approval, credential disclosure, or replay of non-idempotent work. This skill guides an agent; it does not isolate processes, enforce permissions, or provide a security boundary. Host permissions and the CLI's own controls remain necessary.

Security fixes are applied to the current `main` branch. Older snapshots have no separate maintenance commitment. Check the skill revision and the installed MCP version when reporting a problem.

## Reporting a vulnerability

Use GitHub's private [Report a vulnerability](https://github.com/lucky-goals/goals-iterm-skill/security/advisories/new) flow. Include the affected revision, host/CLI/MCP versions, minimal reproduction, expected and observed behavior, and likely impact. Use a dedicated test session and redact credentials and private data.

Do not disclose exploit details, real credentials, or private terminal logs in public issues or pull requests. If private reporting is unavailable, open a public issue requesting a private contact channel without including vulnerability details. There is no guaranteed response time.

For a flaw in the underlying MCP implementation, consult the [goals-iterm-mcp repository](https://github.com/lucky-goals/goals-iterm-mcp) and its reporting guidance.
