# Compatibility guidance

Kosmokrator reviews **declared dependency files in metadata order, followed by the current project**. This is a static model. Saving dependency settings does not activate mods or change Dominions' actual mod order. Unlisted enabled mods remain unknown.

## Read the report

`project_view` / `kosmokrator view` returns `compatibility` alongside the existing `relationships` graph. Existing `activation_order`, `overlaps`, `warnings` and `limitations` remain available.

Each overlap adds:

| Field | Meaning |
| --- | --- |
| `classification` | `hard_id_collision`, `intentional_selector_override`, or `ambiguous_named_definition` |
| `contributors` | Ordered block keys, file origins, opener commands and 1-based source lines; catalog baseline when known |
| `last_contributor` | Last authored block in this overlap's history |
| `winner` | Last selector contributor when no duplicate new-ID collision makes the target unsafe; otherwise null |
| `blocked_by_collision` | An earlier or current duplicate numbered new definition makes order insufficient to resolve the identity |
| `effects` | Ordered authored statements grouped by command, with arguments, source lines and `last_authored` statement |
| `actions` | Concrete review/remap/dependency/reorder suggestions; every action has `automatic: false` |

`winner` is a convenient order label, **not a whole-object replacement**. Earlier fields may survive. Copies, clears, list additions, repeated commands, unsupported semantics and runtime effects can change the effective result. `effects` reports evidence rather than pretending to simulate all those effects. Each overlap is a history snapshot at that point; the last overlap for the identity includes its latest contributor.

A numbered `#new*` reusing an already known identity is a hard collision. Reordering cannot make two independent definitions safely share an ID. Reserve a replacement with all intended dependencies declared, review every typed reference, make guarded targeted source edits, then validate again. Kosmokrator never remaps source IDs by itself: `author_state` kind `remap` lists owned IDs and free targets, and `author_save` kind `remap` previews a typed, reviewable plan that applies only with its plan hash and `confirm`. `allocate_ids` also skips IDs used by other workspace projects and installed mods' `.dm` files and reports what it could not read; mods outside that scan (for example Workshop subscriptions or other players' mods) remain unknown, and random nation IDs only reduce that risk.

A `#select*` block explicitly addresses a shared identity. Its classification describes selector syntax; it does not infer the author's intent or promise the combination is harmless. Review its commands and order. A later selector cannot repair an earlier hard collision. Nation creation commonly uses `#selectnation` in the documented custom range, so selector classification alone cannot prove two independently authored nations intentionally share an ID; review names, clear commands and source provenance.

Unnumbered named definitions can overlap by name without proving a hard numeric-ID collision. Such overlaps and ambiguous references require manual review. Prefer verified numeric targets where the command supports them.

## Resolve a reference or order problem

The additive `summary` counts hard collisions, selector overlaps, ambiguous named definitions, unresolved references and order-sensitive references. `guidance` links uncertain references to their source, command, argument and safe actions.

- **Missing or unverified target:** check spelling, numeric ID, typed context and catalog version. If another mod provides it, declare that dependency and rerun the catalog-backed project view.
- **Ambiguous target name:** inspect competing identities and use the intended verified numeric ID where supported. Do not guess which name the engine will select.
- **Copy target authored later:** a final graph edge may resolve while a copy command still lacks its donor at that point in the declared order. Move the provider before its consumer and recheck. This conservative check does not simulate every engine load-time behavior.
- **Competing selectors:** preview an explicit dependency reorder and inspect the changed last contributor/statements. The current project remains last. Match the intended order in Dominions separately.
- **Duplicate numbered new definitions:** declare dependencies before allocating replacement IDs; remap and review all relevant references. Do not treat reorder as a collision fix.

## Preview and save dependency order

Use existing CLI/MCP `author_state(project, 'dependencies')` and `author_save(project, 'dependencies', body)` operations. The body remains:

```json
{
  "expected_sha256": "<current metadata SHA from author_state>",
  "preview": true,
  "dependencies": ["provider/mod/provider/provider.dm", "patch/mod/patch/patch.dm"]
}
```

Paths stay within the explicit workspace. Existing duplicate-path, self-dependency, stale-hash, lock, backup and atomic-write safeguards remain. Preview changes neither source nor metadata; save changes only project metadata. Reorder the same array to review another candidate order. Save with `preview: false` only after reviewing the diff and use the current metadata SHA.

Dependency state adds `declared_order`; preview/save adds the candidate `compatibility` report. The dependency editor's existing API does not supply a catalog, so its report has `catalog_available: false` and labels that limitation. A vanilla reference unresolved in that preview is **not proven missing**. Use the catalog-backed project view before deciding to change source. This feature does not require UI changes; existing consumers can ignore the additional JSON fields.

No operation in this workflow changes source IDs automatically, launches the game, enables mods or proves runtime compatibility.
