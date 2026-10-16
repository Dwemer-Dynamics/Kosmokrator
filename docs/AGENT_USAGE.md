# Agent usage

Follow the workflow below, then use the task guides for detailed criteria.
A single coding agent is enough. [Specialist coordination](AGENT-TEAM.md) is optional.

## Authoring workflow

1. **Establish scope:** read the user's brief and supplied answers. Choose the task
   guides linked from `AGENTS.md`. A browser download is a design brief, not an
   `author_save` request. Inspect existing projects; create a new slug only when
   requested, never overwrite another project or seed a demo without a request.
2. **Plan and research:** apply the nation or map brief and quality gates before
   bulk assets. Research commands with `lookup_command`; inspect available vanilla
   references and record versions. Reference data is optional; disclose missing
   comparisons rather than inventing them. Reserve IDs with `allocate_ids` in the
   project and declared dependency scope before writing definitions. Never hardcode
   a customary starting ID such as the first nation slot; use the reserved numbers.
   Allocation also skips IDs defined or reserved by other workspace projects and
   defined by installed mods (read-only scan of the configured mods folder). Read its
   `checked` scope and caveats, and review dependency and installed-mod conflicts for
   every ID kind. Nation IDs are drawn at random from the free range; that lowers,
   but never eliminates, collisions with unscanned mods.
3. **Build with guarded changes:** inspect current source/state first. For patches,
   use the current `expected_sha256`, exact unique replacements or line insertions;
   re-inspect after each patch. Never rewrite the whole `.dm` or remove unknown
   commands merely because they are unverified. For `author_save`, preview, inspect
   the changes, then save the same request. Re-read after conflicts/browser edits.
   Map jobs use their documented bundle and output revisions instead.
4. **Complete presentation:** follow [asset rules](ASSET-RULESET.md) and
   [sound defaults](SOUND-DESIGN.md). Track every required asset and inherited sound
   choice. Apply the detailed generation and presentation requirements below.
5. **Validate and deliver:** fix errors after each change; explain warnings and
   unverified results. Apply [the completion checklist](COMPLETION-CHECKLIST.md),
   export the reviewed revision to a fresh destination, and report precise evidence
   and remaining limits. User testing restrictions take precedence over game checks.

## Setup

The source-folder CLI works without installation or MCP. Follow
[the quickstart](COMMUNITY-QUICKSTART.md) for Python, interpreter/shell selection,
workspace paths and optional MCP configuration. Use its linked configuration
examples rather than duplicating them here. A catalog is optional.

Record the installed release/tag or source commit and any local documentation
overrides. Editing these docs locally does not update a published release ZIP.

## Capabilities and task details

Read-only `author_state` kinds now include `inheritance`, `compatibility`, `balance`
and `balance:<nation IDs separated by commas>`. These return source-backed reports;
they do not change the mod or simulate combat. Kind `revisions` lists local checkpoints; `revisions:<id>` and
`revisions:baseline` compare them with the current files. Before larger work, `author_save` kind `revisions`
`{"action": "checkpoint"}` lets the user review or undo it; mark reviews with your true `reviewer_kind` (`agent`)
and never claim a human review. Restores are preview-then-apply with `plan_hash` and `confirm`. Kind `health` (CLI `health`) returns one prioritized, deduplicated
finding list with stable ids, locations, evidence, next actions, recruitment classes, scope and caveats for a
captured revision; read its `not_checked` scope before reporting a project as healthy. See [inheritance](INHERITANCE.md),
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

## What to tell users
- These checks are **static**. They don't prove the mod loads, behaves or is balanced. Recommend loading it
  in Dominions 6 (enable the mod, start a game in the right era) and reporting back.
- The catalog is the third-party dom6inspector data (GPL-3.0) that the user supplied. It may differ from
  their game version. Never claim it's official or complete.
- A project may carry a local reference snapshot (`author_state` kind `reference-snapshot`). Project tools then
  read it instead of the live catalog; pass `project` to `search_game_data`/`reference_game_data` to search it.
  Report its state (offline, current, stale or invalid) and sprite coverage (referenced-only is partial). It holds
  game imagery from the user's own copy of the game: never export, commit or share it.
- Regular exports do not install themselves. Copy `<slug>/` into the game’s `mods` directory, or use the optional guarded local installation described in [WORKSHOP.md](WORKSHOP.md).

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

`kosmokrator serve --workspace ...` (optionally add `--catalog`) lets humans browse, edit and review projects. Authoring
uses the same locks, source hashes and backups as the shared backend. Re-read state after browser saves.
Comparisons and static validation are review aids. Playtest records capture observations against a source
revision; they do not verify evidence files or prove balance.

## Completion

Use [the shared completion checklist](COMPLETION-CHECKLIST.md). Keep project-specific
evidence in the project, not in these reusable instructions.
