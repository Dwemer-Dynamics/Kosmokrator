# Nation comparison reports

`kosmokrator.balance.balance_report(model, catalog, reference_nations=None)` produces
read-only JSON comparison tables from the existing browser model. It never edits a
project, computes a universal power score or declares a nation balanced.
Use [NATION-DESIGN.md](NATION-DESIGN.md) to choose useful references and interpret results.

## Contract

The response schema is `kosmokrator.balance/1`:

- `provenance`: project source revision and catalog metadata.
- `project_nations`: each nation with its resolved recruits, magic access, gem sites and summons.
- `reference_nations`: selected same-era catalog nations and their recruitment/magic tables.
- `selection`: requested IDs, selection mode and available same-era catalog nations.
- `warnings`: missing catalog tables and unresolved catalog recruits.
- `limitations`: scope and verification boundaries.

Pass an explicit list of up to 12 integer catalog nation IDs. An empty list disables
reference comparisons. Invalid IDs or nations outside every project nation's era
raise `KosmoError('bad_value', ...)`. With no explicit selection, the first three
catalog nation IDs per project era are used. This deterministic default is a
convenience, not a claim that those nations are the best benchmarks. In a project
containing several eras, compare each nation to references of its own era.

Without a catalog, project information remains available and the response warns that
vanilla references and copied spell templates cannot be verified. A project without
known-era nations has no default references. The function accepts an unwrapped
browser model, not the CLI's `ok` response envelope.

## Recruitment and costs

Each unit row has `raw_costs`, `cost_estimates`, `stats`, `equipment`, `protection`,
`equipped`, `fixed_paths`, `random_magic`, `recruitment` and source information.
Raw cost records retain their authored/inherited components, interpretation and
line provenance. A value such as `10010` is an autocalculation encoding, not a
10,010-gold recruitment price. Autocalculated final gold remains unresolved.

Equipment and protection reuse the existing conservative equipped-sheet estimator
for project and reference units. Its `status` and `note` travel with the values.
Resource estimates include supported equipment scaling, but mounts and conditional
economy effects can leave values unresolved. Fixed gold components are not a promise
that every game adjustment has been included. Do not replace unresolved values with
zero or silently compare a raw component to another unit's estimated total.

Catalog recruitment includes fort, nonfort and coast tables. Capital-only units are
read from attribute 52 (capital magic site), then `hmon1..5` / `hcom1..5` in
`MagicSites.csv`. Conditional nation mechanics, special site recruitment outside
these fields and inherited vanilla nation rosters in project selectors are not
fully reconstructed. Project rows list resolved project definitions associated
with recruitment; heroes, summons and pretenders are not treated as normal recruits.

## Magic and summons

`magic_access.recruitable_mages` keeps paths and recruitment restrictions per recruit.
`fixed_maxima` reports the maximum fixed level in each path. Those maxima can belong
to different units and do not prove crosspath access. Random metadata preserves
mask, chance, linked levels and count. Only one-level authored picks with a chance
from 0 to 100 receive `per_path_probability`, assuming equal selection among paths.
Combined picks and catalog-linked/count probabilities remain unexpanded.

Summons resolve supported copied or authored effects in source order. Each row
includes research school/level, path requirements, national restrictions, target,
raw fatigue/count, gem cost and an optional `gems_per_unit`. Ratios are produced
only for simple ritual troop/commander effects 10001 and 10021 with a known target,
plain positive count below 500, no caster-level scaling or chained spell, and an
integral fatigue/100 gem cost. Other supported summon effects remain visible with
an unresolved ratio. Encoded counts such as 1002 are never treated as 1,002 units.

The report does not model discounts, boosters, empowerment, caster frequency,
upkeep, fatigue scripting, combat, expansion or production investment. It makes no
in-game verification claim. Compare source revisions and record separate game
observations before drawing numerical balance conclusions.
