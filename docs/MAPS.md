# Maps and scenarios

Before creating or rebuilding geography, read the [map building ruleset](MAP-DESIGN.md).
For generated terrain and winter variants, use the [layer inventory and generation rules](MAP-LAYERS.md).

Kosmokrator keeps maps under `<project>/maps/<MapName>/`, separate from the authoritative `.dm` mod.
Use the **Maps** tab to import a bundle, select a plane and province, edit its settings, review changes and
save. Map export creates a separate ZIP with installation instructions and a file-hash manifest.
Nothing is installed or uploaded to Steam automatically.

The local Hebdomad project includes **SevenRealms**, an illustrated coastal example at 1600x1000 with
21 land and 9 ocean provinces, one lower-plane forge, a linked gateway and named Hebdomad defenders. Its existing `.dm` and
unit artwork are unchanged. The example is for exercising the editor; it has not been tested in game.

## Research and format

Primary references: Illwinter's [Map Making Manual 6.26](https://www.illwinter.com/dom6/dom6mapman.pdf)
and [Dominions 6 File Formats](https://www.illwinter.com/dom6/dom6fileformats.pdf).
The shipped `data/nexus.map` and `data/inferno.map` were inspected read-only as practical examples.

- A `.map` contains text commands, comments and ordered scenario instructions. `#dom2title` comes first;
  `#imagefile` and `#mapsize` identify its geography.
- Hand-drawn maps use 24/32-bit TGA artwork. Pure-white single pixels define province centres. Other white
  artwork should use off-white. `#pb x y length province` stores horizontal ownership spans, needed for
  province selection and dominion overlays. Kosmokrator reads these spans and preserves their source.
- Generated maps can use `.d6m` geography recipes. The published v3 specification supplies dimensions,
  province coordinates, heightfield and province ownership. Kosmokrator reads coordinates and validates
  the binary length and markers. It shows a schematic; it does not reproduce the game's terrain renderer.
  The installed Inferno example uses v1, which is preserved with a warning and no decoded coordinates.
- A map can have up to eight planes. Additional files use `<MapName>_plane2.map`, and so on. Each plane
  has its own geography and local province view. `#gate` numbers link gateways; cross-plane travel and
  special-start numbering are preserved but not simulated.
- Terrain graphics (manual p.10, "Terrain Graphics") use the map basename: `_winter.tga` for the default
  winter look and `_plain`, `_forest`, `_waste`, `_farm`, `_swamp`, `_highland`, `_kelp` and `_water`, each
  with an optional `w` winter suffix (`_forestw.tga`). Other planes put the plane part first
  (`_plane2_waste.tga`). Missing looks use the default image. Imported variants are included unchanged in export.
- Map terrain masks differ from magic-site/mod terrain masks. Use the map-specific checkbox list.
  The cave-wall flag is 2^36; browser editing uses arithmetic rather than 32-bit JavaScript bitwise operators.
- `#neighbour` creates a two-way connection. Reviewed `#neighbourspec` types are standard (0), mountain
  pass (1), river (2), impassable (4) and road (8). Impassable connections are excluded from the static
  movement-component check. This check does not model sailing, flying, gates, spells or seasonal access.
- `#start` recommends a starting province; no-start overrides it. `#specstart` assigns a nation when the
  game's special-start option is enabled. Duplicate and adjacent special starts get static warnings.
- `#setland` selects a province without clearing its occupants. `#land` clears them, which can kill a
  starting pretender. Structured scenario additions always use `#setland`.
- Custom mod monsters must be placed by quoted name, not numeric monster ID, in `#commander`, `#units`,
  `#bodyguards` and `#god`. Items use names. Site commands accept names or numbers. Required mods still
  need to be enabled when creating a game.

## Import and safety

Select the main `.map` and its asset/plane files together. The main basename must match the bundle ID.
Files stay flat, retain exact case and use letters, digits and underscores. The browser accepts uploaded
files rather than arbitrary paths. CLI imports copy only sibling variants, planes and referenced assets;
the original source is untouched. Symlinks, traversal, duplicate/case-colliding names and oversized bundles
are refused. Limits: 160 files, 128 MiB total, 16 MiB per `.map`, 16 megapixels of preview geometry.

Import defaults to preview and refuses to overwrite an existing bundle. Static errors block final import
and export. Unknown commands remain visible as warnings. RGB assets are preserved, but not previewed.
`#pb`, image references, map size, `#land` and `#setland` are read-only in the generic command editor.

Saves use source offsets, keeping comments, unknown commands, encoding, untouched bytes, artwork and
area spans. The revision hashes every bundle file, not just the selected plane. Saving checks that revision
under the project lock, backs up the previous source and atomically replaces it. Stale drafts require a
fresh review. Commander modifiers must follow a commander added in the same province and request.

## Terrain look preview

On a TGA plane, **Terrain look** chooses Default or one of the eight documented looks, and **Winter** picks
its `w` (or `_winter`) image. With a province selected, the look is clipped to that province's `#pb` area and
the rest of the map is dimmed; **Whole map** (or no selection) shows the full image. **Reset preview**
returns to the saved image. Options missing from the bundle are labelled and show the default image.

The preview is held only in the page. It never changes province `#terrain`, the draft, geography,
artwork, starts, gates or export. It does not decide when the game shows a look: there is no temperature,
season or terrain simulation. The plane image route accepts `look=<name>&winter=0|1`; names come from
the fixed list, and an absent or unusable variant (wrong size or format) falls back to `#imagefile`.
Plain `?plane=N` requests are unchanged. Map state lists every variant per plane with its file,
availability and reason.

## Agent and CLI access

The same operations are available to Claude/Codex through MCP and the CLI:

```powershell
kosmokrator import-map hebdomad C:/Maps/SevenRealms/SevenRealms.map --workspace .local/projects --json
kosmokrator import-map hebdomad C:/Maps/SevenRealms/SevenRealms.map --workspace .local/projects --save --json
kosmokrator author hebdomad maps --workspace .local/projects --json
kosmokrator author hebdomad maps:SevenRealms --workspace .local/projects --json
kosmokrator author hebdomad maps:SevenRealms --workspace .local/projects --body-file map-edit.json --json
kosmokrator export-map hebdomad SevenRealms --workspace .local/projects --expected-revision <revision> --json
```

MCP: `import_map`, `export_map`, `author_state(kind="maps" | "maps:<id>")`,
`author_save(kind="maps:import" | "maps:<id>")`. HTTP routes live under `/api/projects/<slug>/maps`.

Example edit request:

```json
{
  "expected_revision": "<whole-bundle revision>",
  "preview": true,
  "plane": 1,
  "changes": [
    {"op": "province", "province": 1, "name": "The Brass Forge", "terrain": 65600},
    {"op": "connection", "a": 1, "b": 2, "kind": 1},
    {"op": "add", "command": "knownfeature", "args": ["A custom site"], "province": 1},
    {"op": "add", "command": "commander", "args": ["A custom commander"], "province": 1},
    {"op": "add", "command": "units", "args": [12, "A custom troop"], "province": 1}
  ]
}
```

Review the returned diff, then repeat with `preview:false` and the original expected revision.
Generic `replace`/`remove` operations address the current statement's line; replacements keep its command.

## Export and limits

Extract the exported map folder into `%APPDATA%/Dominions6/maps` on Windows, or the equivalent game data
directory on other systems. Enable the mod and required dependencies separately. Export preserves every
bundle asset, with a separate `INSTALL.txt` and `kosmokrator-map-manifest.json` outside the map folder.

This first version edits existing map geography. It does not paint province areas, generate new terrain,
render `.d6m` scenery, publish Workshop items or invoke MapNuke. MapNuke output can be imported as ordinary
map bundles; an automated runner would require separate investigation.
Static validation and browser checks do not prove the map loads or is balanced. In-game testing was
explicitly skipped for this implementation.
