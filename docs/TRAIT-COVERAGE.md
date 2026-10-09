# Monster trait coverage (unit editor)

Generated from `kosmokrator/traits.py` (`traits.coverage()`), which is built from the official *Dominions 6 Modding Manual* 6.36, Monster Modding pp.13-36. Every command header there was extracted, and families written as `#summon1...5`, `#batstartsum1d6...9d6`, `#(path)attuned` were expanded. Audit result:

- Documented monster commands: **565**
- Editable as traits (typed / reference / tuple / repeatable controls): **519**
- Edited by the existing dedicated fields (stats, leadership, magic paths, pretender, gold): **22**
- Excluded (not traits; kept verbatim): **24**

Docindex differences: `docindex.MONSTER_DOCUMENTED` lists `#dt` and `#guardspirit`. Both appear only inside prose (`#dt_raise` mid-sentence; `#guardspirit` is the nation command mentioned by `#guardspiritbonus`), so they are not monster commands and are not included. Family members such as `#summon3`-`#summon5`, `#battlesum2`-`#battlesum5`, `#fireattuned` are documented by the family header but absent from docindex; they are included.

## Rules

- Argument count and types follow the manual header (`<value>` = whole number; `"<monster name>" | <monster nbr>` = monster reference; spell/site/item likewise).
- Ranges are enforced only where the manual states them (header such as `<-5 - 5>`, `<0 or 1>`, or the entry text, e.g. `#montag` 1000-100000, `#userestricteditem` 1-10000). Elsewhere only a 32-bit whole number is required.
- References must exist in the project .dm or the loaded game catalog. `#onebattlespell` and `#3castbattlespell` accept only original game spells, as required by p.35. Negative monster numbers are accepted only for commands whose entry documents them (Monster Summoning section, montag-capable shape commands): -2..-26 (table p.29) or -1000..-100000 (montags).
- Repeatable: `#startitem` (p.18 "multiple times"), `#custommagic` (p.33), `#magicboost`/`#gemprod` (per-path tuples), `#homerealm` (several realms per god, catalog realm1-3), `#batstartsum*` (manual: at most 3 times). Everything else is single-valued: duplicates after the last reset are refused, not rewritten.
- No role-based restrictions (troop/commander/god) are invented. Preview and save enforce `#holy` for Holy magic and `#holycost`, reject simultaneous multiple mounts and multiple riders, and reject undocumented random-magic mask bits. Other dependencies, such as reciprocal shape changes and `#montagweight` after `#montag`, are explained in notes and require design review.
- Reset scope: a trait line before `#copystats`, `#clear` or `#clearspec` (plus `#clearmagic` for `#custommagic`/`#magicboost`) is treated as ended. New lines are appended just before `#end`. Inherited traits cannot be removed: the editor never writes `#clearspec`, `#clearmagic`, `#clear` or `#copystats`.
- Display: the unit view lists every authored trait line with its status (authored / ended by a reset / malformed). Inherited abilities outside the modelled donor columns are labelled not modelled rather than guessed.

## Table

| Command | Status | Section (page) | Arguments / reason |
|---|---|---|---|
| `#clear` | excluded | Clearing & Copying (p.13) | Reset/copy command. Never written by the editor because it also removes or replaces other values. |
| `#cleararmor` | excluded | Clearing & Copying (p.13) | Reset/copy command. Never written by the editor because it also removes or replaces other values. |
| `#clearmagic` | excluded | Clearing & Copying (p.13) | Reset/copy command. Never written by the editor because it also removes or replaces other values. |
| `#clearspec` | excluded | Clearing & Copying (p.13) | Reset/copy command. Never written by the editor because it also removes or replaces other values. |
| `#clearweapons` | excluded | Clearing & Copying (p.13) | Reset/copy command. Never written by the editor because it also removes or replaces other values. |
| `#copyspr` | excluded | Clearing & Copying (p.13) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#copystats` | excluded | Clearing & Copying (p.13) | Reset/copy command. Never written by the editor because it also removes or replaces other values. |
| `#descr` | excluded | Basic Commands (p.13) | Name/description text; not a trait (kept verbatim). |
| `#drawsize` | excluded | Visuals (p.13) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#end` | excluded | Basic Commands (p.13) | Opens a monster block; not a trait. |
| `#fixedname` | excluded | Basic Commands (p.13) | Name/description text; not a trait (kept verbatim). |
| `#name` | excluded | Basic Commands (p.13) | Name/description text; not a trait (kept verbatim). |
| `#newmonster` | excluded | Basic Commands (p.13) | Opens a monster block; not a trait. |
| `#selectmonster` | excluded | Basic Commands (p.13) | Opens a monster block; not a trait. |
| `#speciallook` | excluded | Visuals (p.13) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#spr1` | excluded | Visuals (p.13) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#spr2` | excluded | Visuals (p.13) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#enchrebate10` | editable trait | Recruitment Rules (p.14) | `enchantment_number:int` |
| `#gcost` | editable field | Pretender God Commands (p.14) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#godsite` | editable trait | Pretender God Commands (p.14) | `site:site` |
| `#homerealm` | editable trait | Pretender God Commands (p.14) | `realm:int` (repeatable) |
| `#maxprison` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#minprison` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#moregrowth` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#moreheat` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#moreluck` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#moremagic` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#moreorder` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#moreprod` | editable trait | Pretender God Commands (p.14) | `value:int` |
| `#noslowrec` | editable trait | Recruitment Rules (p.14) | flag |
| `#pathcost` | editable field | Pretender God Commands (p.14) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#reclimit` | editable trait | Recruitment Rules (p.14) | `units_turn:int` |
| `#slowrec` | editable trait | Recruitment Rules (p.14) | flag |
| `#startdom` | editable field | Pretender God Commands (p.14) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#triple3mon` | editable trait | Pretender God Commands (p.14) | flag |
| `#triplegod` | editable trait | Pretender God Commands (p.14) | `type:int` |
| `#triplegodmag` | editable trait | Pretender God Commands (p.14) | `penalty:int` |
| `#unify` | editable trait | Pretender God Commands (p.14) | flag |
| `#ainorec` | editable trait | Recruitment Rules (p.15) | flag |
| `#aisinglerec` | editable trait | Recruitment Rules (p.15) | flag |
| `#chaosrec` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#chaosrecscale` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#coldrecscale` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#deathrec` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#deathrecscale` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#defector` | editable trait | Desertion (p.15) | `percent:int` |
| `#deserter` | editable trait | Desertion (p.15) | `percent:int` |
| `#domrec` | editable trait | Recruitment Rules (p.15) | `dominion:int` |
| `#enchrebate100` | editable trait | Recruitment Rules (p.15) | `enchantment_number:int` |
| `#enchrebate20` | editable trait | Recruitment Rules (p.15) | `enchantment_number:int` |
| `#enchrebate25p` | editable trait | Recruitment Rules (p.15) | `enchantment_number:int` |
| `#enchrebate50` | editable trait | Recruitment Rules (p.15) | `enchantment_number:int` |
| `#enchrebate50p` | editable trait | Recruitment Rules (p.15) | `enchantment_number:int` |
| `#enchrebate75` | editable trait | Recruitment Rules (p.15) | `enchantment_number:int` |
| `#growthrecscale` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#heatrecscale` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#horrordeserter` | editable trait | Desertion (p.15) | `percent:int` |
| `#monpresentrec` | editable trait | Recruitment Rules (p.15) | `monster:mon` |
| `#noreqlab` | editable trait | Recruitment Rules (p.15) | flag |
| `#noreqtemple` | editable trait | Recruitment Rules (p.15) | flag |
| `#nowish` | editable trait | Desertion (p.15) | flag |
| `#orderrecscale` | editable trait | Recruitment Rules (p.15) | `value:int` |
| `#ownsmonrec` | editable trait | Recruitment Rules (p.15) | `monster:mon` |
| `#rcost` | editable trait | Gold & Resource Cost (p.15) | `resources:int` |
| `#reqlab` | editable trait | Recruitment Rules (p.15) | flag |
| `#reqtemple` | editable trait | Recruitment Rules (p.15) | flag |
| `#rpcost` | editable trait | Gold & Resource Cost (p.15) | `recruitment_points:int` |
| `#singlebattle` | editable trait | Desertion (p.15) | flag |
| `#att` | editable field | Basic Attributes (p.16) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#def` | editable field | Basic Attributes (p.16) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#hp` | editable field | Basic Attributes (p.16) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#prec` | editable field | Basic Attributes (p.16) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#ressize` | editable trait | Gold & Resource Cost (p.16) | `size:int` |
| `#str` | editable field | Basic Attributes (p.16) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#ap` | editable field | Basic Attributes (p.17) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#armor` | excluded | Weapons & Armor (p.17) | Equipment, not a trait (kept verbatim; edited by the equipment loadout tool). |
| `#enc` | editable field | Basic Attributes (p.17) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#eyes` | editable trait | Basic Attributes (p.17) | `nbr_of_eyes:int` |
| `#mapmove` | editable field | Basic Attributes (p.17) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#mor` | editable field | Basic Attributes (p.17) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#mr` | editable field | Basic Attributes (p.17) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#prot` | editable field | Basic Attributes (p.17) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#size` | editable field | Basic Attributes (p.17) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#voidsanity` | editable trait | Basic Attributes (p.17) | `value:int` |
| `#weapon` | excluded | Weapons & Armor (p.17) | Equipment, not a trait (kept verbatim; edited by the equipment loadout tool). |
| `#bird` | editable trait | Bodytype (p.18) | flag |
| `#djinn` | editable trait | Bodytype (p.18) | flag |
| `#female` | editable trait | Creature Type & Status (p.18) | flag |
| `#humanoid` | editable trait | Bodytype (p.18) | flag |
| `#itemslots` | editable trait | Item Slots (p.18) | `slot_value:int` |
| `#lizard` | editable trait | Bodytype (p.18) | flag |
| `#miscshape` | editable trait | Bodytype (p.18) | flag |
| `#mountedhumanoid` | editable trait | Bodytype (p.18) | flag |
| `#naga` | editable trait | Bodytype (p.18) | flag |
| `#noitem` | editable trait | Item Slots (p.18) | flag |
| `#noweapon` | editable trait | Item Slots (p.18) | `value:int` |
| `#quadruped` | editable trait | Bodytype (p.18) | flag |
| `#snake` | editable trait | Bodytype (p.18) | flag |
| `#startitem` | editable trait | Item Slots (p.18) | `item:item` (repeatable) |
| `#troglodyte` | editable trait | Bodytype (p.18) | flag |
| `#userestricteditem` | editable trait | Item Slots (p.18) | `value:int` |
| `#amphibian` | editable trait | Movement (p.19) | flag |
| `#animal` | editable trait | Creature Type & Status (p.19) | flag |
| `#aquatic` | editable trait | Movement (p.19) | flag |
| `#autocompete` | editable trait | Creature Type & Status (p.19) | flag |
| `#blind` | editable trait | Creature Type & Status (p.19) | flag |
| `#bug` | editable trait | Creature Type & Status (p.19) | flag |
| `#coldblood` | editable trait | Creature Type & Status (p.19) | flag |
| `#demon` | editable trait | Creature Type & Status (p.19) | flag |
| `#divinebeing` | editable trait | Creature Type & Status (p.19) | flag |
| `#doomhorror` | editable trait | Creature Type & Status (p.19) | flag |
| `#drake` | editable trait | Creature Type & Status (p.19) | flag |
| `#dungeon` | editable trait | Creature Type & Status (p.19) | flag |
| `#float` | editable trait | Movement (p.19) | flag |
| `#flying` | editable trait | Movement (p.19) | flag |
| `#greaterhorror` | editable trait | Creature Type & Status (p.19) | flag |
| `#holy` | editable trait | Creature Type & Status (p.19) | flag |
| `#holycost` | editable trait | Creature Type & Status (p.19) | `points:int` |
| `#illusion` | editable trait | Creature Type & Status (p.19) | flag |
| `#immobile` | editable trait | Movement (p.19) | flag |
| `#inanimate` | editable trait | Creature Type & Status (p.19) | flag |
| `#lanceok` | editable trait | Creature Type & Status (p.19) | flag |
| `#lesserhorror` | editable trait | Creature Type & Status (p.19) | flag |
| `#magicbeing` | editable trait | Creature Type & Status (p.19) | flag |
| `#nospiritform` | editable trait | Creature Type & Status (p.19) | flag |
| `#plant` | editable trait | Creature Type & Status (p.19) | flag |
| `#polyimmune` | editable trait | Creature Type & Status (p.19) | flag |
| `#pooramphibian` | editable trait | Movement (p.19) | flag |
| `#snow` | editable trait | Movement (p.19) | flag |
| `#spiritform` | editable trait | Creature Type & Status (p.19) | flag |
| `#stonebeing` | editable trait | Creature Type & Status (p.19) | flag |
| `#stormimmune` | editable trait | Movement (p.19) | flag |
| `#swimming` | editable trait | Movement (p.19) | flag |
| `#undead` | editable trait | Creature Type & Status (p.19) | flag |
| `#unique` | editable trait | Creature Type & Status (p.19) | flag |
| `#uwbug` | editable trait | Creature Type & Status (p.19) | flag |
| `#assassin` | editable trait | Stealth & Assassination (p.20) | flag |
| `#blink` | editable trait | Movement (p.20) | flag |
| `#corruptor` | editable trait | Stealth & Assassination (p.20) | `value:int` |
| `#farsail` | editable trait | Movement (p.20) | `extra_provinces:int` |
| `#forestsurvival` | editable trait | Movement (p.20) | flag |
| `#giftofwater` | editable trait | Movement (p.20) | `size_points:int` |
| `#indepmove` | editable trait | Movement (p.20) | `percent:int` |
| `#indepstay` | editable trait | Movement (p.20) | `value:int` |
| `#mapteleport` | editable trait | Movement (p.20) | flag |
| `#mobilearcher` | editable trait | Movement (p.20) | `value:int` |
| `#mountainsurvival` | editable trait | Movement (p.20) | flag |
| `#nomovepen` | editable trait | Movement (p.20) | flag |
| `#norange` | editable trait | Movement (p.20) | `chance:int` |
| `#noriverpass` | editable trait | Movement (p.20) | flag |
| `#patience` | editable trait | Stealth & Assassination (p.20) | `value:int` |
| `#sailing` | editable trait | Movement (p.20) | `shipsize:int` `unitsize:int` |
| `#scalewalls` | editable trait | Stealth & Assassination (p.20) | flag |
| `#seduce` | editable trait | Stealth & Assassination (p.20) | `value:int` |
| `#spy` | editable trait | Stealth & Assassination (p.20) | flag |
| `#statbreak` | editable trait | Movement (p.20) | `value:int` |
| `#statstorm` | editable trait | Movement (p.20) | `value:int` |
| `#stealthy` | editable trait | Stealth & Assassination (p.20) | `value:int` |
| `#succubus` | editable trait | Stealth & Assassination (p.20) | `value:int` |
| `#swampsurvival` | editable trait | Movement (p.20) | flag |
| `#teleport` | editable trait | Movement (p.20) | flag |
| `#unteleportable` | editable trait | Movement (p.20) | flag |
| `#wastesurvival` | editable trait | Movement (p.20) | flag |
| `#addrandomage` | editable trait | Age, Healing & Afflictions (p.21) | `years:int` |
| `#assencloc` | editable trait | Stealth & Assassination (p.21) | `value:int` |
| `#autocorpsehealer` | editable trait | Age, Healing & Afflictions (p.21) | `value:int` |
| `#autodisgrinder` | editable trait | Age, Healing & Afflictions (p.21) | `value:int` |
| `#autodishealer` | editable trait | Age, Healing & Afflictions (p.21) | `value:int` |
| `#autohealer` | editable trait | Age, Healing & Afflictions (p.21) | `value:int` |
| `#beckon` | editable trait | Stealth & Assassination (p.21) | `value:int` |
| `#diseaseres` | editable trait | Age, Healing & Afflictions (p.21) | `percent:int` |
| `#falsearmy` | editable trait | Stealth & Assassination (p.21) | `value:int` |
| `#foolscouts` | editable trait | Stealth & Assassination (p.21) | `value:int` |
| `#heal` | editable trait | Age, Healing & Afflictions (p.21) | flag |
| `#healer` | editable trait | Age, Healing & Afflictions (p.21) | `percent:int` |
| `#homesick` | editable trait | Age, Healing & Afflictions (p.21) | `percent:int` |
| `#landdamage` | editable trait | Age, Healing & Afflictions (p.21) | `percent:int` |
| `#maxage` | editable trait | Age, Healing & Afflictions (p.21) | `age:int` |
| `#noheal` | editable trait | Age, Healing & Afflictions (p.21) | flag |
| `#older` | editable trait | Age, Healing & Afflictions (p.21) | `age:int` |
| `#plaguedoctor` | editable trait | Stealth & Assassination (p.21) | `percent:int` |
| `#startage` | editable trait | Age, Healing & Afflictions (p.21) | `age:int` |
| `#uwdamage` | editable trait | Age, Healing & Afflictions (p.21) | `percent:int` |
| `#acidres` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#bluntres` | editable trait | Damage Reduction (p.22) | flag |
| `#coldres` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#corpseeater` | editable trait | Age, Healing & Afflictions (p.22) | `value:int` |
| `#deadhp` | editable trait | Age, Healing & Afflictions (p.22) | `value:int` |
| `#decayres` | editable trait | Damage Reduction (p.22) | `value:int` |
| `#doheal` | editable trait | Damage Reduction (p.22) | flag |
| `#ethereal` | editable trait | Damage Reduction (p.22) | flag |
| `#extralives` | editable trait | Age, Healing & Afflictions (p.22) | `percent:int` |
| `#fireres` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#hpoverflow` | editable trait | Age, Healing & Afflictions (p.22) | flag |
| `#icenatprot` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#iceprot` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#insane` | editable trait | Age, Healing & Afflictions (p.22) | `percent:int` |
| `#invulnerable` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#maxdeadhp` | editable trait | Age, Healing & Afflictions (p.22) | `hp:int` |
| `#poisonres` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#regeneration` | editable trait | Damage Reduction (p.22) | `percent:int` |
| `#shockres` | editable trait | Damage Reduction (p.22) | `prot:int` |
| `#startaff` | editable trait | Age, Healing & Afflictions (p.22) | `percent:int` |
| `#startheroab` | editable trait | Age, Healing & Afflictions (p.22) | `percent:int` |
| `#startingaff` | editable trait | Age, Healing & Afflictions (p.22) | `affliction_bitmask:int` |
| `#startmajoraff` | editable trait | Age, Healing & Afflictions (p.22) | `percent:int` |
| `#undregen` | editable trait | Damage Reduction (p.22) | `percent:int` |
| `#woundfend` | editable trait | Age, Healing & Afflictions (p.22) | `value:int` |
| `#xpgain` | editable trait | Age, Healing & Afflictions (p.22) | `percent:int` |
| `#airshield` | editable trait | Damage Reduction (p.23) | `percent:int` |
| `#animalawe` | editable trait | Combat Auras (p.23) | `bonus:int` |
| `#bugreform` | editable trait | Immortality (p.23) | `nbr_of_bugs:int` |
| `#bugshape` | editable trait | Immortality (p.23) | `monster:mon` |
| `#bugswarmshape` | editable trait | Immortality (p.23) | `monster:mon` |
| `#bugswarmuwshape` | editable trait | Immortality (p.23) | `monster:mon` |
| `#buguwshape` | editable trait | Immortality (p.23) | `monster:mon` |
| `#cold` | editable trait | Combat Auras (p.23) | `value:int` |
| `#diseasecloud` | editable trait | Combat Auras (p.23) | `size:int` |
| `#domimmortal` | editable trait | Immortality (p.23) | flag |
| `#enchantedblood` | editable trait | Damage Reduction (p.23) | `points:int` |
| `#falseregen` | editable trait | Damage Reduction (p.23) | `points:int` |
| `#glamour` | editable trait | Damage Reduction (p.23) | flag |
| `#heat` | editable trait | Combat Auras (p.23) | `value:int` |
| `#immortal` | editable trait | Immortality (p.23) | flag |
| `#ironvul` | editable trait | Damage Reduction (p.23) | `points:int` |
| `#pierceres` | editable trait | Damage Reduction (p.23) | flag |
| `#poisonarmor` | editable trait | Combat Auras (p.23) | `dmg:int` |
| `#poisoncloud` | editable trait | Combat Auras (p.23) | `size:int` |
| `#poisonskin` | editable trait | Combat Auras (p.23) | `value:int` |
| `#reconst` | editable trait | Damage Reduction (p.23) | `percent:int` |
| `#reform` | editable trait | Immortality (p.23) | `chance:int` |
| `#reformtime` | editable trait | Immortality (p.23) | `extra_months:int` |
| `#reinvigoration` | editable trait | Damage Reduction (p.23) | `points:int` |
| `#slashres` | editable trait | Damage Reduction (p.23) | flag |
| `#springimmortal` | editable trait | Immortality (p.23) | flag |
| `#twistfate` | editable trait | Damage Reduction (p.23) | flag |
| `#uwheat` | editable trait | Combat Auras (p.23) | `value:int` |
| `#uwregen` | editable trait | Damage Reduction (p.23) | `percent:int` |
| `#acidshield` | editable trait | Combat Auras (p.24) | `damage:int` |
| `#awe` | editable trait | Combat Auras (p.24) | `bonus:int` |
| `#banefireshield` | editable trait | Combat Auras (p.24) | `damage:int` |
| `#bloodvengeance` | editable trait | Combat Auras (p.24) | `strength:int` |
| `#curseluckshield` | editable trait | Combat Auras (p.24) | `penetration_bonus:int` |
| `#damagerev` | editable trait | Combat Auras (p.24) | `strength:int` |
| `#dread` | editable trait | Combat Auras (p.24) | `value:int` |
| `#entangle` | editable trait | Combat Auras (p.24) | flag |
| `#eyeloss` | editable trait | Combat Auras (p.24) | flag |
| `#fallpower` | editable trait | Seasonal Powers (p.24) | `percent:int` |
| `#fear` | editable trait | Combat Auras (p.24) | `value:int` |
| `#fireshield` | editable trait | Combat Auras (p.24) | `damage:int` |
| `#haltheretic` | editable trait | Combat Auras (p.24) | `bonus:int` |
| `#horrormark` | editable trait | Combat Auras (p.24) | flag |
| `#mindslime` | editable trait | Combat Auras (p.24) | `area:int` |
| `#nightmareaura` | editable trait | Combat Auras (p.24) | `area:int` |
| `#overcharged` | editable trait | Combat Auras (p.24) | `dmg:int` |
| `#sleepaura` | editable trait | Combat Auras (p.24) | `area:int` |
| `#slimer` | editable trait | Combat Auras (p.24) | `strength:int` |
| `#spikes` | editable trait | Combat Auras (p.24) | `dmg:int` |
| `#springpower` | editable trait | Seasonal Powers (p.24) | `percent:int` |
| `#summerpower` | editable trait | Seasonal Powers (p.24) | `percent:int` |
| `#sunawe` | editable trait | Combat Auras (p.24) | `bonus:int` |
| `#uwfireshield` | editable trait | Combat Auras (p.24) | `damage:int` |
| `#winterpower` | editable trait | Seasonal Powers (p.24) | `percent:int` |
| `#yearturn` | editable trait | Seasonal Powers (p.24) | `bonus:int` |
| `#aciddigest` | editable trait | Combat Abilities (p.25) | `dmg:int` |
| `#ambidextrous` | editable trait | Combat Abilities (p.25) | `bonus:int` |
| `#autoberserk` | editable trait | Combat Abilities (p.25) | `value:int` |
| `#berserk` | editable trait | Combat Abilities (p.25) | `bonus:int` |
| `#blessbers` | editable trait | Combat Abilities (p.25) | flag |
| `#blessfly` | editable trait | Combat Abilities (p.25) | flag |
| `#chaospower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#clumsy` | editable trait | Combat Abilities (p.25) | `value:int` |
| `#coldpower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#darkpower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#darkvision` | editable trait | Combat Abilities (p.25) | `percent:int` |
| `#deathpower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#digest` | editable trait | Combat Abilities (p.25) | `dmg:int` |
| `#dompower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#firepower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#growthpower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#guardspiritbonus` | editable trait | Combat Abilities (p.25) | `value:int` |
| `#incorporate` | editable trait | Combat Abilities (p.25) | `dmg:int` |
| `#invisible` | editable trait | Combat Abilities (p.25) | flag |
| `#magicpower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#raiseonkill` | editable trait | Combat Abilities (p.25) | `chance:int` |
| `#slothpower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#spiritsight` | editable trait | Combat Abilities (p.25) | flag |
| `#stormpower` | editable trait | Elemental & Scale Powers (p.25) | `bonus:int` |
| `#trample` | editable trait | Combat Abilities (p.25) | flag |
| `#trampswallow` | editable trait | Combat Abilities (p.25) | flag |
| `#truesight` | editable trait | Combat Abilities (p.25) | flag |
| `#unseen` | editable trait | Combat Abilities (p.25) | flag |
| `#appetite` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#beartattoo` | editable trait | Combat Abilities (p.26) | `value:int` |
| `#boartattoo` | editable trait | Combat Abilities (p.26) | `value:int` |
| `#castledef` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#deathcurse` | editable trait | Combat Abilities (p.26) | flag |
| `#deathdisease` | editable trait | Combat Abilities (p.26) | `aoe:int` |
| `#deathfire` | editable trait | Combat Abilities (p.26) | `aoe:int` |
| `#deathgrab` | editable trait | Combat Abilities (p.26) | `aoe:int` |
| `#deathparalyze` | editable trait | Combat Abilities (p.26) | `aoe:int` |
| `#deathpoison` | editable trait | Combat Abilities (p.26) | `aoe:int` |
| `#deathshock` | editable trait | Combat Abilities (p.26) | `aoe:int` |
| `#deathslime` | editable trait | Combat Abilities (p.26) | `aoe:int` |
| `#elegist` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#falsesupply` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#fearofflood` | editable trait | Combat Abilities (p.26) | `value:int` |
| `#heretic` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#horsetattoo` | editable trait | Combat Abilities (p.26) | `value:int` |
| `#iceforging` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#inquisitor` | editable trait | Non-Combat Abilities (p.26) | flag |
| `#mindcollar` | editable trait | Combat Abilities (p.26) | `dmg:int` |
| `#neednoteat` | editable trait | Non-Combat Abilities (p.26) | flag |
| `#patrolbonus` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#pillagebonus` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#powerofdeath` | editable trait | Combat Abilities (p.26) | `limit:int` |
| `#raiseshape` | editable trait | Combat Abilities (p.26) | `monster:mon` |
| `#resources` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#siegebonus` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#sleepres` | editable trait | Combat Abilities (p.26) | `bonus:int` |
| `#snaketattoo` | editable trait | Combat Abilities (p.26) | `value:int` |
| `#spreaddom` | editable trait | Non-Combat Abilities (p.26) | `candles:int` |
| `#supplybonus` | editable trait | Non-Combat Abilities (p.26) | `value:int` |
| `#wolftattoo` | editable trait | Combat Abilities (p.26) | `value:int` |
| `#addupkeep` | editable trait | Non-Combat Abilities (p.27) | `gold:int` |
| `#adeptsacr` | editable trait | Non-Combat Abilities (p.27) | `value:int` |
| `#alchemy` | editable trait | Non-Combat Abilities (p.27) | `percent:int` |
| `#decscale` | editable trait | Non-Combat Abilities (p.27) | `scale:int` |
| `#farthronekill` | editable trait | Non-Combat Abilities (p.27) | `part:int` |
| `#firstshape` | editable trait | Shape Changing (p.27) | `monster:monneg` |
| `#fortkill` | editable trait | Non-Combat Abilities (p.27) | `chance:int` |
| `#gold` | editable trait | Non-Combat Abilities (p.27) | `gold_month:int` |
| `#incprovdef` | editable trait | Non-Combat Abilities (p.27) | `value:int` |
| `#incscale` | editable trait | Non-Combat Abilities (p.27) | `scale:int` |
| `#incunrest` | editable trait | Non-Combat Abilities (p.27) | `value:int` |
| `#insanify` | editable trait | Non-Combat Abilities (p.27) | `percent:int` |
| `#leper` | editable trait | Non-Combat Abilities (p.27) | `percent:int` |
| `#localsun` | editable trait | Non-Combat Abilities (p.27) | flag |
| `#mason` | editable trait | Non-Combat Abilities (p.27) | flag |
| `#mindvessel` | editable trait | Non-Combat Abilities (p.27) | `value:int` |
| `#nobadevents` | editable trait | Non-Combat Abilities (p.27) | `value:int` |
| `#nohof` | editable trait | Non-Combat Abilities (p.27) | flag |
| `#popkill` | editable trait | Non-Combat Abilities (p.27) | `amount:int` |
| `#praise` | editable trait | Non-Combat Abilities (p.27) | `value:int` |
| `#prophetshape` | editable trait | Shape Changing (p.27) | `monster:monneg` |
| `#secondshape` | editable trait | Shape Changing (p.27) | `monster:monneg` |
| `#shapechange` | editable trait | Shape Changing (p.27) | `monster:mon` |
| `#shatteredsoul` | editable trait | Non-Combat Abilities (p.27) | `percent:int` |
| `#taxcollector` | editable trait | Non-Combat Abilities (p.27) | flag |
| `#thronekill` | editable trait | Non-Combat Abilities (p.27) | `chance:int` |
| `#airattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#animated` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#astralattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#autumnshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#battleshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#bloodattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#cleanshape` | editable trait | Shape Changing (p.28) | flag |
| `#deathattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#domshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#earthattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#fireattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#forcess` | editable trait | Shape Changing (p.28) | flag |
| `#foreignshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#forestshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#glamourattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#growhp` | editable trait | Shape Changing (p.28) | `hit_points:int` |
| `#homeshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#labxpshape` | editable trait | Shape Changing (p.28) | `xp_value:int` |
| `#landshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#lich` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#natureattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#notdomshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#plainshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#secondtmpshape` | editable trait | Shape Changing (p.28) | `monster:monneg` |
| `#shapechance` | editable trait | Shape Changing (p.28) | `percent:int` |
| `#shrinkhp` | editable trait | Shape Changing (p.28) | `hit_points:int` |
| `#springshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#summershape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#transformation` | editable trait | Shape Changing (p.28) | `value:int` |
| `#twiceborn` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#waterattuned` | editable trait | Shape Changing (p.28) | `chance:int` |
| `#watershape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#wintershape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#worldshape` | editable trait | Shape Changing (p.28) | `monster:mon` |
| `#xploss` | editable trait | Shape Changing (p.28) | `value:int` |
| `#xpshape` | editable trait | Shape Changing (p.28) | `xp_value:int` |
| `#xpshapeloss` | editable trait | Shape Changing (p.28) | `value:int` |
| `#xpshapemon` | editable trait | Shape Changing (p.28) | `monster:monneg` |
| `#batstartsum1` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum1d3` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum1d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum2` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum2d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum3` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum3d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum4` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum4d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum5` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum5d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum6d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum7d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum8d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#batstartsum9d6` | editable trait | Monster Summoning (p.29) | `monster:monneg` (repeatable) |
| `#battlesum1` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#battlesum1d2` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#battlesum1d3` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#battlesum2` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#battlesum3` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#battlesum4` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#battlesum5` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#battlesumwarm` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#domsummon` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#domsummon2` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#domsummon20` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#makemonsters1` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#makemonsters2` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#makemonsters3` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#makemonsters4` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#makemonsters5` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#montag` | editable trait | Monster Summoning (p.29) | `value:int` |
| `#raredomsummon` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#reanimator` | editable trait | Monster Summoning (p.29) | `nbr:int` |
| `#reanimpriest` | editable trait | Monster Summoning (p.29) | flag |
| `#summon1` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#summon2` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#summon3` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#summon4` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#summon5` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#templetrainer` | editable trait | Monster Summoning (p.29) | `monster:monneg` |
| `#airelementals` | editable trait | Monster Summoning (p.30) | `bonus:int` |
| `#coridermnr` | editable trait | Mounts & Riders (p.30) | `monster:mon` |
| `#corpselord` | editable trait | Monster Summoning (p.30) | `nbr:int` |
| `#dragonlord` | editable trait | Monster Summoning (p.30) | `nbr:int` |
| `#earthelementals` | editable trait | Monster Summoning (p.30) | `bonus:int` |
| `#faysummon` | editable trait | Monster Summoning (p.30) | `nbr:int` |
| `#fireelementals` | editable trait | Monster Summoning (p.30) | `bonus:int` |
| `#ivylord` | editable trait | Monster Summoning (p.30) | `nbr:int` |
| `#lamialord` | editable trait | Monster Summoning (p.30) | `nbr:int` |
| `#montagweight` | editable trait | Monster Summoning (p.30) | `weight:int` |
| `#mountmnr` | editable trait | Mounts & Riders (p.30) | `monster:mon` |
| `#nametype` | excluded | Nametypes (p.30) | Name/description text; not a trait (kept verbatim). |
| `#nofmounts` | editable trait | Mounts & Riders (p.30) | `mounts:int` |
| `#nofriders` | editable trait | Mounts & Riders (p.30) | `riders:int` |
| `#onisummon` | editable trait | Monster Summoning (p.30) | `value:int` |
| `#slaver` | editable trait | Monster Summoning (p.30) | `monster:monneg` |
| `#slaverbonus` | editable trait | Monster Summoning (p.30) | `modifier:int` |
| `#unmountedspr1` | excluded | Mounts & Riders (p.30) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#unmountedspr2` | excluded | Mounts & Riders (p.30) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#waterelementals` | editable trait | Monster Summoning (p.30) | `bonus:int` |
| `#bravemount` | editable trait | Mount commands (p.31) | `percent:int` |
| `#command` | editable trait | Normal Leadership (p.31) | `value:int` |
| `#expertleader` | editable field | Normal Leadership (p.31) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#goodleader` | editable field | Normal Leadership (p.31) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#mounted` | editable trait | Mounts & Riders (p.31) | flag |
| `#mountiscom` | editable trait | Mounts & Riders (p.31) | `value:int` |
| `#nobarding` | editable trait | Mounts & Riders (p.31) | flag |
| `#nofalldmg` | editable trait | Mounts & Riders (p.31) | flag |
| `#noleader` | editable field | Normal Leadership (p.31) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#noremount` | editable trait | Mounts & Riders (p.31) | flag |
| `#nothrowoff` | editable trait | Mounts & Riders (p.31) | flag |
| `#okleader` | editable field | Normal Leadership (p.31) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#poorleader` | editable field | Normal Leadership (p.31) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#regainmount` | editable trait | Mounts & Riders (p.31) | `value:int` |
| `#skilledrider` | editable trait | Mounts & Riders (p.31) | `value:int` |
| `#smartmount` | editable trait | Mount commands (p.31) | `smartness:int` |
| `#superiorleader` | editable field | Normal Leadership (p.31) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#xspr1` | excluded | Mounts & Riders (p.31) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#xspr2` | excluded | Mounts & Riders (p.31) | Sprite or look; not a trait (kept verbatim; edited with the artwork tools). |
| `#almostliving` | editable trait | Undead Leadership (p.32) | flag |
| `#almostundead` | editable trait | Undead Leadership (p.32) | flag |
| `#beastmaster` | editable trait | Morale Related Abilities (p.32) | `bonus:int` |
| `#bodyguard` | editable trait | Morale Related Abilities (p.32) | `bonus:int` |
| `#expertmagicleader` | editable trait | Magic Leadership (p.32) | flag |
| `#expertundeadleader` | editable trait | Undead Leadership (p.32) | flag |
| `#formationfighter` | editable trait | Morale Related Abilities (p.32) | `xsize:int` |
| `#goodmagicleader` | editable trait | Magic Leadership (p.32) | flag |
| `#goodundeadleader` | editable trait | Undead Leadership (p.32) | flag |
| `#inspirational` | editable trait | Morale Related Abilities (p.32) | `bonus:int` |
| `#magiccommand` | editable trait | Magic Leadership (p.32) | `value:int` |
| `#nomagicleader` | editable trait | Magic Leadership (p.32) | flag |
| `#noundeadleader` | editable trait | Undead Leadership (p.32) | flag |
| `#okmagicleader` | editable trait | Magic Leadership (p.32) | flag |
| `#okundeadleader` | editable trait | Undead Leadership (p.32) | flag |
| `#poormagicleader` | editable trait | Magic Leadership (p.32) | flag |
| `#poorundeadleader` | editable trait | Undead Leadership (p.32) | flag |
| `#slave` | editable trait | Morale Related Abilities (p.32) | flag |
| `#standard` | editable trait | Morale Related Abilities (p.32) | `bonus:int` |
| `#superiormagicleader` | editable trait | Magic Leadership (p.32) | flag |
| `#superiorundeadleader` | editable trait | Undead Leadership (p.32) | flag |
| `#taskmaster` | editable trait | Morale Related Abilities (p.32) | `bonus:int` |
| `#undcommand` | editable trait | Undead Leadership (p.32) | `value:int` |
| `#undisciplined` | editable trait | Morale Related Abilities (p.32) | flag |
| `#warning` | editable trait | Morale Related Abilities (p.32) | `bonus:int` |
| `#airrange` | editable trait | Spell Range (p.33) | `range:int` |
| `#astralrange` | editable trait | Spell Range (p.33) | `range:int` |
| `#custommagic` | editable trait | Magic Paths (p.33) | `mask:pathmask` `chance:int` (repeatable) |
| `#earthrange` | editable trait | Spell Range (p.33) | `range:int` |
| `#firerange` | editable trait | Spell Range (p.33) | `range:int` |
| `#latehero` | editable trait | Morale Related Abilities (p.33) | `min_turn:int` |
| `#magicboost` | editable trait | Magic Paths (p.33) | `path:int` `boost:int` (repeatable) |
| `#magicskill` | editable field | Magic Paths (p.33) | Edited by the dedicated stats, leadership, magic path or pretender field of the same editor. |
| `#masterrit` | editable trait | Magic Paths (p.33) | `value:int` |
| `#tolerateund` | editable trait | Morale Related Abilities (p.33) | flag |
| `#undisleader` | editable trait | Morale Related Abilities (p.33) | `value:int` |
| `#waterrange` | editable trait | Spell Range (p.33) | `range:int` |
| `#allrange` | editable trait | Spell Range (p.34) | `range:int` |
| `#bloodrange` | editable trait | Spell Range (p.34) | `range:int` |
| `#deathrange` | editable trait | Spell Range (p.34) | `range:int` |
| `#divineins` | editable trait | Magic Research (p.34) | flag |
| `#drainimmune` | editable trait | Magic Research (p.34) | flag |
| `#elementgems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#elementrange` | editable trait | Spell Range (p.34) | `range:int` |
| `#fixedresearch` | editable trait | Magic Research (p.34) | `value:int` |
| `#gemprod` | editable trait | Gem Production (p.34) | `type:int` `number:int` (repeatable) |
| `#glamourrange` | editable trait | Spell Range (p.34) | `range:int` |
| `#holyrange` | editable trait | Spell Range (p.34) | `range:int` |
| `#inspiringres` | editable trait | Magic Research (p.34) | `value:int` |
| `#magicimmune` | editable trait | Magic Research (p.34) | flag |
| `#naturerange` | editable trait | Spell Range (p.34) | `range:int` |
| `#researchbonus` | editable trait | Magic Research (p.34) | `value:int` |
| `#slothresearch` | editable trait | Magic Research (p.34) | `value:int` |
| `#sorcerygems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#sorceryrange` | editable trait | Spell Range (p.34) | `range:int` |
| `#tmpairgems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#tmpastralgems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#tmpbloodslaves` | editable trait | Gem Production (p.34) | `slaves:int` |
| `#tmpdeathgems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#tmpearthgems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#tmpfiregems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#tmpglamourgems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#tmpnaturegems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#tmpwatergems` | editable trait | Gem Production (p.34) | `gems:int` |
| `#3castbattlespell` | editable trait | Other Magic Abilities (p.35) | `spell:spell` |
| `#allret` | editable trait | Other Magic Abilities (p.35) | `chance:int` |
| `#bonusspells` | editable trait | Other Magic Abilities (p.35) | `spells:int` |
| `#carcasscollector` | editable trait | Gem Production (p.35) | `value:int` |
| `#chorusmaster` | editable trait | Other Magic Abilities (p.35) | flag |
| `#chorusslave` | editable trait | Other Magic Abilities (p.35) | flag |
| `#commaster` | editable trait | Other Magic Abilities (p.35) | flag |
| `#comslave` | editable trait | Other Magic Abilities (p.35) | flag |
| `#crossbreeder` | editable trait | Other Magic Abilities (p.35) | `value:int` |
| `#deathbanish` | editable trait | Other Magic Abilities (p.35) | `value:int` |
| `#douse` | editable trait | Gem Production (p.35) | `bonus:int` |
| `#fastcast` | editable trait | Other Magic Abilities (p.35) | `speedup:int` |
| `#fixforgebonus` | editable trait | Other Magic Abilities (p.35) | `value:int` |
| `#forgebonus` | editable trait | Other Magic Abilities (p.35) | `percent:int` |
| `#glamourmanip` | editable trait | Other Magic Abilities (p.35) | `value:int` |
| `#grandcom` | editable trait | Other Magic Abilities (p.35) | `value:int` |
| `#indepspells` | editable trait | Other Magic Abilities (p.35) | `level:int` |
| `#infernoret` | editable trait | Other Magic Abilities (p.35) | `chance:int` |
| `#kokytosret` | editable trait | Other Magic Abilities (p.35) | `chance:int` |
| `#magicstudy` | editable trait | Other Magic Abilities (p.35) | `bonus:int` |
| `#makepearls` | editable trait | Gem Production (p.35) | `value:int` |
| `#mastersmith` | editable trait | Other Magic Abilities (p.35) | `value:int` |
| `#onebattlespell` | editable trait | Other Magic Abilities (p.35) | `spell:spell` |
| `#randomspell` | editable trait | Other Magic Abilities (p.35) | `percent:int` |
| `#sabbathslave` | editable trait | Other Magic Abilities (p.35) | flag |
| `#spellsinger` | editable trait | Other Magic Abilities (p.35) | flag |
| `#tainted` | editable trait | Other Magic Abilities (p.35) | `chance:int` |
| `#voidret` | editable trait | Other Magic Abilities (p.35) | `chance:int` |
| `#bringeroffortune` | editable trait | New Abilities for Dominions 5 (p.36) | `value:int` |
| `#combatcaster` | editable trait | New Abilities for Dominions 5 (p.36) | flag |
| `#minsizeleader` | editable trait | New Abilities for Dominions 5 (p.36) | `value:int` |
| `#skirmisher` | editable trait | New Abilities for Dominions 5 (p.36) | `value:int` |
| `#unsurr` | editable trait | New Abilities for Dominions 5 (p.36) | `value:int` |
