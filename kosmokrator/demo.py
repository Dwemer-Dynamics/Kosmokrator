"""Build a small generic sample nation through the same core operations agents use.

Flow: create_project -> allocate_ids -> write generated flag -> apply_mod_patch
(single insertion against the inspected SHA-256) -> validate_mod -> optional export.
The synthetic fixture copies two vanilla units by number (sprites are referenced, not
redistributed) and writes a programmatically generated flag. It has no theme or lore.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

from .catalog import Catalog
from .export import export_mod
from .paths import contained
from .project import allocate_ids, apply_mod_patch, create_project, inspect_mod, open_project
from .tga import nation_flag
from .validate import validate_project

FLAG_REL = "art/sample_flag.tga"

# key -> (vanilla base monster number, base name in catalog) ; order = allocation order.
MONSTERS = [
    ("TROOP", 199, "Cardaces"),
    ("COMMANDER", 311, "Mystic"),
]
SITES = ["SITE"]

TEMPLATE = Template(r"""
-- ===== Sample nation (Kosmokrator demo fixture) =====
-- All new objects use ids reserved with allocate_ids. Bases are vanilla monsters copied by number.

#newmonster $TROOP
#copystats 199
#copyspr 199
#name "Sample Infantry"
#descr "Generic sample infantry."
#end

#newmonster $COMMANDER
#copystats 311
#copyspr 311
#name "Sample Commander"
#descr "Generic sample commander."
#end

#newsite $SITE
#name "Sample Site"
#path 0
#level 0
#rarity 5
#gems 0 1
#end

#selectnation $NATION
#name "Sample Nation"
#epithet "Example Fixture"
#era 1
#descr "Generic sample nation built by the Kosmokrator demo."
#summary "Sample fixture for tooling checks."
#brief "Sample fixture."
#clearnation
#clearrec
#clearsites
#flag "$FLAG"
#startsite "Sample Site"
#addrecunit $TROOP
#addreccom $COMMANDER
#startcom $COMMANDER
#startunittype1 $TROOP
#startunitnbrs1 10
#end
""")


def render(ids: dict[str, int]) -> str:
    return TEMPLATE.substitute({**{k: str(v) for k, v in ids.items()}, "FLAG": FLAG_REL}).lstrip("\n")


def build_demo(workspace: Path, slug: str = "sample_mod", catalog: Catalog | None = None,
               export: str | None = None, export_dest: str | None = None) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    created = create_project(workspace, slug, name="Sample Mod",
                             description="Kosmokrator demo: a small generic sample nation. "
                                         "Static validation only; test in game.")
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
    flag_path = contained(project.mod_dir, FLAG_REL, what="flag asset")
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    with open(flag_path, "xb") as fh:
        fh.write(nation_flag("sample_mod", (54, 89, 119), "spear"))
    steps.append({"op": "write_asset", "path": project.rel(flag_path)})

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
