"""Pretender (god) view for the read-only browser.

Lists, per nation, the gods a static reading of the .dm and the supplied catalog makes plausible, keeping four
things apart: vanilla realm candidates (dom6inspector realms.csv), the nation's explicit god commands
(#addgod/#delgod/#cleargods/#cheapgod20/#cheapgod40/#noundeadgods), project-defined god objects, and the
constraints this view cannot resolve. Rules follow the modding manual (6.36, "Pretender God Commands" and
nation "Gods"). Where the manual is silent, the reading is conservative and the entry is marked provisional.

This is not the game's god list. Final design-point costs are never computed, and nothing here proves that a god
appears in game.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .catalog import Catalog, _read_table
from .dmparse import Block
from .errors import KosmoError
from .paths import is_link

REALM_NAMES = {1: "North", 2: "Celtic", 3: "Mediterranean", 4: "Far East", 5: "Middle East",
               6: "Middle America", 7: "Africa", 8: "India", 9: "Deeps", 10: "Default"}
PATHS = ["F", "A", "W", "E", "S", "D", "N", "G", "B", "H"]
PATH_NAMES = dict(zip(PATHS, ["Fire", "Air", "Water", "Earth", "Astral", "Death", "Nature", "Glamour", "Blood",
                              "Holy"]))
STAT_FIELDS = ["hp", "size", "prot", "mr", "mor", "str", "att", "def", "prec", "enc", "mapmove", "ap"]
# dom6inspector attributes_by_nation codes (attribute_keys.csv).
ATTR_HOMEREALM, ATTR_CHEAPGOD20, ATTR_CHEAPGOD40 = "289", "314", "315"
# MNation.js skips this id from pretender_types_by_nation ("Why is royal guard marked as pretender?").
INSPECTOR_SKIPPED_PRETENDER = 134
GCOST_FIXED_BELOW = 5000
SPRITE_FRAMES = {"idle": 1, "attack": 2}
GOD_COMMANDS = {"clearnation", "cleargods", "homerealm", "addgod", "delgod", "cheapgod20", "cheapgod40",
                "noundeadgods"}
REALM10_NOTE = ("Realm 10 (Default) is not added implicitly. The manual lists it as an ordinary realm number, and "
                "the catalog stores it per nation: most vanilla nations declare it (e.g. EA Arcoscephale 3 and "
                "10) but some do not (e.g. EA Mekone 3 only).")

_LOCK = threading.Lock()
_TABLES: dict[tuple[str, str], list[dict[str, str]]] = {}


def _int(v: Any) -> int | None:
    s = str(v).strip() if v is not None else ""
    return int(s) if s.lstrip("-").isdigit() else None


def _table(catalog: Catalog | None, name: str) -> list[dict[str, str]]:
    """Read an auxiliary dom6inspector table once per catalog; missing tables read as empty."""
    if catalog is None:
        return []
    key = (str(catalog.gamedata), name)
    with _LOCK:
        if key not in _TABLES:
            p = catalog.gamedata / name
            _TABLES[key] = _read_table(p) if p.is_file() and not is_link(p) else []
        return _TABLES[key]


def _units(catalog: Catalog | None) -> dict[int, dict[str, str]]:
    if catalog is None:
        return {}
    out = {}
    for r in catalog.table("units"):
        i = _int(r.get("id"))
        if i is not None:
            out[i] = r
    return out


def realm_members(catalog: Catalog | None) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for r in _table(catalog, "realms.csv"):
        m, realm = _int(r.get("monster_number")), _int(r.get("realm"))
        if m is not None and realm is not None:
            out.setdefault(realm, []).append(m)
    return out


def catalog_sprite_path(catalog: Catalog | None, monster_id: int, frame: str) -> Path | None:
    """The inspector's sprite file for one catalog monster (images/sprites/NNNN_1|2.png), or None.

    Built only from an integer id and a fixed frame name, never from request text."""
    if catalog is None or frame not in SPRITE_FRAMES or not isinstance(monster_id, int) or monster_id < 0:
        return None
    base = catalog.gamedata.parent / "images" / "sprites"
    p = base / f"{monster_id:04d}_{SPRITE_FRAMES[frame]}.png"
    for part in (base.parent, base, p):
        if is_link(part):
            return None
    return p if p.is_file() else None


def _f(value: Any, source: str, line: int | None = None, status: str = "resolved", note: str | None = None
       ) -> dict[str, Any]:
    out: dict[str, Any] = {"value": value, "source": source, "line": line, "status": status}
    if note:
        out["note"] = note
    return out


def design_points(raw: int | None, source: str, line: int | None, command: str = "#gcost") -> dict[str, Any]:
    """The #gcost (catalog basecost) component as a design-point encoding. Never a final cost."""
    out: dict[str, Any] = {"command": command, "column": "basecost", "authored_value": raw, "source": source,
                           "line": line, "final": None, "status": "unresolved"}
    if raw is None:
        out.update(interpretation="unset", note="No value; the game default applies and is not modelled.")
    elif raw < GCOST_FIXED_BELOW:
        out.update(interpretation="fixed", note=(
            f"{raw} is stored as a fixed cost (inspector convention: below {GCOST_FIXED_BELOW}). The manual says "
            "shape-changing pretenders should use fixed costs. Dominion, magic and scale purchases and nation "
            "discounts are added by the game and not computed."))
    else:
        out.update(interpretation="autocalc_encoded", base=raw - 10000, note=(
            f"{raw} = 10000 + base {raw - 10000}: the game autocalculates the pretender's design points from its "
            "attributes and abilities (pretender rules differ from unit autocalc) and adds the base. The final "
            "points are not computed here."))
    return out


def _catalog_god(c: Any, mid: int, row: dict[str, str]) -> dict[str, Any]:
    """A vanilla god object from its raw catalog row (values as stored, not effective)."""
    cat = c.catalog
    realms = sorted({r for r in (_int(row.get(k)) for k in ("realm1", "realm2", "realm3")) if r})
    specials = {k: row[k].strip() for k in ("holy", "female", "undead", "demon", "inanimate", "spiritsight",
                                             "flying", "fireres", "coldres", "shockres", "poisonres", "awe",
                                             "fear", "regeneration", "ethereal", "trample", "invulnerable",
                                             "gemprod", "alchemy", "moremagic", "shapechange", "firstshape",
                                             "secondshape", "triplegod", "domsummon", "spreaddom")
                if (row.get(k) or "").strip() not in ("", "0")}
    art = {}
    for frame in SPRITE_FRAMES:
        p = catalog_sprite_path(cat, mid, frame)
        art[frame] = ({"status": "available", "path": f"images/sprites/{p.name}", "origin": "catalog",
                       "url": f"/api/projects/{c.slug}/pretenders/catalog-{mid}/sprite/{frame}"} if p else
                      {"status": "unavailable", "origin": "catalog",
                       "note": "no catalog sprite file for this id" if cat else "no catalog supplied"})
    return {
        "uid": f"god:catalog:{mid}", "source": "catalog", "id": mid, "name": (row.get("name") or "").strip(),
        "monster_uid": None,
        "provenance": {"catalog": "dom6inspector (third-party)", "table": "BaseU.csv", "row_id": mid,
                       "revision": (cat.meta.get("revision") if cat else None),
                       "dataset_version": (cat.meta.get("dataset_version") if cat else None),
                       "note": "Raw catalog values; may differ from the installed game."},
        "art": art,
        "starting_magic": {"paths": {p: {"level": _int(row.get(p)), "path_name": PATH_NAMES[p], "source": "catalog"}
                                     for p in PATHS if (_int(row.get(p)) or 0) > 0}, "random": []},
        "startdom": _f(_int(row.get("startdom")), "catalog", status="resolved" if _int(row.get("startdom")) is not None
                       else "unresolved", note=None if _int(row.get("startdom")) is not None else "empty in catalog"),
        "pathcost": _f(_int(row.get("pathcost")), "catalog", status="resolved" if _int(row.get("pathcost")) is not None
                       else "unresolved", note=None if _int(row.get("pathcost")) is not None else "empty in catalog"),
        "design_points": design_points(_int(row.get("basecost")), "catalog", None, command="basecost"),
        "physical": {k: _f(_int(row.get(k)), "catalog") for k in STAT_FIELDS} | {
            "leader": _f(_int(row.get("leader")), "catalog")},
        "abilities": {"raw": specials, "note": "Selected raw catalog columns; see the inspector for all of them."},
        "equipment": None,
        "homerealm": _f(realms, "catalog"),
        "roles": [], "pretender_only": False,
    }


def _project_god(c: Any, m: dict[str, Any]) -> dict[str, Any]:
    r = m["resolved"]
    g = r["god"]
    assets = c.asset_index
    art = {}
    for frame in SPRITE_FRAMES:
        sp = m["sprites"].get(frame)
        if not sp:
            art[frame] = {"status": "unavailable", "origin": "project", "note": "no sprite command"}
        else:
            ok = sp["path"] in assets
            art[frame] = {"status": "available" if ok else "missing", "origin": "project", "path": sp["path"],
                          "url": sp["url"] if ok else None, "line": sp["line"],
                          **({} if ok else {"note": "referenced file not found in the mod folder"})}
    gc = r["costs"]["gold"]
    return {
        "uid": f"god:project:{m['id']}", "source": "project", "id": m["id"], "name": m["name"],
        "monster_uid": m["uid"],
        "provenance": {"file": m["source"]["file"], "line": m["source"]["line"], "end_line": m["source"]["end_line"],
                       "donor": ({"id": m["donor"]["id"], "name": m["donor"]["name"], "resolved": m["donor"]["resolved"]}
                                 if m["donor"] else None)},
        "art": art,
        "starting_magic": {"paths": {p: {"level": f["value"], "path_name": f["path_name"], "source": f["source"],
                                         "line": f["line"]} for p, f in r["magic"]["paths"].items()},
                           "random": r["magic"]["random"]},
        "startdom": g["startdom"], "pathcost": g["pathcost"],
        "design_points": design_points(gc["authored_value"], gc["source"], gc["line"]),
        "physical": {k: r["stats"][k] for k in STAT_FIELDS} | {"leader": r["leadership"]},
        "abilities": {"specials": r["specials"], "traits": r["creature_traits"],
                      "unmodelled_donor_columns": r["unmodelled_donor_columns"]},
        "equipment": {"weapons": r["equipment"]["weapons"], "armor": r["equipment"]["armor"],
                      "weapons_status": r["equipment"]["weapons_status"], "armor_status": r["equipment"]["armor_status"]},
        "homerealm": g["homerealm"],
        "roles": [m["role"]], "pretender_only": m["role"] == "pretender",
        "unsupported": m["unsupported"], "unresolved": m["unresolved"],
    }


def _ref(c: Any, st_arg: Any) -> tuple[str | None, int | None, str]:
    """(source, id, label) for a god reference: project first, then catalog number; names only within the project."""
    ref = c.ref_monster(st_arg)
    if ref.get("origin") == "project":
        return "project", ref["id"], ref["name"] or str(st_arg)
    if ref.get("origin") == "catalog":
        return "catalog", ref["id"], ref["name"] or str(st_arg)
    return None, ref.get("id"), str(ref.get("name") or st_arg)


def _baseline(c: Any, nid: int) -> dict[str, Any]:
    """Catalog-only starting god data for an existing vanilla nation."""
    realms, cheap, extras, removed = [], {}, [], []
    for r in _table(c.catalog, "attributes_by_nation.csv"):
        if _int(r.get("nation_number")) != nid:
            continue
        a, v = (r.get("attribute") or "").strip(), _int(r.get("raw_value"))
        if a == ATTR_HOMEREALM and v:
            realms.append(v)
        elif a in (ATTR_CHEAPGOD20, ATTR_CHEAPGOD40) and v is not None:
            cheap[v] = 20 if a == ATTR_CHEAPGOD20 else 40
    for r in _table(c.catalog, "pretender_types_by_nation.csv"):
        if _int(r.get("nation_number")) == nid and _int(r.get("monster_number")) not in (None, INSPECTOR_SKIPPED_PRETENDER):
            extras.append(_int(r["monster_number"]))
    for r in _table(c.catalog, "unpretender_types_by_nation.csv"):
        if _int(r.get("nation_number")) == nid and _int(r.get("monster_number")) is not None:
            removed.append(_int(r["monster_number"]))
    return {"realms": realms, "cheap": cheap, "extras": extras, "removed": removed}


def _nation_view(c: Any, n: dict[str, Any], b: Block, gods: dict[str, dict[str, Any]],
                 project_gods: dict[int, dict[str, Any]], members: dict[int, list[int]],
                 units: dict[int, dict[str, str]]) -> dict[str, Any]:
    realms: list[dict[str, Any]] = []
    explicit: list[dict[str, Any]] = []   # addgod (and catalog-baseline nation additions)
    dels: list[dict[str, Any]] = []
    cheap: dict[tuple[str | None, int | None], dict[str, Any]] = {}
    noundead: int | None = None
    commands: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    vanilla_nation = (not b.new and isinstance(n["id"], int) and c.catalog is not None
                      and str(n["id"]) in {(r.get("id") or "").strip() for r in c.catalog.table("nations")})
    basis = "authored"
    if vanilla_nation:
        base = _baseline(c, n["id"])
        basis = "catalog_baseline+authored"
        realms = [{"realm": r, "name": REALM_NAMES.get(r), "line": None, "source": "catalog_baseline"} for r in base["realms"]]
        explicit = [{"source": "catalog", "id": i, "label": (units.get(i) or {}).get("name"), "line": None,
                     "origin": "catalog_baseline"} for i in base["extras"]]
        dels = [{"source": "catalog", "id": i, "label": (units.get(i) or {}).get("name"), "line": None,
                 "origin": "catalog_baseline"} for i in base["removed"]]
        cheap = {("catalog", i): {"discount": d, "line": None, "origin": "catalog_baseline"} for i, d in base["cheap"].items()}
        unresolved.append({"kind": "catalog_baseline", "message": (
            "Starting god data for this existing nation comes from the catalog's per-nation tables "
            "(homerealm, pretender_types_by_nation, unpretender_types_by_nation, cheapgod). These are third-party "
            "extractions, not the game's list.")})
    elif not b.new:
        unresolved.append({"kind": "unknown_baseline", "message": (
            "This #selectnation is not in the catalog, so any gods it already has are unknown.")})

    for st in b.statements:
        cmd = st.command
        if cmd not in GOD_COMMANDS:
            continue
        v = st.args[0].value if st.args else None
        entry = {"line": st.line, "command": f"#{cmd}", "args": [a.raw for a in st.args]}
        if cmd == "clearnation":
            realms, explicit, dels, cheap, noundead = [], [], [], {}, None
            unresolved = [u for u in unresolved if u["kind"] not in ("catalog_baseline", "unknown_baseline")]
            basis = f"authored (god list cleared by #clearnation on line {st.line})"
            entry["effect"] = "clears the god list and the home realm (manual); earlier god commands no longer apply"
        elif cmd == "cleargods":
            explicit = []
            entry["effect"] = "clears the explicit god list; home realm gods stay (manual: remove them with #delgod)"
        elif cmd == "homerealm" and isinstance(v, int):
            realms.append({"realm": v, "name": REALM_NAMES.get(v), "line": st.line, "source": "authored"})
            entry["effect"] = f"adds realm {v} ({REALM_NAMES.get(v, 'unknown')}) gods"
        elif cmd == "addgod" and v is not None:
            src, i, label = _ref(c, v)
            explicit.append({"source": src, "id": i, "label": label, "line": st.line, "origin": "authored"})
            entry.update(target={"source": src, "id": i, "name": label}, effect="adds this god to the nation's list")
            if src is None:
                unresolved.append({"kind": "unresolved_reference", "line": st.line,
                                   "message": f"#addgod {st.args[0].raw}: god not found in the project or catalog"})
        elif cmd == "delgod" and v is not None:
            src, i, label = _ref(c, v)
            dels.append({"source": src, "id": i, "label": label, "line": st.line, "origin": "authored"})
            entry.update(target={"source": src, "id": i, "name": label},
                         effect="removes a god gained through the home realm")
        elif cmd in ("cheapgod20", "cheapgod40") and v is not None:
            src, i, label = _ref(c, v)
            d = 20 if cmd == "cheapgod20" else 40
            cheap[(src, i)] = {"discount": d, "line": st.line, "origin": "authored"}
            entry.update(target={"source": src, "id": i, "name": label},
                         effect=f"this god costs {d} design points less for the nation (final points not computed)")
        elif cmd == "noundeadgods":
            noundead = st.line
            entry["effect"] = "the nation cannot choose undead pretenders"
        else:
            entry["effect"] = "not interpreted (missing argument)"
        commands.append(entry)

    realm_set = sorted({r["realm"] for r in realms})
    cands: dict[str, dict[str, Any]] = {}

    def god_uid(src: str | None, i: int | None) -> str | None:
        if src == "project" and i in project_gods:
            return project_gods[i]["uid"]
        if i is not None and i in project_gods:   # #selectmonster of a catalog id is described by the project
            return project_gods[i]["uid"]
        if src == "catalog" and i in units:
            uid = f"god:catalog:{i}"
            if uid not in gods:
                gods[uid] = _catalog_god(c, i, units[i])
            return uid
        return None

    def add(uid: str | None, via: dict[str, Any]) -> None:
        if uid is None:
            return
        cands.setdefault(uid, {"god": uid, "via": [], "reasons": [], "status": "eligible"})["via"].append(via)

    for realm in realm_set:
        lines = [r["line"] for r in realms if r["realm"] == realm]
        for mid in members.get(realm, []):
            if mid in project_gods and project_gods[mid]["homerealm"]["source"] == "authored":
                continue  # the project redefines this id's realm; handled below
            add(god_uid("catalog", mid), {"kind": "homerealm", "realm": realm, "lines": lines,
                                          "evidence": "catalog realms.csv"})
        for pid, g in project_gods.items():
            hr = g["homerealm"]
            if isinstance(hr["value"], list) and realm in hr["value"]:
                add(g["uid"], {"kind": "homerealm", "realm": realm, "lines": lines,
                               "evidence": f"project #homerealm ({hr['source']})", "provisional": hr["status"] != "resolved"})
    for e in explicit:
        add(god_uid(e["source"], e["id"]), {"kind": "addgod" if e["origin"] == "authored" else "catalog_nation_list",
                                            "line": e["line"], "evidence": e["origin"]})

    for uid, cand in cands.items():
        g = gods[uid]
        realm_gained = any(v["kind"] == "homerealm" for v in cand["via"])
        explicit_gained = any(v["kind"] != "homerealm" for v in cand["via"])
        if any(v.get("provisional") for v in cand["via"]):
            cand["status"] = "provisional"
            cand["reasons"].append("gained through a home realm whose inheritance is unresolved")
        for d in dels:
            if god_uid(d["source"], d["id"]) != uid:
                continue
            where = f"line {d['line']}" if d["line"] else "catalog unpretender list"
            if realm_gained and not explicit_gained:
                cand["status"] = "excluded"
                cand["reasons"].append(f"removed by #delgod ({where})")
            elif d["origin"] == "catalog_baseline":
                cand["status"] = "excluded"
                cand["reasons"].append("removed by the catalog unpretender list (inspector applies it last)")
            else:
                if cand["status"] != "excluded":
                    cand["status"] = "provisional"
                cand["reasons"].append(f"#delgod ({where}) targets a god that is also added explicitly; the manual "
                                       "documents #delgod only for home realm gods")
        sd, pc = g["startdom"], g["pathcost"]
        missing = [k for k, f in (("#startdom", sd), ("#pathcost", pc)) if f["value"] is None]
        if missing and cand["status"] != "excluded":
            if g["source"] == "project" and all(f["status"] == "resolved" for f in (sd, pc)):
                cand["status"] = "excluded"
                cand["reasons"].append(f"missing {' and '.join(missing)}: the manual requires both for a god")
            else:
                cand["status"] = "provisional"
                cand["reasons"].append(f"{' and '.join(missing)} not known (catalog row empty; e.g. a trinity part or "
                                       "game default)")
        if noundead is not None and cand["status"] != "excluded":
            is_undead = (g["abilities"].get("raw", {}).get("undead") if g["source"] == "catalog"
                         else (g["abilities"]["traits"].get("undead") or {}).get("value"))
            trait_unknown = g["source"] == "project" and (g["abilities"]["traits"].get("undead") or {}).get("status") == "unresolved"
            if trait_unknown:
                cand["status"] = "provisional"
                cand["reasons"].append(f"#noundeadgods (line {noundead}): undead status unresolved after #clearspec")
            elif is_undead:
                cand["status"] = "excluded"
                cand["reasons"].append(f"undead; the nation has #noundeadgods (line {noundead})")
        key_hits = [v for (src, i), v in cheap.items() if god_uid(src, i) == uid]
        cand["cheapgod"] = key_hits[-1] if key_hits else None
        if g["source"] == "project" and realm_gained:
            cand["reasons"].append("a project god with a home realm is offered to every nation in that realm, "
                                   "including vanilla and other mods' nations")
        g.setdefault("availability", []).append({"nation": n["uid"], "nation_name": n["name"],
                                                 "status": cand["status"], "via": cand["via"],
                                                 "reasons": cand["reasons"], "cheapgod": cand["cheapgod"]})

    for d in dels:
        if god_uid(d["source"], d["id"]) not in cands and d["origin"] == "authored":
            unresolved.append({"kind": "delgod_no_target", "line": d["line"],
                               "message": f"#delgod {d['label']}: no candidate with this id in the declared realms"})
    if realm_set and not members:
        unresolved.append({"kind": "no_catalog_realms", "message": (
            "No catalog realms table is available, so vanilla gods of the declared realms are not listed.")})
    if 10 not in realm_set:
        unresolved.append({"kind": "default_realm", "message": REALM10_NOTE + " This nation does not declare it, "
                           "so Default-realm gods are not listed."})
    unresolved.append({"kind": "not_modelled", "message": (
        "Not modelled: era or game-setting restrictions on gods, #disbless, AI templates, trinity splitting, and any "
        "other mod loaded with this one that adds gods to the same realm.")})
    ordered = sorted(cands.values(), key=lambda x: (gods[x["god"]]["source"] != "project", x["status"] == "excluded",
                                                    gods[x["god"]]["name"] or "", gods[x["god"]]["id"] or 0))
    counts = {s: sum(1 for x in ordered if x["status"] == s) for s in ("eligible", "provisional", "excluded")}
    counts["listed"] = counts["eligible"] + counts["provisional"]
    counts["custom"] = sum(1 for x in ordered if gods[x["god"]]["source"] == "project")
    counts["vanilla_realm"] = sum(1 for x in ordered if gods[x["god"]]["source"] == "catalog"
                                  and any(v["kind"] == "homerealm" for v in x["via"]))
    counts["explicit"] = sum(1 for x in ordered if any(v["kind"] != "homerealm" for v in x["via"]))
    return {"nation": n["uid"], "nation_id": n["id"], "name": n["name"], "basis": basis,
            "realms": realms, "default_realm_10": {"included": 10 in realm_set, "note": REALM10_NOTE},
            "commands": commands, "noundeadgods": noundead, "candidates": ordered, "counts": counts,
            "unresolved": unresolved}


def build_pretenders(c: Any, nation_blocks: list[Block], nations: list[dict[str, Any]],
                     monsters: list[dict[str, Any]]) -> dict[str, Any]:
    """The pretender section of the browser model. `c` is browse._Ctx; monsters/nations are browse models."""
    try:
        units = _units(c.catalog)
    except KosmoError:
        units = {}
    members = realm_members(c.catalog)
    gods: dict[str, dict[str, Any]] = {}
    project_gods: dict[int, dict[str, Any]] = {}
    for m in monsters:
        g = m["resolved"]["god"]
        addgodded = any(x["via"] == "#addgod" for x in m.get("god_commands", []))
        if m["id"] is not None and (addgodded or g["startdom"]["value"] is not None or g["pathcost"]["value"] is not None
                                    or (isinstance(g["homerealm"]["value"], list) and g["homerealm"]["value"])):
            pg = _project_god(c, m)
            project_gods[m["id"]] = pg
            gods[pg["uid"]] = pg
    views = [_nation_view(c, n, b, gods, project_gods, members, units) for n, b in zip(nations, nation_blocks)]
    for g in gods.values():
        g.setdefault("availability", [])
    lead = views[0]["counts"] if views else {}
    ordered = sorted(gods.values(), key=lambda g: (g["source"] != "project", g["name"] or "", g["id"] or 0))
    return {
        "nations": views, "gods": ordered,
        "counts": {"gods": len(ordered), "custom": sum(1 for g in ordered if g["source"] == "project"),
                   "listed_for_first_nation": lead.get("listed", 0),
                   "catalog_realm_table": bool(members)},
        "assumptions": [
            "Realm gods come from the catalog's realms.csv plus project monsters with a resolved #homerealm. "
            "#addgod requires #startdom and #pathcost (manual).",
            "Nation commands are read in order: #clearnation clears home realm and god list; #cleargods clears the "
            "explicit list but not home realm gods; #delgod removes home realm gods. Interactions the manual does "
            "not describe are marked provisional.",
            REALM10_NOTE,
            "Restrictions: only #noundeadgods is interpreted (documented nation command). Other limits (era, game "
            "settings, blesses) are not modelled.",
            "#clearspec clears dominion strength and path cost (manual: they are special abilities). Its effect on "
            "home realm, creature traits and unmodelled columns is not documented and is shown as assumed or "
            "unresolved.",
            "Existing vanilla nations start from the catalog's per-nation god tables; new nations start empty.",
        ],
        "limitations": [
            "Static reading. It does not prove a god appears in game, and it is not the game's pretender screen.",
            "Final design points are never computed. #gcost/basecost is shown as its encoding only.",
            "Catalog values are third-party extractions and may differ from the installed game.",
        ],
    }
