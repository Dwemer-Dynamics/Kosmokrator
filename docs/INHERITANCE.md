# Inheritance evidence

`kosmokrator.inheritance.inheritance_report(model, catalog=None)` accepts the existing
project browser model, not the CLI `ok/result` envelope. It returns a JSON-serializable
`kosmokrator.inheritance/1` report and does not modify the model, source or catalog.
It imports no browser/server modules, so callers can wire it into CLI, MCP or HTTP.

The report includes source/catalog provenance, per-monster ordered `history`, copy
`donors`, final resolver `fields`, unmodelled donor columns, unsupported commands,
`issues`, project-copy `cycles` and counts. History keeps original lines and effects;
trait reset annotations distinguish ended authored settings from retained settings.
Field states are `retained`, `authored`, `cleared`, `unresolved` or `recorded` (status-only
evidence, such as a resolved equipment list). Unresolved item/list evidence takes
precedence over the item's authored or donor origin. Overwritten state
belongs to history entries, because overwritten settings are absent from final fields.

Supply the same catalog used to build the model to identify earlier donors as well as
the final donor. Without it, the final saved donor row can still be identified; earlier
unknown donors remain uncertain. Project-to-project copy chains, forward references,
overlapping project/catalog IDs and cycles are exposed rather than simulated.
Cycle detection includes historical copy commands and does not prove a runtime cycle.

Unmodelled transformation and unusual ability columns keep their resolver confidence.
An ability marked "assumed cleared" is **unresolved**, not confirmed absent. Source
diagnostics can refer to earlier overwritten copies; retain their line references.
No new default values, forging results, transformation behavior or game balance are
inferred. Static evidence is separate from in-game testing.

Integration example:

```python
from kosmokrator.inheritance import inheritance_report
report = inheritance_report(project_model, catalog)
unit_report = next(r for r in report["monsters"] if r["id"] == monster_id)
```

Expose `report` as the result in existing API envelopes. Do not pass a report back as
source-edit instructions: existing guarded authoring/patch APIs remain responsible
for writes and validation.
