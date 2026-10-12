# Hebdomad design review

Historical project-specific evidence. This is not a current generation rule or release verification.

For the current expanded local project, read [the expanded roster review](HEBDOMAD-ROSTER-REVIEW.md).
The older review below preserves its original source scope and historical test evidence.

Reviewed October 7, 2026. Source: the local project `.local/projects/hebdomad/mod/hebdomad/hebdomad.dm` (mod version 0.10), with donor units from the supplied dom6inspector snapshot marked 6.37. This is a source review, not an in-game balance verdict. The local project has custom sprites; the reusable demo generator still uses vanilla sprite references.

Use [NATION-DESIGN.md](NATION-DESIGN.md) for the criteria, source links and test protocol. The authoring expansion below adds draft content; its balance remains unproven.

## Current authoring expansion and engine check (October 7, 2026)

Current source SHA-256: `a834aee33c71c7a80c3c55e8466935748f55b8b33bb351fc2ef76ff993bbf016`.
Static validation reports zero errors, warnings or unverified commands. Dominions 6.37 loaded an exact copy and
created a turn-1 save with normal-AI Hebdomad in an isolated configuration. Evidence is in
`.local/authoring-expansion/engine-check-02/report.json` and `logs/log.txt`; the live project's Playtests tab records
that revision and the evidence hashes. No turns were played. Hero arrivals, ritual casts, equipped costs,
battle appearance and balance remain unverified. The regular game mod/save directories were not used.

| Addition | Definition | Intended constraint |
| --- | --- | --- |
| Norea, Bearer of the Hidden Flame | Hero 5013: F2 E1 H1 | Rare hero; introduces no new recruitable path |
| Abrasax, Smith of the Unsealed Gate | Hero 5014: F1 E3, forge bonus 2 | Rare specialist; no gem generation |
| Vessel of Sealed Matter | Summon 5015, Attentive Statue donor 1497, FR5 | Heavy, slow construct; donor map movement 3 |
| Warden of the Borrowed Flame | Summon 5016, Living Statue donor 474, FR15, heat 2 | Slow construct; heat can harm unprotected allies |
| Forge a Sealed Vessel | Conjuration 3, E2F1, 4 earth gems, 2 vessels | Extra research/cross-path gates compared with Attentive Statues |
| Borrow the Furnace Flame | Conjuration 5, F2E1, 6 fire gems, 2 wardens | Gem investment and friendly-fire positioning |
| Open the Seventh Forge | Conjuration 7, E3F2, 18 earth gems, 8 vessels | High research and cross-path gate; no scaling count |
| Gatebreaker Hammer / Mantle of the Brass Gate | Weapon 1000 / armour 400 | Copy ordinary Hammer 13 / Bronze Cuirass 100; cosmetic national names |
| Quarry resources | Site 1701 gets +5 resources | Small capital production benefit; gem income stays F2 E2 |

All three rituals are restricted to nation 150 and copy documented vanilla monster-summon templates before bounded
overrides. Heroes and summons currently share accepted custom roster sprite pairs; no new unique artwork is claimed.
Seventeen monster definitions now comprise eleven recruits, two pretenders, two heroes and two summon types.
The pre-expansion source, metadata and asset hashes are retained under `.local/authoring-expansion/before/`.

## Earlier engine check

Dominions 6.37 loaded the exact local source revision
`1edb7ea7a0628a701fb02d0370222dc27ae081606033151df9cce4c7d7450c3b`
and completed creation of `kosmokrator_nation_edit_smoke` with Hebdomad present. The isolated copy is under
`.local/nation-edit-game-check/`; `report.json` and `logs/creation.debug.txt` record the evidence. Project source,
assets and reservations were not changed, and the regular game mod/save directories were not used.

This is a **load and game-creation check only**. Scripted creation included all 36 EA nations despite the requested
four-nation selection. Subsequent host invocations reported `Game Over` with zero human players and did not
advance beyond turn 1. They provide no expansion, research, AI performance or balance result. The Windows
game-control helper failed to initialize, so recruitment screens, final costs, pretender selection and battle
appearance remain unchecked.

The next playable test should use a human-controlled Hebdomad start alongside EA Arcoscephale, Mekone and Ulm,
with the matched settings and checkpoints in the test matrix below. First inspect all recruitable units and both
custom gods; record final costs and the inherited prophet transformation behaviour before changing balance.

## Verdict and intended playstyle

Hebdomad has a coherent foundation, but its gameplay identity and balance remain unproven. The immediate work is an inheritance/cost audit, followed by baseline testing. There is no evidence yet that it needs a general buff or nerf.

Proposed identity: **A disciplined forge-state whose infantry holds the line while smiths strengthen matter and Archons bring fire; powerful in prepared battles, but limited in mobility and magical diversity.**

Primary comparisons: EA Mekone (Fire/Earth rulers and forging), EA Arcoscephale (formation infantry and donor units), EA Ulm (smiths and Iron Warrior donor). EA Agartha and Abysia provide additional support-magic and fire-specialisation comparisons. MA Marignon is a secondary religious reference only.

## Current design facts

- Five troops, six commanders. Four ordinary troops and five commanders are fort recruits; Sealbearers and Archons are capital-site recruits.
- Seventeen monster definitions: eleven roster units, two pretender forms (5011, 5012), two heroes (5013, 5014) and two summon types (5015, 5016). The four additions do not become fort recruits.
- National recruitment gives Fire, Earth and Holy only. Outside the capital: Kindlers have F1 and a 10% F/E random; Smiths have E2 and a 50% F/E random. Archons have F2 E2 H1 and a guaranteed F/E random.
- Randoms mean Kindlers are 90% F1, 5% F2 and 5% F1E1; Smiths are 50% E2, 25% E3 and 25% F1E2; Archons are evenly split between F3E2H1 and F2E3H1.
- Capital produces two Fire and two Earth gems per turn. The researched EA comparison pages list six total each; four is a deliberate test question, not an established defect.
- Starting army: 15 Brazen Wardens and 15 Smoke Slingers, led by a Strategos, plus a scout.
- Three national summon rituals and two heroes are defined. No explicit per-unit recruitment limits are added; capital and normal recruitment constraints still apply.
- Costs are inherited automatic values rather than explicitly tuned gold/resource/recruitment-point overrides. Changed magic and sacred status affect derived costs.

## Roster assessment

| Entry | Current basis / role | Question to resolve |
| --- | --- | --- |
| Hylic Spearman | Cardaces; inexpensive formation infantry. | Does it remain useful after Wardens become affordable? |
| Smoke Slinger | Vanilla Slinger; cheap ranged support. | Does it contribute against the enemies actually encountered, with and without support magic? |
| Brazen Warden | Myrmidon plus fire resistance 5. | Formation density, armour and Earth support may be effective together. Test fatigue and replenishment constraints. |
| Iron Warden | Iron Warrior, special abilities cleared, mountain survival restored. Donor MR is 8. | Is it a distinct offensive option beside the Brazen Warden? Preserve low MR as a possible counter rather than automatically correcting it. |
| Sealbearer | Myrmidon plus sacred status, fire resistance 5 and morale 14. | Does the capital-only sacred offer a worthwhile alternative across plausible blesses? Its non-bless differences from Brazen Wardens are small. |
| Watcher | Scout donor. | Verify scouting/movement behaviour and cost. |
| Strategos | Myrmidon Champion donor. | Verify leadership and recruitment cost; does recruiting it impose a meaningful mage-production tradeoff? |
| Hierophant | Mystic with magic replaced by H2, sacred. | Verify cost, blessing support and inherited prophet transformation. |
| Kindler | Mystic with F1 and rare F/E random. | Evaluate research per gold, upkeep and commander point. Do not depend on rare F2 results for the basic Fire army plan. |
| Firmament Smith | Warrior Smith, replaced magic/specials, E2 random, forge bonus 1. | Audit the removal of sacred/resource traits and resulting cost/upkeep; compare research, forging and battlefield demand for the same mage turns. |
| Seventh Archon | Giant Archon donor, replaced magic/specials, capital-only, sacred. | Verify derived cost and recruitment speed. Test equipped combat roles, buff/spell access and capital production pressure. |

## Priorities

### 1. Audit inherited mechanics before balancing

**Source-backed risk:** Mystic donor 311 has `prophetshape 382`. The Hierophant and Kindler use `#clearmagic` without `#clearspec` or an explicit prophet-shape override. The official manual says prophetshape changes the unit when made prophet. Check whether these units become a vanilla Mystic, changing appearance and magic. This has not been reproduced in game.

Inspect all eleven entries for inherited age, equipment, shape references, movement, leadership and special abilities. Verify what `#clearspec` removes from the Smith and Archon instead of assuming only intended traits disappear. Record the final displayed costs and recruitment requirements.

### 2. Establish expansion and research baselines

**Hypotheses:** formation infantry may expand reliably, but resource demand and fatigue may limit it; Kindlers may be cheap researchers but consume commander capacity for limited combat utility. Smiths may have competing duties. Test these rather than adjusting prices from donor names.

### 3. Differentiate overlapping troops

**Design concern:** Brazen Wardens, Iron Wardens and Sealbearers need distinct reasons to recruit them. Measure their use and performance before adding abilities. A sacred being similar to normal infantry can be intentional if its bless and upkeep create a worthwhile tradeoff.

### 4. Check magic timing and counterplay

The recruitment roster lacks native Air, Water, Astral, Death, Nature, Glamour and Blood. Pretenders, independent recruits, sites, items and summons may change access in a particular game; absence from recruitment does not mean permanent impossibility.

Build an actual opening/first-war/later research plan using the target game. Test fire-resistant enemies, low-MR exploitation, prolonged fatigue, ranged pressure and mobile raids as candidate counters. Also test Earth-supported armies without relying on Fire damage. None of these matchup outcomes is established yet.

### 5. Express the Gnostic theme through a player decision

**Design proposal:** the tension between Archontic control of matter and the hidden divine spark should eventually affect a roster relationship or a bounded national mechanic. Select one only after baseline tests show what is missing. New paths, freespawn, communion systems, events and summons are not automatically required.

## Pretender proposal (first draft, October 7, 2026)

**Status:** added to the local project and the demo generator. Static validation is clean (0 errors, 0 warnings, 0 unverified). The mod passes the headless load/game-creation check above; pretender selection and balance remain untested. This is a design proposal; earlier findings above are unchanged.

Two national gods express the theme from item 5: the Archontic maker of matter and the hidden wisdom. They are proposed archetypes, not claims about historical theology. Both use `#homerealm 0` and are added only through the nation's `#addgod`, so other Mediterranean nations do not get them.

| God | Donor | Intended role | Authored values |
| --- | --- | --- | --- |
| Demiurge of the Brass Heaven (5011) | Great Archon 3416 (size 9, HP 97, prot 7, F1 E1 S1, dominion 3, path cost 60, basecost 10020) | Material false creator: lion-headed giant in brass armour; a combat-capable Fire/Earth start. | `#clearweapons #weapon 11 #cleararmor #armor 100`, `#clearmagic #clearspec`, F1 E1 (no Astral), `#startdom 3`, `#pathcost 60`, `#gcost 10060` |
| Sophia of the Hidden Spark (5012) | Great Enchantress 485 (size 3, HP 9, G1, dominion 1, basecost 10000) | Fragile human wisdom god with staff and lamp; cheap paths and a dominion focus instead of combat. | `#clearmagic #clearspec #female`, S1 G1, `#startdom 1`, `#pathcost 20`, `#gcost 10040` |

Copied-unit audit (from the catalog; confirm in game):

- **Source-backed:** the manual says dominion strength and path cost are special abilities, so `#clearspec` clears them. Both blocks set `#startdom` and `#pathcost` after it, and `#addgod` requires both.
- **Assumption:** `#clearspec` also removes the Great Archon's spirit sight, alchemy 100 and `moremagic` 1, and the Great Enchantress's Glamour gem income and independent spells. The manual does not list every column it clears.
- **Changed:** Demiurge equipment, to match its humanoid sword art. `#clearweapons #weapon 11` (Great Sword, one attack) and `#cleararmor #armor 100` (Bronze Cuirass) replace the donor's Scourge of Power, two Serpent Leg attacks, Bronze Cuirass and Shield of Wisdom. Tradeoff: fewer attacks and no shield make it a weaker melee god than the donor. The blade's flame is decorative, not fire damage. Sophia keeps the donor Quarterstaff.
- **Not given:** free gems, freespawn, global effects, immunities or all-path access.
- **Costs:** `#gcost` encodes autocalc plus +60 and +40. Final design points are unknown until checked on the pretender screen.

Pretender list as the browser reads it (static): `#homerealm 3` gives 37 catalog realm entries, plus the two `#addgod` gods. Three entries are provisional because their catalog rows have no path cost (Grey One and two Titan of Crossroads parts). Realm 10 (Default) is not declared; the catalog stores it explicitly per nation (e.g. EA Arcoscephale 3 and 10, EA Mekone 3 only), so it is not assumed.

Test questions to add to the matrix: do both gods appear for Hebdomad only; what are their final design points and starting scales; does the Demiurge outclass the vanilla Great Archon for the same nation; does Sophia's cheap path cost make a magic-heavy start dominate; does any inherited ability remain after `#clearspec`.

## Initial test matrix

Use vanilla EA rules first, with matched settings and several map seeds. Compare Hebdomad with Arcoscephale, Ulm and Mekone.

| Trial | Evidence to collect |
| --- | --- |
| Recruitment and prophet checks | Final costs, commander points, Holy requirements, equipment, random paths and prophet outcomes. |
| Expansion with three pretender approaches | Turns 12/24/36 economy/research, losses, failed attacks and reinforcement delays. |
| Ordinary infantry versus sacred investment | Whether different compositions remain useful; bless cost and economic scales included. |
| Smith-supported armies and Fire-supported armies | Research arrival, mage turns committed, fatigue, friendly fire, gem costs and repeat-battle survival. |
| Giants, fire-resistant enemies, ranged armies and raiders | Prepared counters and costly adaptations; equal investment and production-time comparisons. |
| Siege, attrition and capital disruption | Replacement ability, supply/movement issues, and dependence on Archons/Sealbearers. |
| AI-controlled nation | Recruitment mix, research/summoning behaviour and potential snowballing, separately from human play. |

## Review status

- Theme and roster structure reviewed from current source.
- Research references and reusable criteria documented.
- No evidence-backed overall power rating yet.
- No new game launch, battle, multiplayer trial or AI test performed for this review.
- Next decision: resolve inheritance/cost questions, then use baseline trials to choose specific balance changes.
- Two national pretenders proposed and added (static validation only). In-game availability, final design points and `#clearspec` effects are unverified.

## Flag and mod-banner update

Current source SHA-256: `e01e61c4e289da4a55c68de19b8bcc69e978a5ced9aaf9d0385a2525fe5ee0d7`. The only source change is the added `#icon "mod_banner.tga"`; the flag artwork was replaced and the 256x64 title banner added. Gameplay definitions are unchanged. Validation remains clean. Isolated Dominions 6.37 creation exited 0 and created a turn-one save; the current report is `.local/flag-work/engine-check/report.json`. Banner/menu and flag/map appearance require visual in-game confirmation.

## Recruitable roster expansion

Eight recruitable troops and seven commanders. New fort recruits:

| ID | Unit | Authored gold | Role |
| --- | --- | --- | --- |
| 5017 | Ashen Javelinman | 10 | Two-shot javelin, weaker melee skill and morale, no formation bonus |
| 5018 | Furnace Guard | 13 | Shielded bronze infantry, HP 10 and skill 10, below Wardens |
| 5019 | Penitent Levy | 6 | Cheap spear/shield troops, strength 9 and skill/morale 8 |
| 5020 | Gate Captain | 40 | Leadership 50, one recruitment point, no magic |

Troops use ten recruitment points and base resource component one; equipment adds resources.
All four clear donor specials and magic. Accepted custom sprite frames are reused from Spearman,
Brazen Warden and Strategos. Distinct new artwork remains future work.

Existing Wardens were unchanged: Brazen retains formation fighting and fire resistance with bronze
hauberk and spear; Iron has stronger physique, iron armour, hammer and mountain survival.
Test these roles in armies before declaring either successful.

Source SHA-256: a7cfd26dbf381d1e846ddfa40e39dfdd1672a5f2375eb114ac89d2baa1fdf3eb.
Validation has zero errors, warnings or unverified commands. Isolated Dominions 6.37 creation
exited zero and wrote a turn-one save. Reports/backups: .local/roster-expansion/.
Installed source matches the tested draft. Costs, recruitment and battle balance remain unverified.
Start a new Early Age game to test the expanded roster.
