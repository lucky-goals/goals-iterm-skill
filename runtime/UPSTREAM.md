# Runtime source provenance

The extracted iTerm service and supporting modules originate from
[`goals-iterm-mcp`](https://github.com/lucky-goals/goals-iterm-mcp) source commit
`66f4d82dfed12bba974149a795dea266e243dfc1` (version 0.2.2).

The MIT license and copyright notice are preserved in `runtime/LICENSE`.
The standalone runtime adapts `direct.py` to remove MCP and Pydantic imports,
server decorators, transport envelopes, and stdio serving. It does not fetch
upstream source at runtime.
