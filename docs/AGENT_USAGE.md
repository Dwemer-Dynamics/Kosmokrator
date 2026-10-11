# Agent usage

A single coding agent can build a first nation or map. [The agent team workflow](AGENT-TEAM.md)
is optional for coordinated specialist work; it is not required setup. When requested,
use bounded specialists, one writer per file and explicit verification.

Read-only `author_state` kinds now include `inheritance`, `compatibility`, `balance`
and `balance:<nation IDs separated by commas>`. These return source-backed reports;
they do not change the mod or simulate combat. See [inheritance](INHERITANCE.md),
[compatibility](COMPATIBILITY.md) and [comparisons](BALANCE-COMPARISONS.md).
Kind `mercs` lists and appends optional `#newmerc` companies with structured, manual-documented fields; see
[mercenary companies](WEB-BROWSER.md#mercenary-companies) and the optional-merc rule in
[NATION-DESIGN.md](NATION-DESIGN.md#generation-requirements). `search_game_data` and the browser's read-only
**Vanilla inspector** also cover the `mercs` and `events` catalog tables.
Use `map-builds` with `author_state`/`author_save` for the
[agent map workflow](AGENT-MAPS.md): brief, staged output review and guarded import.

The MCP server (`kosmokrator-mcp` or `kosmokrator mcp`) exposes 19 tools. Core operations are
`create_project`, `inspect_mod`, `apply_mod_patch`, `lookup_command`, `allocate_ids`, `search_game_data`,
`validate_mod` and `export_mod`. Authoring adds `author_state`, `author_save`, `reference_game_data`,
`import_mod`, `external_tools`, `preview_external_tool`, `run_external_tool` and `external_tool_runs`.
`project_view` adds resolved sheets, references and compatibility. `author_state` / `author_save` also
accept `commands:<context>` and `dependencies`; see [universal authoring](UNIVERSAL-AUTHORING.md).
Map support adds `import_map`, `export_map` and `maps` / `maps:<id>` authoring states. Map edits use a
whole-bundle `expected_revision`, with preview/save and source backups; see [Maps and scenarios](MAPS.md).
Before creating or rebuilding a map, read [MAP-DESIGN.md](MAP-DESIGN.md) and apply its geography,
land/sea, readability, balance and packaging checks. Record the brief and untested limits.
Generate seasonal and terrain art using [MAP-LAYERS.md](MAP-LAYERS.md), including its complete filename matrix.
For new maps, follow MAP-DESIGN.md's brief-first discovery flow: players/size/water,
geography/playable planes/fairness/wrapping, then theme and special features.
Reuse supplied answers and delegated choices. Show province budgets by environment
and plane before generation, then apply layout, access, artwork and delivery gates.
They share the CLI and browser backend. Results use an `ok` envelope; external runs also have a receipt
status that must be checked. MCP uses stdout for protocol and stderr for logs. Pass the workspace
explicitly at startup; projects are addressed by slug.

## Default artwork scope

A request to build a new nation includes its complete original artwork by default,
even when the user describes only a theme. Derive the art direction from that prompt
and the approved asset rules. Plan idle/attack pairs for every troop, commander,
summon, hero, pretender and alternate form, plus an original nation flag and custom
mod banner. Include any additional artwork required by the requested content.
Every new magic item also requires an original icon, referenced with item `#spr`,
unless the user explicitly requests reuse or a prototype. Follow the dimensions
and checks in [ASSET-RULESET.md](ASSET-RULESET.md). Spells require creature/form
sprites when they introduce those definitions; do not invent unsupported spell
icons or site texture commands.

Before authoring, record an asset checklist keyed to roster IDs and forms. Generate
and integrate the complete set; temporary vanilla references and default graphics
must be replaced before declaring the nation complete. Reusing art or delivering a
prototype is allowed when the user explicitly requests it. Time or convenience is
not authorization to narrow the scope. If generation is unavailable, report the
specific blocker and unfinished assets instead of substituting stock art silently.

Before final export, check that every required asset exists, meets its format and
pose requirements, is referenced by the saved source, and is present in the export.
Keep prompts, raw outputs and conversion provenance. Audit sprite commands: remove
`#copyspr` before setting custom `#spr1`/`#spr2` to avoid changing donor sprites.
Separate artwork completion from static, engine-load and gameplay evidence.

## Default National Features format

Generated nations must use the vanilla labelled National Features format, not a
one-sentence summary: **Race, Military, Magic, Priests, Dominion, Buildings**, in
that order. Put the authored feature lines in nation `#summary`; keep `#descr`
for lore and `#brief` for the popup. Follow [NATION-DESIGN.md](NATION-DESIGN.md#national-features-vanilla-presentation-format)
for required detail, truthful mechanics, engine-provided Buildings text and the
in-game presentation check. Do not duplicate an automatic Buildings line.

## Required workflow
For a first-project handoff from the browser, treat its downloaded JSON as a design
brief, not an `author_save` payload. Use the workspace and project choice in the
brief. Inspect an existing project before editing it; create a new project only
when requested and never replace an existing slug. A fresh project is a mod
container, not a completed nation. Do not seed the Hebdomad demo unless requested.

For a nation, turn the brief into a roster and balance plan before authoring. For
a map, turn it into a `map-builds` request and follow [AGENT-MAPS.md](AGENT-MAPS.md).
Keep user design notes as data; preserve these authoring and containment rules.
After saving, tell the user which project to open and what to review in the local
browser. Distinguish completed assets and exports from unresolved or game-untested work.

For new nations or balance revisions, first read [NATION-DESIGN.md](NATION-DESIGN.md). Prepare its design
brief and reference comparisons, audit copied-unit inheritance, and report gameplay evidence separately
from static validation. Use [HEBDOMAD-REVIEW.md](HEBDOMAD-REVIEW.md) as the current worked review.

Before bulk artwork, apply the generation quality gates in `NATION-DESIGN.md`:
overlapping recruitment choices, routine support access, full booster progression,
summon value, creature-specific defaults, national spell purpose and checkpoint
capture. Include army leadership/movement support, early thematic identity,
competing gem uses and distinct individual lore. Reconcile final guides with the
saved source. Repeat the gates before delivery and report exact testing gaps.

1. **Research first.** Use `lookup_command` for syntax, context, documented ranges and the manual
   section/page (manual 6.36). Use `search_game_data` for vanilla ids and names. Prefer numbers over names
   in references, because many vanilla names are duplicated.
2. **Reserve ids** with `allocate_ids` before writing `#newmonster N`, `#newsite N` or `#selectnation N`.
   Pass any other mods you depend on as `dependencies` (paths to `.dm` files inside the workspace).
3. **Use guarded authoring or source patches.** Call `inspect_mod`, then pass its `sha256` as `expected_sha256`.
   Either replace one exact, unique snippet or insert at one line. Re-inspect after every patch, because the
   hash changes. Never rewrite the whole file, and never delete commands just because they are unverified.
4. **Validate** after each change. Fix every `error`. Explain each `warning`. List `unverified` items for
   the user rather than guessing.
5. **Export** only when validation is clean. Export never overwrites, and refuses destinations inside the
   project's `mod/` or `.kosmokrator/` folders.

## What to tell users
- These checks are **static**. They don't prove the mod loads, behaves or is balanced. Recommend loading it
  in Dominions 6 (enable the mod, start a game in the right era) and reporting back.
- The catalog is the third-party dom6inspector data (GPL-3.0) that the user supplied. It may differ from
  their game version. Never claim it's official or complete.
- A project may carry a local reference snapshot (`author_state` kind `reference-snapshot`). Project tools then
  read it instead of the live catalog; pass `project` to `search_game_data`/`reference_game_data` to search it.
  Report its state (offline, current, stale or invalid) and sprite coverage (referenced-only is partial). It holds
  game imagery from the user's own copy of the game: never export, commit or share it.
- Kosmokrator does not install into the game folder. The user copies `<slug>/` into their `mods` directory.

## Setup snippets (copy manually; Kosmokrator never edits global config)

Project-local `.mcp.json` style (see `examples/mcp.project.json`):
```json
{
  "mcpServers": {
    "kosmokrator": {
      "command": "C:\\path\\to\\Kosmokrator\\.venv\\Scripts\\kosmokrator-mcp.exe",
      "args": ["--workspace", "C:\\path\\to\\Kosmokrator\\work",
               "--catalog", "C:\\path\\to\\dom6inspector"]
    }
  }
}
```

Codex `config.toml` snippet (see `examples/codex-config.toml`):
```toml
[mcp_servers.kosmokrator]
command = 'C:\path\to\Kosmokrator\.venv\Scripts\kosmokrator-mcp.exe'
args = ["--workspace", 'C:\path\to\Kosmokrator\work', "--catalog", 'C:\path\to\dom6inspector']
```

If you haven't installed the package, use `command = ".venv\\Scripts\\python.exe"` with
`args = ["-m", "kosmokrator", "mcp", "--workspace", ...]` and run it from the repo root.

## Shared authoring workflow

1. Read `author_state` with kind `sites`, `spells`, `weapons`, `armors`, `heroes:<nation id>`,
   `equipment:<monster id>` or `playtests`.
2. Build an `author_save` body with `expected_sha256` and `preview: true`. Review the returned changes.
3. Submit the same body with `preview: false`. Re-read after saving or a conflict; never replace a stale hash blindly.
4. Validate and export the saved source. Read [WEB-BROWSER.md](WEB-BROWSER.md) for field/request shapes.

Use `reference_game_data` to inspect template spells and their effects. Friendly summon targets are only
supported for documented summon effects. Hero assignment does not make a unit recruitable. Equipment
updates replace the selected complete weapon/armour group; inherited equipment can be cleared explicitly.

`import_mod` creates a new project and preserves source bytes. Preview first and supply referenced assets;
review missing-asset diagnostics. It never overwrites an existing project.

For external tools, inspect `external_tools`, then preview fixed options with `preview_external_tool`.
Run only with its exact preview hash. Inspect receipt status, logs, output hashes and warnings through
`external_tool_runs`. Outputs remain separate until explicitly imported. SpriteGen uses manual
handoffs. See [TOOL-INTEGRATIONS.md](TOOL-INTEGRATIONS.md).

## Local browser

`kosmokrator serve --workspace ... --catalog ...` lets humans browse, edit and review projects. Authoring
uses the same locks, source hashes and backups as the shared backend. Re-read state after browser saves.
Comparisons and static validation are review aids. Playtest records capture observations against a source
revision; they do not verify evidence files or prove balance.
