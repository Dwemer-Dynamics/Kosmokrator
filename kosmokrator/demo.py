"""Build the Hebdomad demo nation through the same core operations agents use.

Flow: create_project -> allocate_ids -> write original flag -> apply_mod_patch
(single insertion against the inspected SHA-256) -> validate_mod -> optional export.
Vanilla bases (copystats/copyspr) were checked against the dom6inspector catalog at
revision 68904be; the 11 roster units reuse vanilla sprites by number, not redistributed.
The two national pretenders ship original 64x64 frames from package data (PRETENDER_ART),
written under art/pretenders/ and referenced with #spr1/#spr2.
Lore is original and only inspired by Sethian/Archontic themes (Apocryphon of John,
Hypostasis of the Archons); it is not a historical account.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

from .catalog import Catalog
from .export import export_mod
from .paths import contained
from .project import allocate_ids, apply_mod_patch, create_project, inspect_mod, open_project
from .tga import hebdomad_flag
from .validate import validate_project

FLAG_REL = "art/hebdomad_flag.tga"
# Processed pretender frames (assets/hebdomad-pretenders/sprites), packaged as kosmokrator/demo_assets.
# Source sheets are not packaged.
PRETENDER_ART_DIR = Path(__file__).resolve().parent / "demo_assets" / "pretenders"
PRETENDER_ART_REL = "art/pretenders"
PRETENDER_ART = ["brass_demiurge_idle.png", "brass_demiurge_attack.png",
                 "hidden_spark_idle.png", "hidden_spark_attack.png"]

# key -> (vanilla base monster number, base name in catalog) ; order = allocation order.
MONSTERS = [
    ("SPEAR", 199, "Cardaces"),
    ("SLING", 50, "Slinger"),
    ("WARDEN", 1077, "Myrmidon"),
    ("IRON", 1156, "Iron Warrior"),
    ("SEAL", 1077, "Myrmidon"),
    ("WATCHER", 431, "Scout"),
    ("STRATEGOS", 1076, "Myrmidon Champion"),
    ("HIEROPHANT", 311, "Mystic"),
    ("KINDLER", 311, "Mystic"),
    ("SMITH", 1159, "Warrior Smith"),
    ("ARCHON", 3116, "Archon"),
    # National pretender forms: added only with #addgod, never recruitable.
    ("DEMIURGE", 3416, "Great Archon"),
    ("SOPHIA", 485, "Great Enchantress"),
]
SITES = ["FURNACE", "QUARRY"]

TEMPLATE = Template(r"""
-- ===== Hebdomad, Forges of the False Heaven (Kosmokrator demo) =====
-- All new objects use ids reserved with allocate_ids. Bases are vanilla monsters
-- copied by number; magic and special abilities are cleared where inherited.

-- ----- Troops -----
#newmonster $SPEAR
#copystats 199
#copyspr 199
#name "Hylic Spearman"
#descr "Levies of the lower forge-cities, men and women of clay and sweat who are told that the weight of the world is their virtue. They carry spear and shield in close order and rarely ask what lies above the smoke."
#end

#newmonster $SLING
#copystats 50
#copyspr 50
#name "Smoke Slinger"
#descr "Youths of the slag-heaps who sling shot cast from the forges' waste. They are counted among the lightest of the bound and are spent freely."
#end

#newmonster $WARDEN
#copystats 1077
#copyspr 1077
#name "Brazen Warden"
#descr "Drilled wardens in bronze who keep the stairways between the forge-cities. They are taught that each sphere above is a locked door, and that a warden's duty is to hold the key and never turn it."
#fireres 5
#end

#newmonster $IRON
#copystats 1156
#copyspr 1156
#clearspec
#mountainsurvival
#name "Iron Warden"
#descr "Heavy infantry quenched in the deepest forges. Their armour is said to be stamped with the seal of the Archon who owns them, so that even their deaths are recorded as property."
#end

#newmonster $SEAL
#copystats 1077
#copyspr 1077
#name "Sealbearer of the Seventh Gate"
#descr "Sacred guardians who carry the seals of the seven gates. They believe the seals keep chaos out; the hidden teachers say the seals keep the spark in. Only the capital's furnace-temple can consecrate them."
#holy
#fireres 5
#mor 14
#end

-- ----- Commanders -----
#newmonster $WATCHER
#copystats 431
#copyspr 431
#name "Watcher of the Lower Spheres"
#descr "Scouts who walk the ash-roads between provinces, reporting every unlicensed fire and every whisper of gnosis."
#end

#newmonster $STRATEGOS
#copystats 1076
#copyspr 1076
#name "Hebdomad Strategos"
#descr "Captains appointed by the Archons. They command well and believe little, which the Archons find restful."
#end

#newmonster $HIEROPHANT
#copystats 311
#copyspr 311
#prophetshape $HIEROPHANT
#clearmagic
#magicskill 9 2
#holy
#name "Pneumatic Hierophant"
#descr "Priests of the furnace-temples who preach the Archons' law by day. In private some of them teach that the divine spark in each soul is older than any forge and answers to no Archon."
#end

#newmonster $KINDLER
#copystats 311
#copyspr 311
#prophetshape $KINDLER
#clearmagic
#magicskill 0 1
#custommagic 1152 10
#name "Kindler of the Lamp"
#descr "Minor fire-adepts who keep the temple lamps lit. Their art is small, but they are the first to notice when a flame burns with a light that the forges did not make."
#end

#newmonster $SMITH
#copystats 1159
#copyspr 1159
#clearmagic
#clearspec
#magicskill 3 2
#custommagic 1152 50
#fixforgebonus 1
#mountainsurvival
#name "Smith of the Firmament"
#descr "Earth-mages who hammer molten stone into the brass vaults of the false heaven. They shape matter so well that they forget it was ever shaped."
#end

#newmonster $ARCHON
#copystats 3116
#copyspr 3116
#clearmagic
#clearspec
#magicskill 0 2
#magicskill 3 2
#magicskill 9 1
#custommagic 1152 100
#holy
#fireres 5
#name "Archon of the Seventh Sphere"
#descr "One of the seven rulers set over the spheres, a towering lord of fire and stone who keeps the gate of its sphere and half-believes it is a god. It knows the world of matter intimately and the light beyond it not at all. Only the capital's furnace answers its summons."
#end

-- ----- Pretender gods (national; added only by #addgod, no homerealm) -----
-- First-draft, vanilla-based proposals. Themed on Archontic myth, not historical theology.
-- Not balance-tested. #clearspec also clears dominion and path cost (manual, Monster Modding: Special Abilities), so they are set after it.
-- Demiurge equipment matches the humanoid sword art: donor Scourge of Power, Serpent Legs and Shield of
-- Wisdom are cleared; Great Sword (11) and Bronze Cuirass (100) only. The flame on the blade is decorative.
#newmonster $DEMIURGE
#copystats 3416
#spr1 "$ART/brass_demiurge_idle.png"
#spr2 "$ART/brass_demiurge_attack.png"
#name "Demiurge of the Brass Heaven"
#descr "The lesser maker who hammered out the world of matter and set seven brass heavens over it. It wears the face of a lion and armour of its own forging, and believes no light shines above its vaults. The Archons call it Father; the hidden teachers call it the one who mistook its reflection for the sky."
#clearweapons
#weapon 11
#cleararmor
#armor 100
#clearmagic
#clearspec
#magicskill 0 1
#magicskill 3 1
#startdom 3
#pathcost 60
#homerealm 0
#gcost 10060
#end

#newmonster $SOPHIA
#copystats 485
#spr1 "$ART/hidden_spark_idle.png"
#spr2 "$ART/hidden_spark_attack.png"
#name "Sophia of the Hidden Spark"
#descr "A frail woman in a pale, muted robe who carries a staff and a small lamp. The forge-cities do not admit that she exists. The hidden teachers say she is the wisdom whose fall gave the world its spark, and that she walks the ash-roads to remind every forged thing of the light it came from."
#clearmagic
#clearspec
#female
#magicskill 4 1
#magicskill 7 1
#startdom 1
#pathcost 20
#homerealm 0
#gcost 10040
#end

-- ----- Start sites -----
#newsite $FURNACE
#name "The Furnace of the Seventh Gate"
#path 0
#level 0
#rarity 5
#gems 0 2
#homecom $ARCHON
#end

#newsite $QUARRY
#name "The Quarry of Sealed Matter"
#path 3
#level 0
#rarity 5
#gems 3 2
#homemon $SEAL
#end

-- ----- Nation -----
#selectnation $NATION
#name "Hebdomad"
#epithet "Forges of the False Heaven"
#era 1
#descr "Beneath seven brass heavens lie the forge-cities of the Hebdomad. Their people are taught that the world of matter was hammered out by a lesser maker who mistook its own reflection for the only light, and that seven Archons were set as smiths and wardens over every gate between earth and sky. The Archons teach that obedience tempers the soul as fire tempers bronze. Yet in the furnace-temples a quieter teaching survives: within every forged thing sleeps a spark that did not come from any forge, and gnosis - knowing that spark - is the only key that the Archons cannot hold. The Hebdomad fields spearmen, slingers and bronze wardens, raises Sealbearers and Archons only at its capital, and relies on mages of fire and earth."
#summary "Race: Humans of the forge-cities. Military: Spearmen, slingers, bronze and iron wardens; sacred Sealbearers recruitable only at the capital. Magic: Fire, Earth, some Holy. Capital-only Archons of fire and earth. Start sites give fire and earth gems."
#brief "Early-era forge-state ruled by fire and earth Archons beneath a false heaven."
#clearnation
#clearrec
#clearsites
#color 0.80 0.32 0.10
#secondarycolor 0.30 0.24 0.20
#flag "$FLAG"
#idealcold -1
#fortera 1
#templepic 2
#startsite "The Furnace of the Seventh Gate"
#startsite "The Quarry of Sealed Matter"
#homerealm 3
#addgod $DEMIURGE
#addgod $SOPHIA
#aifirenation
#aiearthnation
#addrecunit $SPEAR
#addrecunit $SLING
#addrecunit $WARDEN
#addrecunit $IRON
#addreccom $WATCHER
#addreccom $STRATEGOS
#addreccom $HIEROPHANT
#addreccom $KINDLER
#addreccom $SMITH
#startcom $STRATEGOS
#startscout $WATCHER
#startunittype1 $WARDEN
#startunitnbrs1 15
#startunittype2 $SLING
#startunitnbrs2 15
#defcom1 $STRATEGOS
#defcom2 $STRATEGOS
#defunit1 $SPEAR
#defmult1 20
#defunit1b $SLING
#defmult1b 10
#defunit2 $WARDEN
#defmult2 10
#wallcom $STRATEGOS
#wallunit $SLING
#wallmult 10
#guardcom $STRATEGOS
#guardunit $WARDEN
#guardmult 10
#end
""")


def render(ids: dict[str, int]) -> str:
    return TEMPLATE.substitute({**{k: str(v) for k, v in ids.items()}, "FLAG": FLAG_REL,
                               "ART": PRETENDER_ART_REL}).lstrip("\n")


def build_demo(workspace: Path, slug: str = "hebdomad", catalog: Catalog | None = None,
               export: str | None = None, export_dest: str | None = None) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    created = create_project(workspace, slug, name="Hebdomad - Forges of the False Heaven",
                             description="Kosmokrator demo: an Early Age fire and earth nation inspired by "
                                         "Archontic myth. Static validation only; test in game.")
    steps.append({"op": "create_project", "dm_path": created["dm_path"]})
    ids: dict[str, int] = {}
    mons = allocate_ids(workspace, slug, "monster", len(MONSTERS), labels=[m[0] for m in MONSTERS], catalog=catalog)
    ids.update({key: i for (key, _, _), i in zip(MONSTERS, mons["ids"])})
    sites = allocate_ids(workspace, slug, "site", len(SITES), labels=SITES, catalog=catalog)
    ids.update(dict(zip(SITES, sites["ids"])))
    nation = allocate_ids(workspace, slug, "nation", 1, labels=["NATION"], catalog=catalog)
    ids["NATION"] = nation["ids"][0]
    steps.append({"op": "allocate_ids", "ids": ids})

    project = open_project(workspace, slug)
    from importlib.resources import files
    (project.mod_dir / "mod_banner.tga").write_bytes(
        files("kosmokrator").joinpath("demo_assets/hebdomad_banner.tga").read_bytes())
    flag_path = contained(project.mod_dir, FLAG_REL, what="flag asset")
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    with open(flag_path, "xb") as fh:
        fh.write(hebdomad_flag())
    steps.append({"op": "write_asset", "path": project.rel(flag_path)})
    for name in PRETENDER_ART:
        art_path = contained(project.mod_dir, f"{PRETENDER_ART_REL}/{name}", what="pretender asset")
        art_path.parent.mkdir(parents=True, exist_ok=True)
        with open(art_path, "xb") as fh:
            fh.write((PRETENDER_ART_DIR / name).read_bytes())
        steps.append({"op": "write_asset", "path": project.rel(art_path)})

    info = inspect_mod(workspace, slug)
    line_count = project.dm_path.read_bytes().count(b"\n")
    patch = apply_mod_patch(workspace, slug, info["sha256"], insert_line=line_count + 1, text="\n" + render(ids))
    steps.append({"op": "apply_mod_patch", "before_sha256": patch["before_sha256"],
                  "after_sha256": patch["after_sha256"], "backup": patch["backup"]})

    report = validate_project(workspace, slug, catalog=catalog)
    steps.append({"op": "validate_mod", "ok": report["ok"], "counts": report["counts"]})
    result: dict[str, Any] = {"project": slug, "root": created["root"], "ids": ids, "steps": steps,
                              "validation": report}
    if export:
        if not report["ok"]:
            result["export"] = {"skipped": "validation reported errors"}
        else:
            result["export"] = export_mod(workspace, slug, dest=export_dest, fmt=export, catalog=catalog)
    return result
