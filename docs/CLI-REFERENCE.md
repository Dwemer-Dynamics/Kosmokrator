# Command line and project reference

For your first nation or map, start with [the first-project guide](COMMUNITY-QUICKSTART.md).
This page covers optional installation, direct commands and file handling.

## Install (Windows, project-local `.venv`)

```powershell
py -3 -m venv .venv                          # or reuse an existing .venv
.venv\Scripts\python.exe -m pip install -e .    # core CLI only
.venv\Scripts\python.exe -m pip install -e ".[mcp]"   # plus the MCP server
```

For source-folder use without installation, use a verified Python 3.11+ executable with `-m kosmokrator`. Browser handoffs identify the interpreter and shell. A `.venv` only exists after you create it.

## Game-data catalog (local, supplied by you)

Reference checks and `search` use a local checkout of the third-party
[dom6inspector](https://github.com/larzm42/dom6inspector) repository (GPL-3.0, by larzm42). Kosmokrator
does not bundle or download it, and copies from it only into a project's local reference snapshot when you ask
(see below). Clone it once and point to it:

```powershell
git clone https://github.com/larzm42/dom6inspector C:\data\dom6inspector
$env:KOSMOKRATOR_CATALOG = "C:\data\dom6inspector"   # or pass --catalog on every command
```

Its `gamedata/*.csv` files are tab-separated, and Kosmokrator detects the delimiter. Results include the
catalog path, origin URL, git revision and the dataset version stated in the checkout's `index.html`
(e.g. `[ver 6.37]`); when that marker is absent the dataset version is reported as unknown (`null`). The data is community-extracted and can lag behind or differ
from your installed game. Without a catalog, `validate` still runs, but it reports vanilla references as
`unverified`.

A project can carry its own **reference snapshot** (`author PROJECT reference-snapshot` shows its status; with a
`--body-file` of `{"expected_sha256", "expected_snapshot", "sprites": "referenced"|"all", "preview"}` it previews or
writes one from the live catalog). It holds every catalog table, the catalog licence and the local reference art the
project needs under `<project>/.kosmokrator/reference/`, with a manifest of sources, versions and hashes. Project
commands (`validate`, `export`, `allocate`, `author`, and `search`/`reference` with `--project`) then read the
snapshot instead of `--catalog`, never both. It includes game imagery extracted from your own copy of the game: it is
local only and is never written into exports. See [WEB-BROWSER.md](WEB-BROWSER.md#reference-snapshot-self-contained-project).

## Starter demo

`demo` creates the lightweight starter nation (13 definitions, including two pretenders).
The expanded local Hebdomad showcase has 21 definitions and a separate SevenRealms map;
it is not reconstructed by this command or included in the Python wheel. Neither demo is
game-verified. A wheel installation includes web resources; the repository's `docs/` directory
is optional source-checkout content supplied with `serve --docs`.

For optional coordinated project work, see [Agent team workflow](AGENT-TEAM.md).
See [Community preview readiness](COMMUNITY-READINESS.md) for current evidence and release gaps.

```powershell
mkdir work
$K = ".venv\Scripts\kosmokrator.exe"            # or: .venv\Scripts\python.exe -m kosmokrator

& $K demo --workspace work                      # builds work\hebdomad via the core operations
& $K validate hebdomad --workspace work         # exit 0 clean, 1 errors, 2 operation error
& $K export hebdomad --workspace work           # -> work\hebdomad\exports\hebdomad-<utc>.zip + .manifest.json
& $K export hebdomad --workspace work --format folder --dest hebdomad_out
```

To try the demo in game, copy the exported `hebdomad` folder (which holds `hebdomad.dm` and `art/`) into
your Dominions 6 user-data `mods` folder (*Game Tools > Open User Data Directory*, usually
`%APPDATA%\Dominions6\mods`). Then enable the mod and start an **Early Age** game. Kosmokrator never
copies files into the game folder itself.

### Commands

| CLI | MCP tool | Purpose |
| --- | --- | --- |
| `create SLUG` | `create_project` | New project; refuses to overwrite |
| `inspect PROJECT` | `inspect_mod` | Non-mutating parse: sha256, blocks, definitions, unverified commands |
| `patch PROJECT --expected-sha256 H (--old-file F --new-file F \| --insert-line N --text-file F)` | `apply_mod_patch` | One exact replacement or one insertion, with a backup and a diff |
| `lookup [CMD] [--context]` | `lookup_command` | Curated syntax/context/ranges with manual section and page |
| `allocate PROJECT KIND [N] [--label] [--dep]` | `allocate_ids` | Reserve free ids in documented ranges |
| `search QUERY [--category] [--limit] [--project]` | `search_game_data` | Offline catalog search by id or name (max 50 results); `--project` searches that project's snapshot if it has one |
| `validate PROJECT [--dep]` | `validate_mod` | Errors, warnings and unverified items, each with file and line |
| `export PROJECT [--dest] [--format zip\|folder]` | `export_mod` | Error-free export with a sha256 manifest; never overwrites |
| `demo [--export zip\|folder]` | (CLI only) | Builds the Hebdomad demo |
| `author PROJECT KIND [--body-file JSON]` | `author_state`, `author_save` | State or preview/save sites, spells, weapons, armors, heroes:N, equipment:N, playtests, reference-snapshot |
| `reference CATEGORY [QUERY] [--id N] [--project]` | `reference_game_data` | Inspect spell, site or equipment catalog references |
| `import-dm SOURCE --slug SLUG [--preview]` | `import_mod` | Copy an existing mod and supplied assets into a new project |
| `tools status\|preview\|run\|history\|receipt` | external tool operations | Fixed optional adapters, fingerprinted previews and diagnostic receipts |
| `mcp` | n/a | Starts the MCP stdio server |

Global options: `--workspace/-w` (an explicit root that contains projects, dependencies and export
destinations), `--catalog` (an explicit, read-only source that may live outside the workspace),
`--target-version` (default `6.37`; recorded in new projects) and `--json`.

## Project layout

```
<workspace>/<slug>/
  kosmokrator.json            metadata, target version, id reservations
  mod/<slug>/<slug>.dm        authoritative source
  mod/<slug>/...              assets referenced by the .dm (relative, forward slashes, case-sensitive)
  .kosmokrator/backups/       pre-patch copies (git-ignored)
  .kosmokrator/reference/     optional local reference snapshot (git-ignored, never exported)
  exports/                    default export target (git-ignored)
```

## Safety properties

- Patches require the file's current SHA-256. A replacement must match exactly once. Untouched bytes,
  the encoding (UTF-8, or latin-1 when the file isn't valid UTF-8) and the newline style are preserved.
- Project files, dependency `.dm` files and export destinations must be inside the workspace (and asset
  paths inside the mod folder); Kosmokrator rejects `..`, absolute paths, backslashes in `.dm` paths, and
  symlinks/junctions in project, source, backup and state paths. Two kinds of input are read from wherever
  you point them, read-only: the `--catalog`/`KOSMOKRATOR_CATALOG` checkout and the CLI's `--old-file`,
  `--new-file` and `--text-file` inputs. This is path checking in the tool, not an OS sandbox for the
  process.
- Export writes only to a fresh destination inside the workspace and never into the project's
  source or state folders. The output holds exactly `<slug>/<slug>.dm` plus the referenced assets.

## Local web browser and monster editor

`serve` starts a loopback-only browser for the projects in a workspace. It shows nations, units with
sprites, donor inheritance, resolved fields, sites, assets, validation, source and docs. **Edit values** on a
project monster or pretender changes curated stats, magic paths, god fields and traits in that block of the
`.dm`, after a review step, with a backup and a stale-file check. Additional editors cover nations, equipment, sites, spells, heroes, maps and supported command contexts; see the browser guide for their scope.

**Edit nation** (Nation tab) changes identity, fort roster, gods, realms, start sites and start army of an
existing `#selectnation` block the same way, never adding resets. **Compare with vanilla units** shows a project
unit beside one or two catalog units (read-only, no balance score). See
[docs/WEB-BROWSER.md](WEB-BROWSER.md#edit-an-existing-nation).

Authoring workflows in the same browser, each reviewed as a diff before writing: **New unit / New god / Duplicate**
(Units and Pretenders), **New nation** (Nation tab) and **Artwork: upload or replace frames** (PNG idle/attack
frames on a project monster). Ids come from the core allocator; writes use the project lock, the expected SHA-256
and a backup. See [docs/WEB-BROWSER.md](WEB-BROWSER.md#authoring-create-duplicate-nations-artwork).

```powershell
.venv\Scripts\python.exe -m kosmokrator serve --workspace work --docs docs --port 8765
```

Open <http://127.0.0.1:8765/>. See [docs/WEB-BROWSER.md](WEB-BROWSER.md) for the JSON API, what
"resolved" covers and its limits.

## MCP

See [docs/AGENT_USAGE.md](AGENT_USAGE.md) for agent instructions and config snippets:
[examples/mcp.project.json](../examples/mcp.project.json) (project-local `.mcp.json` style) and
[examples/codex-config.toml](../examples/codex-config.toml). Kosmokrator does not edit any global agent
configuration.

