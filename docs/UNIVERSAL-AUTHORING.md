# Universal authoring foundation

Kosmokrator supports nine editing contexts: monsters, nations, sites, spells, weapons, armour, items,
mercenaries and events. Dedicated forms remain the quickest way to edit common fields. **Advanced tools → All manual commands** exposes the wider manual command index. Use the **Tool** selector
for Weapons, Armour, Heroes, Events, Reference lookup and Playtests. Spells, Sites, Items and Mercenaries
are edited in their own content sections; raw line editors are labelled **Advanced**.
Common-field editors appear near the definition heading; raw catalog details stay collapsed until needed.
Mercenary companies also have **Mercenaries → New company** with a structured form; it
writes names for `#com`, `#unit` and `#item` as manual p.63 documents, and the advanced editor refuses numbers for
those three. Agents use `author_state`/`author_save` with kind `mercs` for the same structured path.

## Command coverage and safe saves

The index uses Illwinter's [Modding Manual](https://www.illwinter.com/dom6/dom6modman.pdf) and
[Event Modding Manual](https://www.illwinter.com/dom6/dom6eventman.pdf), version 6.36. Each indexed command
has its printed signature or reviewed schema, description and page. Terrain, hero and underwater-defence
families are expanded. The checked-in data is `kosmokrator/manual_commands_data.py`; reviewed schemas in
`commands.py` and `traits.py` take precedence. `manual_commands.py` normalizes the index for editors.

Coverage means access to documented command forms, **not** complete simulation of every command's effect.
Some names have no established editable signature; those remain read-only. Newly introduced commands
outside the 6.36 manuals remain visible as source and unverified. Table-derived signatures are distinguished
from reviewed schemas. The supplied catalog's game version is reported separately.

An edit addresses a block and individual statement lines. Repeatable and multi-argument commands can be
added, replaced or removed individually. Unknown statements, comments, encoding and unrelated blocks are
preserved. Text arguments are quoted; embedded quotes and NUL are refused. Review shows the exact diff.
Saving checks the loaded SHA-256 under the existing project lock, makes a backup and replaces the file
atomically. Stale-file errors retain the browser draft. Deleting an entire block requires preview and is
refused while known references use it. New explicit IDs are checked against project, dependency and catalog
identities. Automatic game-assigned IDs remain unknown offline; unique names are important.

## References and compatibility

Unit, site and definition details have **Used by** and **Uses** sections. JSON adds `relationships.objects`,
`edges` and `unresolved`, plus per-object `used_by`, `uses` and `identity`. References include documented
typed arguments, supported inherited equipment and event-code requirements. Dependencies and vanilla
targets show their origin and remain read-only here. Import a mod as a separate project to edit it.

Compatibility lists the explicit dependency order followed by this project, selector overrides and
conflicting new identities. Repeated selectors are intentional extensions; repeated new IDs are conflicts.
The dependency settings editor accepts other imported projects or workspace `.dm` paths, with ordering,
preview, metadata SHA check and backup. Changing a dependency invalidates the project's cached view.
Dependency contents are not bundled into exports automatically; enable those mods in the same order in-game.

This is an explicit, flat activation list. It does not discover every mod enabled in Dominions, follow other
projects' metadata recursively or simulate all source-order effects. Runtime spell summons, arbitrary
event logic, montags and unrecognized commands can add references the graph cannot prove. The deletion
guard protects known references, not all possible game behavior.

## Equipped unit sheets

Supported base fields are layered through dependency definitions, local selectors and `#copystats` chains
in source order. Custom equipment can supply the same fields as catalog equipment. The original catalog
is never modified. Supported copies, equipment clears and magic-path changes are carried into later donors;
unmodelled commands still require source review.

Sheets add armour head/body/average protection, melee attack per weapon, static dual-wield adjustments,
equipment defence and melee encumbrance. Ranged weapons use precision rather than melee attack. Resource
estimates add weapon/armour resources scaled by resource size. Fixed gold and explicit recruitment points
are shown where supported. Encoded autocalculation, mounts and unavailable fields remain unresolved.
Mounts and forms show their referenced identities without simulating transformations.

Estimated values carry `status: "estimated"` and **≈** in the browser. Missing values remain null and fall back
to labelled base values; they never become zero. These are static estimates before conditional abilities,
blesses, spells, combat penalties and special economy rules. Confirm important values in the installed game.

## Agent and CLI access

The existing `author_state` / `author_save` MCP tools accept `commands:<context>` and `dependencies`.
`project_view` returns the same sheets, graph and compatibility report as the browser.

```powershell
kosmokrator author sample_mod commands:item --workspace .local/projects --json
kosmokrator author sample_mod commands:event --workspace .local/projects --body-file request.json --json
kosmokrator author sample_mod dependencies --workspace .local/projects --json
kosmokrator view sample_mod --workspace .local/projects --catalog .local/references/dom6inspector --json
```

Command request shape:

```json
{
  "expected_sha256": "<source SHA>",
  "preview": true,
  "context": "item",
  "mode": "new",
  "opener": {"command": "newitem", "args": []},
  "changes": [
    {"op": "add", "command": "name", "args": ["Brass Seal"]},
    {"op": "add", "command": "constlevel", "args": [2]}
  ]
}
```

For existing blocks use `mode: "edit"`, the returned `target` key and operations `add`, `replace` or `remove`.
Replace/remove use the current statement's `line`. Always preview, inspect the diff, save, then validate.
Dependency requests use the **metadata** SHA rather than the `.dm` SHA.

## Verification boundary

Existing tests plus disposable fixture probes cover safe writes, dependencies, named selectors, donor
chains, references, event links, ID collisions, equipment and unknown-line preservation. Browser evidence
is recorded separately. A successful build or static check does not prove game loading or balance.
