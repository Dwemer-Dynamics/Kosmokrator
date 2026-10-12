# Demo: Hebdomad, Forges of the False Heaven

An Early Age fire and earth nation. `kosmokrator demo` builds it with the same operations an agent uses:
`create_project`, then `allocate_ids` (13 monsters: 11 roster units and 2 pretender forms; 2 sites; 1 nation), then writes the flag TGA and the four packaged pretender frames, then
calls `apply_mod_patch` (a single insertion checked against the inspected sha256), then `validate_mod`,
and optionally `export_mod`. There is no pre-built zip; the template lives in `kosmokrator/demo.py`.

## Theme (original lore, inspired by)
The demo draws loosely on Archontic themes from the *Apocryphon of John* and the *Hypostasis of the
Archons* (gnosis.org translations). It is not a historical or theological account. The ideas it uses:
- **Matter**: the forge-cities and the brass "false heaven" shaped by a lesser maker.
- **Archons**: seven rulers and wardens of the spheres who half-believe they are gods.
- **The divine spark**: a light inside every forged thing that no forge made.
- **Gnosis**: knowing that spark. It is taught quietly by priests and kindlers, tolerated and watched.

## Roster (vanilla bases copied by number; sprites via `#copyspr`, no vanilla sprites redistributed)
| Role | Name | Base (id) | Overrides |
| --- | --- | --- | --- |
| Troop | Hylic Spearman | Cardaces (199) | description |
| Troop | Smoke Slinger | Slinger (50) | description |
| Troop | Brazen Warden | Myrmidon (1077) | `#fireres 5` |
| Troop | Iron Warden | Iron Warrior (1156) | `#clearspec`, `#mountainsurvival` |
| Sacred troop (capital only) | Sealbearer of the Seventh Gate | Myrmidon (1077) | `#holy`, `#fireres 5`, `#mor 14` |
| Scout | Watcher of the Lower Spheres | Scout (431) | description |
| Leader | Hebdomad Strategos | Myrmidon Champion (1076) | description |
| Priest | Pneumatic Hierophant | Mystic (311) | `#clearmagic`, H2, `#holy` |
| Small fire mage | Kindler of the Lamp | Mystic (311) | `#clearmagic`, F1, 10% F/E random |
| Earth mage | Smith of the Firmament | Warrior Smith (1159) | `#clearmagic #clearspec`, E2, 50% F/E random, forge bonus 1 |
| Capital-only archon | Archon of the Seventh Sphere | Archon (3116) | `#clearmagic #clearspec`, F2 E2 H1, 100% F/E random, `#holy`, `#fireres 5` |

Base ids were checked in the dom6inspector catalog at rev 68904be. Mages clear their inherited magic, and
the smith and archon also clear inherited special abilities, re-adding only what they need.

## Pretender gods (first-draft proposal)
Two national gods, monsters 5011 and 5012. They are pretender forms only: the nation adds them with `#addgod`,
and no recruitment command names them, so the recruitable roster stays at 11. Both use `#homerealm 0`, so they
are not offered to other nations in their donors' realms. They are archetypes themed on the myth, not claims
about historical theology, and they have not been balance-tested.

| Name | Donor (id) | Magic | `#startdom` | `#pathcost` | `#gcost` |
| --- | --- | --- | --- | --- | --- |
| Demiurge of the Brass Heaven | Great Archon (3416) | F1 E1 (donor S1 removed) | 3 | 60 | 10060 |
| Sophia of the Hidden Spark | Great Enchantress (485) | S1 G1 | 1 | 20 | 10040 |

- Each block uses `#copystats`, `#clearmagic` and `#clearspec`. The manual says dominion strength and path cost
  are special abilities, so `#startdom` and `#pathcost` are set after `#clearspec`. Sophia restores `#female`.
- `#gcost` is 10000 plus an autocalc adjustment (+60 and +40). The donors' values are 10020 and 10000. This is
  not a final design-point cost; the game autocalculates pretender points from attributes and abilities.
- `#clearspec` is expected to remove the donors' spirit sight, alchemy and `moremagic` dominion trait (Great
  Archon) and Glamour gem income and independent spells (Great Enchantress). This is not reproduced in game.
- Demiurge equipment matches its humanoid sword art: `#clearweapons` then `#weapon 11` (Great Sword, one sword
  attack), and `#cleararmor` then `#armor 100` (Bronze Cuirass, checked in the catalog). The donor's Scourge of
  Power, two Serpent Leg attacks and Shield of Wisdom are gone. Tradeoff: fewer attacks than the donor and no
  shield, so it is a weaker melee god than a Great Archon; final design points may also shift. The flame on the
  blade is decorative for this first build and has no fire damage. Sophia keeps the Great Enchantress's
  Quarterstaff.
- The nation also keeps `#homerealm 3`, so vanilla Mediterranean gods remain available. Realm 10 (Default)
  is not declared.

## Nation
- `#selectnation <allocated>` in the unused 150+ range, `#era 1`, then `#clearnation #clearrec #clearsites`.
- **Start sites** (new, rarity 5, level 0), assigned with `#startsite` by name:
  - *The Furnace of the Seventh Gate*: fire path, 2 fire gems, `#homecom` Archon.
  - *The Quarry of Sealed Matter*: earth path, 2 earth gems, `#homemon` Sealbearer.
- **Start army:** Strategos with 15 Brazen Wardens and 15 Smoke Slingers, plus a Watcher scout.
- **Province defence:** Strategos commanders, Hylic Spearmen (Ã—20 multiplier), Slingers, Wardens at PD 20+;
  wall and gate defenders.
- **Pretenders:** `#homerealm 3` (Mediterranean realm; the catalog lists e.g. Titan of the Forge,
  Demiurge and Great Archon for that realm), plus `#addgod` for the two national gods above. No realm 10.
- **Flag:** original 128Ã—128 32-bit TGA generated with the stdlib (an ember banner, a dark "matter" disc, a
  bright spark and seven gold spheres), at `art/hebdomad_flag.tga`.
- AI hints: `#aifirenation`, `#aiearthnation`. The nation uses no complex or untested mechanics (no
  shapechange, events or custom spells).

## Artwork scope

The demo uses vanilla sprite references for its 11 roster units and includes four
original pretender frames from `kosmokrator/demo_assets/pretenders/`. Source sheets
and historical replacement-art sets are not included in this distribution.

This lightweight starter is an explicit demo exception to the complete original-art
requirements in [ASSET-RULESET.md](ASSET-RULESET.md). New nation requests follow those
requirements unless the user requests a prototype or reused artwork.

## Not verified
See [HEBDOMAD-REVIEW.md](HEBDOMAD-REVIEW.md) for the current source review, including inherited prophet
transformation risks, roster overlap, recruitment economics and the proposed playtesting matrix.

Gold costs come from inherited autocalc values. Balance, AI behaviour and whether the game honours the
realm gods for this era have not been tested in game. Neither has whether the two national gods appear on the
pretender screen, their final design points, or what `#clearspec` removed from them. Load the mod and check
before relying on it.

- **Mod banner:** packaged original 256x64 TGA, referenced by `#icon "mod_banner.tga"`.
