# Nation design and balance criteria

Scope: new nations and nation revisions built with Kosmokrator. These are human-approved design criteria from the October 7, 2026 research review. They guide authoring and review; they are not automatic balance checks or a universal tier formula.

## Required design brief

Before building a nation, record:

- Target game version, era, vanilla or overhaul baseline, and intended single-player/multiplayer use.
- One sentence describing what the player does differently with this nation.
- How its mythology affects recruitment, armies, magic or strategic decisions.
- Main strengths, meaningful weaknesses and practical counters available to opponents.
- Opening expansion plan, first-war research targets and later development options.
- At least three same-era vanilla references, with sources and reasons for choosing them.

Keep facts, community reports, design proposals and untested hypotheses explicitly separate. Record source dates/version context; a Dom5 guide, another era or an overhaul is not a direct Dom6 vanilla benchmark.

## Design criteria and prevention checks

| Criterion | Prevention check before declaring the design ready |
| --- | --- |
| Clear playstyle | Explain the normal army, research and economy decisions in one sentence. Identify at least one recurring decision shaped by the theme. |
| Useful roster | Give each troop and commander a recruitment purpose. Compare alternatives under gold, resources, recruitment capacity and upkeep; flag choices that always dominate or are never useful. |
| Strengths with counters | Describe how a prepared opponent can respond. Test whether the nation can adapt at a cost without erasing its weaknesses. |
| Whole economy | Compare displayed costs, upkeep, fort/lab/temple investment, commander points, Holy limits, explicit recruitment limits, capital-only availability and gem income. |
| Development across the game | Map opening, first-war and later options. Include path/random probabilities, boosters, fatigue and gem requirements; theoretical access is not reliable mass access. |
| Combination balance | Test sacreds with plausible blesses, troops with buffs, equipped commanders, forging discounts and summons. Compare armies at equal investment and equal production time, not only equal headcount. |
| Lore expressed through play | Use a bounded mechanic or meaningful roster relationship to convey the theme. Avoid adding chores or piling bonuses onto every unit. |
| Player choice and fun | Check whether different builds and army compositions remain useful. Record frustrating repetition, obsolete units and unavoidable bottlenecks separately from win rates. |

## Copied-unit audit

Inspect the donor and resulting unit, not only the commands added to it. Review weapons, armour, size, attack/defence, morale, magic resistance, movement, encumbrance, age, leadership, special abilities, transformations and recruitment costs.

`#clearmagic` clears magic, not all inherited behaviour. Check prophet and other shape references explicitly. `#clearspec` removes special abilities; document which are deliberately restored. Automatic gold pricing can change when magic, leadership or sacred status changes. Resource cost includes equipment. Confirm final values in the game before making numerical balance claims. See the [official modding manual](https://illwinter.com/dom6/dom6modman.pdf).

## Reference findings

These are reference lessons, not endorsements that any mod is balanced. Community wiki strategy sections can be incomplete; verify mechanics against the target-version catalog and game.

| Reference | Mechanic or author finding | Design lesson |
| --- | --- | --- |
| [EA Mekone](https://illwiki.com/dom5/dom6/mekone-ea) | Fire/Earth forging, powerful recruitment-limited giants, slave troops and fort unrest. | Elite power can be bounded by production and strategic costs. Closest Hebdomad theme reference. |
| [EA Abysia](https://illwiki.com/dom5/dom6/abysia-ea) | Heat-resistant infantry and Fire magic, with capital Blood/Astral mages. | Plan for fire-resistant enemies and later development. |
| [EA Agartha](https://illwiki.com/dom5/dom6/agartha-ea) | Durable troops with weak combat skills, cave/amphibious advantages and Earth magic. | Terrain and support can make imperfect troops useful. |
| [EA Ulm](https://illwiki.com/dom5/dom6/ulm-ea) | Strong humans with low magic resistance, smiths and increased fort resources. | Production and forging can carry identity while leaving vulnerabilities. Do not conflate it with MA Ulm. |
| [EA Arcoscephale](https://illwiki.com/dom5/dom6/arcoscephale-ea) | Formation infantry, flying troops and varied mages. Wiki lists Myrmidons at 15 gold, 29 resources and 21 recruitment points. | Compare equipment and recruitment bottlenecks as well as gold; reverify prices for the target version. |
| [MA Marignon](https://illwiki.com/dom5/dom6/marignon-ma) | Mage-priests and sacred cavalry available beyond the capital. | Sacred availability affects replenishment. Different era: thematic reference, not primary EA price benchmark. |
| [Lemnos](https://steamcommunity.com/sharedfiles/filedetails/?id=3144768491) | Author targets vanilla power levels; revisions change fear, movement, sacred availability and equipment cost. | Tune availability and mechanics as well as gold. An AI snowball report remains an unverified player report. |
| [Liaozhai](https://steamcommunity.com/sharedfiles/filedetails/?id=3282531883) | EA Cassia uses homesick immortal bee dreams returning in spring; Guanghan combines attackers with mediocre defence. | Mythology can produce bounded timing and composition choices. |
| [Dominions Enhanced / Zion](https://github.com/BlueFeuer/DominionsEnhanced6/blob/main/README.md) | Author documents a capital angel recruit limit of one; the overhaul changes the wider balance environment. [Source](https://github.com/BlueFeuer/DominionsEnhanced6/blob/main/DomEnhanced2_GitHub.dm). | Scarce supernatural power can complement ordinary troops. Do not transplant overhaul prices into vanilla. |

Player discussions emphasise expansion survival, research/upkeep efficiency, timing and raiding, but disagree about rankings and numerical targets. Use their claims as test hypotheses: [nation-strength discussion](https://www.reddit.com/r/IllwintersDominions/comments/1sn65lr/what_makes_a_nation_good/) and [EA Agartha discussion](https://www.reddit.com/r/Dominions6/comments/1rfdqcb/early_ages_agartha_optimization/). The latter illustrates why success against AI does not prove multiplayer balance. The former includes overhaul context.

## Playtesting protocol

1. Record exact game/mod versions, map/seed, opponents, independent strength, research settings and pretender/scales/bless. Keep settings matched between comparisons.
2. Verify recruitment screens, random paths, equipment, transformations and restrictions before strategic trials.
3. Run repeated expansion trials across several map seeds, including economy-focused, sacred-focused and awake combat-pretender builds. Record losses and failed attempts, not only successful runs.
4. At turns 12, 24 and 36, record provinces, income, upkeep, forts, research totals/unlocks, mage counts, gem income/spending and surviving armies.
5. Compare representative army matchups at equal investment and equal production time. Include giants, ordinary infantry, ranged pressure, elemental resistance and mobile raiders. Record scripts, buffs, equipment and gems.
6. Test repeated battles, replenishment, sieges, raids and capital loss; an isolated battle win is insufficient.
7. Evaluate human-controlled play and AI-controlled behaviour separately. Multiplayer claims require prepared human opponents; AI trials establish only their tested scope.
8. Record roster usage and fun: meaningful choices, theme expressed in play, frustrating chores and strategies that become mandatory.

Use same-era vanilla results as a comparison range. Do not adopt a fixed province target or win-rate threshold from forums as a universal pass condition. Change one balance lever at a time and repeat the affected comparisons.

## Review output

For every nation, deliver the design brief, reference comparisons, source-backed findings, proposed changes ranked by importance, and a test log with untested limits. Static validation, successful export and successful loading are distinct from gameplay balance evidence.

Current example: [Hebdomad review](HEBDOMAD-REVIEW.md).
