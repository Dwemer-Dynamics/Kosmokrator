# Expanded Hebdomad roster review

Reviewed October 8, 2026 against the local authoritative project and dom6inspector 6.37 catalog.
This replaces the old eleven-unit scope for the current demo. It is a source review, not a power rating.
The mod has eight recruitable troops, seven recruitable commanders, two heroes, two summoned
constructs and two custom pretenders: 21 definitions. All now have distinct idle/attack sprite pairs.

## Playstyle and roles

Build a cheap human line, invest selectively in disciplined wardens, and use Fire/Earth mages to
support slow infantry and constructs. Capital recruitment, mage turns and gem spending compete.
The hidden spark is expressed by the two exceptional heroes and the choice between human armies
and forged guardians; it does not give ordinary troops extra paths or universal resistance.

| Troop | Intended choice | Current source tradeoff |
| --- | --- | --- |
| Penitent Levy | Cheap bodies, siege support and replacements | 6 gold; strength 9, skill/morale 8; leather, spear and shield. |
| Hylic Spearman | Reliable basic formation line | Inherited formation fighter 2, skill/morale 10; leather and bronze spear. Gold is encoded autocalc, not a confirmed displayed price. |
| Ashen Javelinman | Opening volleys before melee | 10 gold, two javelin shots; melee skill/morale 9 and movement 12; no formation bonus. |
| Smoke Slinger | Cheap ranged support | Sling and dagger, light leather; friendly-fire and armour matchups remain untested. |
| Furnace Guard | Affordable armoured spear line | 13 gold, skill 10, morale 11, bronze cuirass/cap/shield; fire resistance 5 now follows the special-ability reset. |
| Brazen Warden | Elite ordinary line | Skill 12, morale 13, heavier bronze armour, formation bonus and fire resistance 5. More resource demand than a Furnace Guard. |
| Iron Warden | Hammer infantry and mountain travel | Stronger human donor, maul and scale armour; clears specials then restores mountain survival. No shield in resolved equipment. |
| Sealbearer | Capital sacred investment | Warden equipment, sacred, morale 14, fire resistance 5; capital and Holy recruitment constraints. |

Commander purposes: Watchers scout; Gate Captains provide cheap ordinary leadership (40 gold,
50 leadership); Strategoi provide better leadership (100) and combat stats; Hierophants provide H2;
Kindlers provide F1 research and occasional higher paths; Smiths provide E2 support and a fixed
one-gem forge reduction; Archons supply capital-only F2 E2 H1 with a full Fire/Earth random.
Heroes supply F2 E1 H1 or F1 E3, but their arrival cannot anchor a dependable research plan.

## Magic timing and summon economy

The mask 1152 is Fire plus Earth. Assuming equal path selection, Kindlers have 5% F2, 5% F1 E1
and 90% F1; Smiths have 25% F1 E2, 25% E3 and 50% E2. Archons split between F3 E2 H1
and F2 E3 H1. These probabilities follow authored random picks; recruitment screens remain unchecked.
See the [official modding manual](https://www.illwinter.com/dom6/dom6modman.pdf), Magic Paths.

| National ritual | Source requirements | Output and opportunity cost |
| --- | --- | --- |
| Forge a Sealed Vessel | Conjuration 3, E2 F1, 4 Earth gems | Two vessels: 2 gems each plus a mage turn. Only Fire-random Smiths or Archons qualify without boosters. |
| Borrow the Furnace Flame | Conjuration 5, F2 E1, 6 Fire gems | Two hot wardens: 3 gems each plus a mage turn. Archons qualify; basic Kindlers do not reliably qualify. |
| Open the Seventh Forge | Conjuration 7, E3 F2, 18 Earth gems | Eight vessels: 2.25 gems each; halves of the Archon random outcomes qualify without boosters. Saves casting turns rather than gems per vessel. |

Both constructs inherit magic-being/stone-being traits, poison resistance 25, slash/pierce resistance,
poor amphibian movement and no need to eat from their final statue donors. Both move only 3.
Vessels additionally have patrol bonus 5. Hot wardens have heat 2 and fire resistance 15; their heat
requires spacing or protection for allies. Slow movement is a strong operational cost, but does not
prove these gem prices are balanced. Compare equal-gem armies and defensive siege use later.

## October 9 source corrections and decisions

- Moved Furnace Guard's existing `#fireres 5` after `#clearspec`. No magnitude or cost changed.
- Added explicit `#prophetshape 5007` and `5008` to Hierophant and Kindler, overriding the
  copied vanilla Mystic target. The starter template uses its allocated IDs too. Research
  bonus 1 remains inherited intentionally. Self-target prophet behavior is not game-verified.
- Kept Abrasax's `#forgebonus 2` as a modest two-percent discount: his exceptional Fire/Earth
  paths supply the hero's specialization. Changing it to two gems would be a separate buff.

## Remaining balance and runtime questions

1. Furnace Guard's restored fire resistance does not establish that mixed formations beside hot
   constructs are safe. Check fatigue, heat and spacing in a later battle test.
2. The hero smith uses `#forgebonus 2`: that means **2 percent**, not two gems. Ordinary Smiths use
   `#fixforgebonus 1`, an absolute one-gem reduction. The manual distinguishes these explicitly.
   The current decision keeps the stronger paths and the smaller discount; verify forge costs later.
3. Hierophants and Kindlers retain Mystic research bonus 1. The donor also has prophetshape 382;
   the source now overrides that target explicitly with each custom unit's own ID. Check actual
   prophet identity before claiming runtime correctness. `#clearmagic` alone does not clear abilities.
4. Levy and Furnace Guard have explicit low gold costs and ten recruitment points. Compare production
   and replacement rates against Hylic/Brazen Wardens before changing costs. Equipment adds resources.
5. Sealbearers closely resemble Brazen Wardens. Their capital restriction, bless and sacred upkeep
   must justify the choice; adding more bonuses now would obscure the comparison.

The October 8 art pass changed no gameplay numbers. The October 9 ordering fix restores existing
authored resistance and explicitly overrides two shape references. New art removes shared sprite references; the two
constructs' sprite commands now follow their final `#copystats`, matching the asset ruleset.

## Reference and counterplay checks

Use EA Arcoscephale for formation infantry and production comparisons, EA Ulm for smith-supported
humans and resource pressure, and EA Mekone for Fire/Earth elites constrained by recruitment.
These are the same-era references recorded in [NATION-DESIGN.md](NATION-DESIGN.md), not evidence
that Hebdomad matches their strength. EA Abysia is the useful fire-resistant matchup reference.

Candidate counters: fire-resistant armies, high-damage attacks against armoured infantry, anti-magic-being
effects against constructs, fatigue/attrition and mobile raiding against slow reinforcement.
Earth support and mundane weapons provide a potential alternate plan, at the cost of research and
mage turns. Final costs, buffs, battle losses, expansion speed and multiplayer balance remain untested.

Next balance decision should use these specific questions, not an overall numerical tier score.
