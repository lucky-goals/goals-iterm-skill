# Session nickname library and mandatory naming protocol

Every iTerm2 Session created by `goals-iterm-skill` through `goals-iterm-mcp` **must** carry an explicitly designated, memorable nickname. Creating or operating a nameless task-created Session (or leaving it with a generic shell label such as `Shell`/`zsh` or a fallback placeholder such as `session-1a2b3c4d`) is forbidden.

## Mandatory creation naming workflow

1. **Enumerate occupied names first:** Call MCP `list_sessions` before creating a Window or Tab, and collect every existing session's `name` and `title` (trimmed and case-folded), together with active nicknames in `session_registry.py`.
2. **Select an explicit nickname before creation:**
   - If the user explicitly requested a session nickname, validate that it is 1–64 characters after trimming, contains no control characters, is not a reserved selector (`active`, `all`, `current`, `focused`, `*`), and does not collide case-insensitively with any live session. If it collides, report the conflict instead of silently dropping the name.
   - Otherwise, explicitly choose unused 4–6 character nickname(s) from the **200-word nickname library** below (or run `python3 /absolute/path/to/skill/scripts/session_registry.py pick-nickname --occupied <existing-name> ...`, passing `--count <N>` when allocating distinct nicknames up front for parallel Session creation; `pick-nickname` automatically excludes non-closed nicknames in the local registry).
3. **Apply the nickname explicitly through MCP:**
   - Inspect the connected `goals-iterm-mcp` schema for `create_window` / `create_tab`:
     - **Current MCP schema (`name` parameter present):** Pass `name="<chosen-nickname>"` directly in `create_window` or `create_tab`.
     - **Older MCP schema (e.g. `0.2.2` without creation `name`):** Call `create_window` / `create_tab`, then **immediately** call `rename_session(session_id=<new_session_id>, name="<chosen-nickname>")` before registering the session or sending any shell/CLI input.
4. **Verify before registration or dispatch:**
   - Confirm from the MCP return value and `list_sessions` that the new `session_id` has a non-empty `name` matching `<chosen-nickname>`, and not a blank string, default shell title (`Shell`, `zsh`, `bash`, `login`), or fallback `session-<prefix>`.
   - If naming fails or remains unverified, treat it as a creation blocker: do **not** start a CLI or dispatch task instructions into an unnamed Session.
5. **Persist in registry and audit ledger:**
   - Pass `"nickname": "<chosen-nickname>"` when calling `session_registry.py register` (`origin="created"` rejects records without a valid explicit `nickname`), and record both `nickname` and `session_id` in the Markdown audit ledger (`index.md` and the resource-binding event). Still bind and operate the session by exact `session_id` during execution.

## Built-in 200 memorable nicknames (4–6 letters, a–z)

All 200 entries are lowercase ASCII words of length 4 to 6 characters, synchronized with `goals-iterm-mcp`:

| Range | Nicknames (8 per row) |
| --- | --- |
| A–B | `acorn`, `alpha`, `amber`, `apex`, `apple`, `arrow`, `aspen`, `atlas` |
| A–B | `azure`, `badge`, `bamboo`, `basil`, `beacon`, `berry`, `birch`, `blaze` |
| B–C | `bloom`, `bolt`, `breeze`, `brook`, `cabin`, `cactus`, `candle`, `canyon` |
| C | `cedar`, `charm`, `cider`, `cliff`, `cloud`, `clover`, `cobalt`, `comet` |
| C–D | `coral`, `cosmos`, `crane`, `crest`, `crisp`, `crown`, `daisy`, `dawn` |
| D–E | `delta`, `dingo`, `dove`, `dragon`, `dream`, `drift`, `dune`, `eagle` |
| E–F | `earth`, `echo`, `ember`, `falcon`, `fern`, `flame`, `flare`, `flash` |
| F–G | `flint`, `flora`, `focus`, `forge`, `frost`, `galaxy`, `gale`, `garden` |
| G–H | `gecko`, `glade`, `gleam`, `globe`, `grain`, `grape`, `grove`, `halo` |
| H | `harbor`, `haven`, `hawk`, `hazel`, `helix`, `heron`, `honey`, `husky` |
| I–J | `igloo`, `indigo`, `iris`, `island`, `ivory`, `jade`, `jazz`, `jewel` |
| K–L | `kayak`, `kite`, `kitten`, `kiwi`, `koala`, `lagoon`, `lake`, `lark` |
| L | `laser`, `laurel`, `lava`, `leaf`, `lemon`, `lilac`, `lime`, `lion` |
| L–M | `lotus`, `lucky`, `lumen`, `lunar`, `lynx`, `magic`, `mango`, `maple` |
| M | `marsh`, `meadow`, `meteor`, `mint`, `misty`, `mocha`, `moose`, `moss` |
| M–O | `music`, `nectar`, `neon`, `nexus`, `noble`, `north`, `nova`, `oasis` |
| O | `ocean`, `olive`, `omega`, `onyx`, `opera`, `orbit`, `orchid`, `otter` |
| P | `panda`, `peach`, `pearl`, `pebble`, `pepper`, `petal`, `piano`, `pilot` |
| P | `pine`, `pixel`, `planet`, `plum`, `polar`, `pond`, `poppy`, `prism` |
| Q–R | `quartz`, `quest`, `radar`, `raven`, `reef`, `river`, `robin`, `rocket` |
| R–S | `rose`, `ruby`, `safari`, `sage`, `sail`, `scout`, `shore`, `silver` |
| S | `solar`, `sonic`, `spark`, `spruce`, `star`, `stone`, `storm`, `summit` |
| S–T | `sunny`, `swift`, `tango`, `teal`, `terra`, `tiger`, `timber`, `topaz` |
| T–W | `torch`, `trail`, `tulip`, `velvet`, `violet`, `vista`, `whale`, `willow` |
| W–Z | `winter`, `wolf`, `wonder`, `xenon`, `zebra`, `zenith`, `zephyr`, `zinc` |
