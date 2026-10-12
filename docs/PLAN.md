# Historical implementation plan

This records the initial architecture, not current feature coverage or release readiness.
Use [AGENT_USAGE.md](AGENT_USAGE.md) and [CLI-REFERENCE.md](CLI-REFERENCE.md) for current workflows.

## Goals
A small, complete, stdlib Python package. The CLI and an optional MCP stdio server share one set of
core operations (`kosmokrator/core.py`). The `.dm` file is the single source of truth, and nothing
re-serialises it.

## Sources used
- *Dominions 6 Modding Manual* ver 6.36 (local extract): syntax (p.3), mod info (p.5), monsters (pp.13-36),
  sites (pp.37-41), nations (pp.41-50) and number limits (p.64).
- Game 6.37 `--help` output (local) for the version string. The tool does not depend on the game's behaviour.
- dom6inspector `gamedata` (local checkout, rev 68904be). The `.csv` files are tab-separated.

## Modules
| Module | Role |
| --- | --- |
| `dmparse.py` | Offset-preserving parser: commands, quoted multi-line strings, `--` comments, blocks/#end, definitions |
| `commands.py` | Curated command table (context, args, documented ranges, section/page) plus lookup |
| `docindex.py` | Command *names* per manual section (monster/site/nation), used for context checks |
| `catalog.py` | Lazy offline catalog loading, delimiter/encoding detection, git metadata from `.git`, capped search |
| `project.py` | Create, inspect, guarded patch (sha256, single edit, backup, diff, lock), id allocation |
| `validate.py` | Syntax, context, ranges, ordering rules, duplicates/ids, references, assets |
| `images.py`, `tga.py` | PNG/TGA header checks and the demo's stdlib flag writer |
| `export.py` | Error-free export (zip or folder) plus a sha256 manifest beside the mod folder |
| `demo.py` | Hebdomad build through the core operations |
| `cli.py`, `mcp_server.py` | Front ends |

## Key decisions
- **Severity:** an `error` means the manual or catalog marks something as invalid, and blocks export. A
  `warning` means the construct is legal but risky. `unverified` covers anything outside the curated subset
  and is kept verbatim. Ranges are only enforced when the manual states them.
- **Context errors:** a curated command used in another core block (for example `#startsite` in a monster
  block) is an error. A command the manual documents only in another section raises a warning.
- **Id ranges:** monsters 5000-8999 (the stricter #newmonster text; the limits table allows up to 19999 and
  triggers a warning), sites 1700-3999, nations 150-499, weapons 1000-3999, armor 400-1999. Spells and items
  are created without numbers, so the tool can't allocate them.
- **Allocation:** takes the project lock, then avoids the catalog, the project `.dm`, explicit dependency
  `.dm` files (inside the workspace) and earlier reservations. Reservations are written atomically to
  `kosmokrator.json`.
- **Asset paths** resolve relative to the mod folder, with every component matched case-sensitively.
  Kosmokrator rejects symlinks and junctions everywhere.
- **Export** writes the manifest outside the `<slug>` mod folder: beside the zip, or at the root of the
  export folder.

## Known limits
- No proof of in-game loading, behaviour or balance; no checks on weapon, armor, spell, item or event grammar.
- The catalog may differ from the installed game. Mods that aren't listed as dependencies aren't checked
  for conflicts.
- `#newnation` and unnumbered `#newmonster`/`#newsite` are reported as unverified (the game picks the id).
