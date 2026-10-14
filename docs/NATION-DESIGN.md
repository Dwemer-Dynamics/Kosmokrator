# Nation design and balance criteria

Scope: new nations and nation revisions built with Kosmokrator. These criteria guide authoring and review; they are not automatic balance checks or a universal tier formula.

## Required design brief

Before building a nation, record:

- Target game version, era, vanilla or overhaul baseline, and intended single-player/multiplayer use.
- One sentence describing what the player does differently with this nation.
- How its mythology affects recruitment, armies, magic or strategic decisions.
- Main strengths, meaningful weaknesses and practical counters available to opponents.
- Opening expansion plan, first-war research targets and later development options.
- At least three same-era vanilla references, with sources and reasons for choosing them.
- Art direction derived from the user's prompt and a complete original-asset checklist:
  idle/attack pairs for every troop, commander, summon, hero, pretender and alternate
  form; nation flag; custom mod banner; any additional artwork the content requires.
  Record explicit user-authorized reuse/prototype exceptions. Follow `ASSET-RULESET.md`.
  Completion requires all listed assets integrated and included in the export; stock
  sprites and default graphics alone do not satisfy a request for a complete nation.

Keep facts, community reports, design proposals and untested hypotheses explicitly separate. Record source dates/version context; a Dom5 guide, another era or an overhaul is not a direct Dom6 vanilla benchmark.

## Default recruitable troop roster

For a complete new nation, target 10-12 distinct recruitable troop types by default,
including ordinary fort troops and capital-only troops. Summons, commanders, heroes,
pretenders and alternate forms do not satisfy this target. Count distinct equipment
variants only when they create a meaningful recruitment or battlefield choice.

- A deliberately compact roster of 6-8 troops requires an explicit user request or
  a documented design reason, such as unusual terrain recruitment or freespawn.
- An expansive roster may target 14-16 troops when the theme supports useful variety.
- Keep national summons additional to the recruitable roster. Do not reduce troop
  or original artwork scope merely to finish sooner.
- Give every troop a purpose and tradeoff in equipment, cost, protection, mobility,
  recruitment location or battlefield role. Preserve thematic weaknesses; the
  target does not require every nation to have cavalry, archers or every role.
- Before generation, record the proposed count, recruitment locations and roles in
  the brief. Before completion, reconcile the saved recruitment lists and capital
  sites against that plan and the original asset checklist; explain exceptions.

Reference basis: the local Dominions 6.37 dom6inspector catalog at revision
68904be9da4a683e93ceff6ae457d430be2e43dd has a median core recruitable troop roster
of 10 in each era. Core means unique troop IDs from ordinary fort recruitment and
starting capital sites, excluding commanders and summons. Examples: EA Tir na n'Og
6, Mekone 7, Ulm 10, Marverni 11, Caelum 14 and Machaka 14. Terrain/coastal/foreign
recruitment and freespawn need separate review. These counts motivate the default;
they are not a balance guarantee.

## Generation requirements

Apply these checks to complete new nations and record the results in the brief
and delivery report. Do not erase the nation's weaknesses to satisfy a checklist.

- Troop choices: document each recruit's role, cost and equipment tradeoffs,
  mobility and availability. Review overlapping units for a real reason to choose
  either. More expensive or numerically stronger copies alone do not provide depth.
- National magic: plan early, middle and late development with national summons
  plus thematic battlefield support or utility spells where supported and useful.
  A complete magic plan must consider more than summoning rituals. Verify custom
  effects against the manual, catalog and engine; do not invent unsupported effects.
  Document deliberate omissions and how vanilla spells support the intended play.
- Recruitment geography: evaluate ordinary forts, capital sites, non-fort and
  terrain recruitment. Use location restrictions when they express the theme and
  create a useful choice. Record what is available where and verify the saved
  references; do not force special recruitment into every nation.
- Natural progression: trace each signature spell from recruited caster paths and
  random probabilities through research, boosters, forging access, gem income and
  cost. Test normal production access and timing where tools permit. Accelerated
  fixtures may prove execution but do not prove normal access, affordability or
  balance. Report those evidence categories and any untested limits separately.
- Presentation: review descriptions, equipment, temple appearance, site looks,
  flag, banner and sprites together for thematic consistency. Select supported
  built-in temple/site visuals deliberately. Site illustrations made for a browser
  or guide are separate presentation assets, not custom in-game site textures.

- Mercenary companies (optional): custom `#newmerc` companies are supported content, not a requirement.
  There is no mandatory count, and a nation does not get an automatic company. Add one only when it serves
  the theme or the world, and record it in the brief. A company references existing or new monster
  definitions by name (manual p.63) and has no sprite command of its own; any new monster it introduces needs
  its own original idle and attack artwork under the asset rules. Use names that are unique so `#com` and
  `#unit` cannot pick a different monster with the same name.

Prevention check: before final export, reconcile these five areas against the
saved mod and test evidence. Correct defects or identify the exact unverified
item; do not describe an accelerated or static result as normal gameplay proof.

## Nation prose: vanilla tone

Before writing, compare the lore and feature summaries of two or three relevant
vanilla nations in the official manual or verified game data. Record the references.
Write original prose; do not copy their wording.

- `#descr`: use a compact historical account of origins, society, religion and
  military traditions. Explain how magic and sacred warriors belong to that culture.
  Keep prices, numerical paths, random percentages, research plans and tactical
  counter advice in the project guide, rather than the lore paragraph.
- `#brief`: one short factual sentence identifying the nation.
- `#summary`: use short labelled feature lines, not a roster catalogue. Group troops
  by type and magic by path. Mention decisive restrictions such as capital-only
  sacreds or secondary magic. Keep individual mage names and exact random chances
  in unit sheets. Avoid authoring phrases such as ordinary human stats.

Prevention check: compare the saved prose with the references, reconcile claims
against the saved mechanics, and read the final in-game presentation when possible.
Static validation cannot prove line wrapping or engine-added feature text.

## National Features: vanilla presentation format

For every generated nation, write the in-game National Features text in nation
`#summary` using the vanilla labelled-line format. Keep
the labels, spelling and order below; write original, nation-specific content.
Do not replace this section with a short promotional sentence or lore paragraph.

```text
Race: <population and mechanically relevant racial traits>
Military: <main troop types, sacreds and distinctive military capabilities>
Magic: <main paths, secondary access and distinctive research or magic rules>
Priests: <priest strength and distinctive priest abilities>
Dominion: <special dominion effects, or explicitly no special effects>
Buildings: <actual fort types and building cost or construction exceptions>
```

Use one readable line per category, with concise comma-separated facts and short
parenthetical explanations where needed, matching the vanilla example's structure
and useful detail. Cover all six categories even for a nation with ordinary priests
or no special dominion. Do not invent mechanics to fill a line. Distinguish reliable
magic access from random, rare, capital-only or summon-dependent access. Mention
important recruitment restrictions; put detailed tactical weaknesses in the guide.
Describe concrete capabilities and restrictions. For priests, state Holy levels,
availability and distinctive abilities rather than relying on adjectives such as
weak or strong. Keep lore readable and separate from mechanical feature lines.

The engine may append a Buildings line automatically. Inspect the actual in-game
screen and let the engine supply that line when it already reports the correct
information; do not create a duplicate or contradictory Buildings entry. The final
display must cover all six categories in the order above. Verify supported text
line breaks against the modding manual and engine rather than assuming Markdown,
HTML or literal backslash-n escapes render correctly.

Keep `#descr` as the fuller nation lore and `#brief` as the short popup description;
neither substitutes for `#summary`. Before export, reconcile every claim against
saved nation commands, recruits, mage/priest paths, sites and inherited defaults.
Before delivery, check the nation-selection screen for label order, line breaks,
readability, completeness and duplicate Buildings text. If that screen cannot be
checked, report presentation as unverified. Sparse unlabelled summaries fail this
generation requirement even when the mod validates.

## Generation quality gates

Scope: complete nation generation and revisions. Apply these reusable checks before
bulk artwork and repeat them against the saved source before delivery.

- Recruitment choices: for overlapping troops, state a situation favouring each
  choice and compare equal gold investment and equal production time, accounting
  for resources, recruitment points and upkeep. Test representative alternatives
  where the engine permits; do not pad the roster with dominated variants or erase
  intentional cheap-to-elite progression merely to make every unit unique.
- Routine support access: identify which recruitable casters can repeatedly use
  the intended army support without temporary gem boosting. Record capital-only,
  slow-recruit, commander-point and path-random bottlenecks. Keep deliberate
  scarcity when it supports the design, but do not describe exceptional access as
  ordinary support or silently give every nation stronger mages.
- Army leadership: map each advertised army composition to an available commander
  with the required living, magical and undead command capacity, stealth, movement
  and terrain/water survival. Check recruitable availability and price, not just
  hero or late-summon possibilities. Do not assume Holy paths grant undead command;
  verify nation-specific prerequisites and actual capacity against the manual and
  engine. Reconcile source, roster, guide and displayed totals before delivery.
- Early identity: make at least one theme-shaped decision available during opening
  or first-war play, through recruitment, geography, support or a bounded mechanic.
  A late capstone may extend that identity; it must not be the only distinctive
  promise in the brief. Do not lower research or add free units automatically.
- Signature magic progression: verify the complete recruited caster -> research
  -> forge -> equip -> cast route for any required booster. Record actual forging
  charges, spell charges and competing gem uses. Demonstrate it under ordinary
  production rules when possible; unlocking research or seeding a boosted caster
  proves only fixture execution. Report any untested link explicitly.
- Summon value: compare each summon against accessible same-era alternatives at
  equal gem investment, including caster turns, research, upkeep, leadership,
  replenishment and battlefield role. Test a representative use before numerical
  balance claims; low headcount alone is not proof of poor value.
  Show saving time from starting income and competing uses of that same gem path,
  including forging, battle magic and other summons. Explain who can lead and
  replenish the force. Distinguish a deliberately scarce investment from a useful
  routine purchase; neither price nor a successful cast proves worthwhile value.
- Creature defaults: audit newly defined units as well as copied units. Choose
  age/max age, size, anatomy/item slots, food needs, encumbrance, resistances,
  leadership and costs by creature type. Human defaults must not automatically
  propagate to gods, undead, animals or alternate forms. Verify documented engine
  behaviour rather than assuming a trait makes an irrelevant default harmless.
- National spell purpose: explain what each spell adds beyond vanilla access.
  For copied effects, record the original and changed school, research, paths,
  fatigue, gem cost and targeting. Retain intentional variants with a thematic
  or strategic rationale; a renamed vanilla effect alone does not establish depth.
- Individual lore: write a distinct origin, custom, oath, relationship or mythic
  consequence for every troop, commander, summon, hero and pretender. Connect it
  to the role where useful. Keep practical instructions clear, but do not substitute
  role labels followed by a repeated national sentence for individual descriptions.
  Review the actual saved descriptions for repetition before final export.
- Evidence capture: configure checkpoint collection before the first host. Save
  settings, production source hashes, recoverable saves and per-turn score/log
  receipts. At turns 12, 24 and 36 capture income, upkeep, forts, research/unlocks,
  living mage counts, gem income/stocks/spending and surviving army composition
  where available. Preserve missing fields explicitly; do not substitute cumulative
  purchases for living mages or combine separate campaigns into one trajectory.

Prevention check: reconcile planned roles and leadership, early identity, caster
access, creature defaults, individual lore, spell changes and progression links
against actual source, delivery documentation and evidence. Rank
remaining design hypotheses separately from proven defects and testing gaps.

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
| [EA Mekone](https://illwiki.com/dom5/dom6/mekone-ea) | Fire/Earth forging, powerful recruitment-limited giants, slave troops and fort unrest. | Elite power can be bounded by production and strategic costs.  |
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

Use the same review structure for every nation; record project-specific evidence in its delivery report.
