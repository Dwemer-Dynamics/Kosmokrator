"""Read-only project model for the local web browser.

Builds JSON-ready views of a project's .dm: nations, monsters, sites, other parsed definitions, assets,
validation and source. Three layers are kept distinct for every monster:
  authored  - the commands written in the .dm block, verbatim and in order;
  donor     - the raw dom6inspector catalog row of the #copystats base (never interpreted as effective);
  resolved  - the small subset of fields whose sequential effect Kosmokrator models reliably.
Unmodelled commands remain visible. Raw cost components stay separate from the conservative equipped
stat and cost estimates attached to the view. Building this model never writes to disk.
"""

from __future__ import annotations

import collections
import datetime as _dt
import hashlib
import os
import re
import threading
from pathlib import Path
from typing import Any

from . import MANUAL_VERSION, __version__
from . import commands as cmdreg
from .catalog import Catalog
from .dmparse import Block, Statement, block_id, block_name, parse
from .errors import KosmoError
from .images import image_info
from .paths import SLUG_RE, contained, exact_case_lookup, is_link, mod_relpath_problems
from .pretenders import _table, build_pretenders, catalog_sprite_path
from .project import META_FILE, inspect_mod, open_project, read_dm, resolve_dm_target, sha256_bytes
from .validate import GENERIC_ASSETS, validate_project

SCHEMA = "kosmokrator.browser/1"
PATHS = ["F", "A", "W", "E", "S", "D", "N", "G", "B", "H"]  # #magicskill path numbers 0-9 (Magic Paths, p.33)
PATH_NAMES = dict(zip(PATHS, ["Fire", "Air", "Water", "Earth", "Astral", "Death", "Nature", "Glamour",
                              "Blood", "Holy"]))
PATH_BITS = {128 << i: p for i, p in enumerate(PATHS)}
ERA_NAMES = {1: "Early Age", 2: "Middle Age", 3: "Late Age"}

# Plain numeric stats that are both catalog columns and "#cmd value" setters.
STAT_FIELDS = ["hp", "prot", "mr", "mor", "str", "att", "def", "prec", "enc", "mapmove", "ap", "size"]
# Leadership setters (#xxxleader take no argument) and the leadership value they set.
LEADER_CMDS = {"noleader": 0, "poorleader": 10, "okleader": 50, "goodleader": 100, "expertleader": 150,
               "superiorleader": 200}  # Dominions 6 values (Modding Manual, Leadership)
# Special abilities that are catalog columns and same-named commands; #clearspec removes them.
SPECIALS = ["holy", "fireres", "coldres", "shockres", "poisonres", "acidres", "slashres", "bluntres",
            "pierceres", "forestsurvival", "mountainsurvival", "wastesurvival", "swampsurvival",
            "cavesurvival", "stealthy", "flying", "float", "amphibian", "pooramphibian", "darkvision",
            "regeneration", "awe", "animalawe", "fear", "berserk", "inspirational", "standard", "heal",
            "ethereal", "trample", "invulnerable", "iceprot", "neednoteat", "inquisitor", "formationfighter",
            "undisciplined", "bodyguard", "firepower", "coldpower", "stormpower", "darkpower", "teleport",
            "spy", "assassin", "seduce", "taskmaster", "forgebonus", "fixforgebonus", "mastersmith",
            "researchbonus", "castledef", "siegebonus", "patrolbonus", "pillagebonus", "supplybonus",
            "resources", "fireshield", "poisoncloud", "diseasecloud", "skirmisher", "snowmove"]
# Creature-type flags: shown from the donor, but whether #clearspec removes them is not modelled.
TRAITS = ["undead", "demon", "inanimate", "magicbeing", "stonebeing", "animal", "coldblood", "female",
          "mind", "aquatic", "immobile", "slave"]
# Commands that only affect presentation or identity, applied without touching stats.
PRESENTATION = {"name", "descr", "spr1", "spr2", "fixedname", "nametype"}
# Pretender columns/commands. The manual (Monster Modding, Special Abilities) says dominion strength and path
# costs are special abilities too, so #clearspec clears them; whether it clears the home realm is not stated.
GOD_FIELDS = ["startdom", "pathcost"]
REALM_COLUMNS = ["realm1", "realm2", "realm3"]
# Donor columns that change economy, shape or pretender behaviour but are not modelled. They are surfaced so a
# copied unit can be audited; the effect of #clearspec on each is an assumption, not a resolved value.
NOTABLE_UNMODELLED = ["gemprod", "alchemy", "spiritsight", "moremagic", "moreorder", "moreprod", "moreheat",
                      "moregrowth", "moreluck", "magicboostF", "magicboostA", "magicboostW", "magicboostE",
                      "magicboostS", "magicboostD", "magicboostN", "magicboostALL", "domsummon", "domsummon2",
                      "domsummon20", "raredomsummon", "spreaddom", "shapechange", "firstshape", "secondshape",
                      "secondtmpshape", "landshape", "watershape", "forestshape", "plainshape", "xpshape",
                      "prophetshape", "homeshape", "indepspells", "triplegod", "godsite", "minprison", "maxprison"]
COST_CMDS = {"gcost": "gold", "rcost": "resources", "rpcost": "recruitment_points"}
# Catalog column holding the same authored component as each cost command.
COST_COLUMNS = {"gcost": "basecost", "rcost": "rcost", "rpcost": "rpcost"}
# dom6inspector (MUnit.monsterGoldCost) treats gold below this as fixed, otherwise as autocalc-encoded
# (10000 + base; the base may be negative, e.g. 9960). The manual documents only the 10000 + base form.
GCOST_FIXED_BELOW = 5000

# Nation commands that recruit or place monsters, with the role they imply.
NATION_COMMANDER_CMDS = {"addreccom", "startcom", "startscout", "defcom1", "defcom2", "wallcom", "guardcom",
                         "addforeigncom", "forestcom", "mountaincom", "swampcom", "wastecom", "cavecom",
                         "coastcom1", "coastcom2", "landcom", "uwcom"}
NATION_HERO_CMDS = {f"hero{i}" for i in range(1, 11)} | {f"multihero{i}" for i in range(1, 8)}
NATION_COMMANDER_CMDS |= NATION_HERO_CMDS
NATION_TROOP_CMDS = {"addrecunit", "startunittype1", "startunittype2", "defunit1", "defunit1b", "defunit1c",
                     "defunit1d", "defunit2", "defunit2b", "wallunit", "guardunit", "addforeignunit",
                     "forestrec", "mountainrec", "swamprec", "wasterec", "caverec", "coastrec", "landrec",
                     "uwrec", "coastunit1", "coastunit2", "coastunit3"}
# Nation god commands that name a monster; they never make it recruitable.
NATION_GOD_CMDS = {"addgod", "delgod", "cheapgod20", "cheapgod40"}
SITE_COMMANDER_CMDS = {"homecom", "com"}
SITE_TROOP_CMDS = {"homemon", "mon"}
RECRUIT_WHERE = {
    "addrecunit": "Recruitable in the nation's forts", "addreccom": "Recruitable in the nation's forts",
    "homemon": "Recruitable only where this site is (start sites are at the capital)",
    "homecom": "Recruitable only where this site is (start sites are at the capital)",
    "mon": "Recruitable where this site is", "com": "Recruitable where this site is",
}

_INDEX_LOCK = threading.Lock()
_CATALOG_INDEX: dict[tuple[str, str], dict[str, dict[str, str]]] = {}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cat_rows(catalog: Catalog | None, category: str) -> dict[str, dict[str, str]]:
    """id -> raw row for one catalog table, indexed once per catalog (the core only offers linear lookups)."""
    if catalog is None:
        return {}
    key = (str(catalog.gamedata), category)
    with _INDEX_LOCK:
        if key not in _CATALOG_INDEX:
            if len(_CATALOG_INDEX) >= 48:
                _CATALOG_INDEX.clear()
            try:
                rows = catalog.table(category)
            except KosmoError:
                rows = []
            _CATALOG_INDEX[key] = {(r.get("id") or "").strip(): r for r in rows}
        return _CATALOG_INDEX[key]


def _raw_row(row: dict[str, str] | None) -> dict[str, str] | None:
    """Non-empty raw catalog columns, as strings exactly as the catalog stores them."""
    if row is None:
        return None
    return {k: v for k, v in row.items() if isinstance(k, str) and isinstance(v, str) and v.strip() != ""}


def _int(v: Any) -> int | None:
    s = str(v).strip() if v is not None else ""
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def _mask_paths(mask: int) -> list[str]:
    return [p for bit, p in PATH_BITS.items() if mask & bit]


def _cmd_status(ctx: str, cmd: str) -> str:
    if cmdreg.get(ctx, cmd):
        return "curated"
    if cmd in cmdreg.DOCUMENTED.get(ctx, ()):
        return "documented_uncurated"
    return "unverified"


def _arg_value(st: Statement, i: int = 0) -> Any:
    return st.args[i].value if len(st.args) > i else None


def _source(text_lines: list[str], dm_rel: str, b: Block) -> dict[str, Any]:
    start = b.opener.line
    end = b.end.line if b.end else (b.statements[-1].end_line if b.statements else start)
    return {"file": dm_rel, "line": start, "end_line": end, "text": "\n".join(text_lines[start - 1:end])}


def _diag_in(validation: dict[str, Any] | None, start: int, end: int) -> list[dict[str, Any]]:
    if not validation:
        return []
    out = []
    for sev in ("errors", "warnings", "unverified"):
        for i in validation.get(sev, []):
            if i.get("line") and start <= i["line"] <= end:
                out.append(i)
    return out


class _Ctx:
    """Shared lookups while building one project model."""

    def __init__(self, slug: str, dm_rel: str, lines: list[str], catalog: Catalog | None,
                 validation: dict[str, Any] | None) -> None:
        self.slug = slug
        self.dm_rel = dm_rel
        self.lines = lines
        self.catalog = catalog
        self.validation = validation
        self.monsters_by_id: dict[int, dict[str, Any]] = {}
        self.monsters_by_name: dict[str, list[int]] = {}
        self.sites_by_id: dict[int, dict[str, Any]] = {}
        self.sites_by_name: dict[str, list[int]] = {}
        self.asset_index: set[str] = set()  # mod-relative paths of files that exist

    def asset_url(self, ref: str) -> str:
        return f"/api/projects/{self.slug}/assets/{ref}"

    def ref_monster(self, arg: Any) -> dict[str, Any]:
        """Resolve a monster reference (number or name) to the project or catalog, or mark it unresolved."""
        if isinstance(arg, int):
            if arg in self.monsters_by_id:
                m = self.monsters_by_id[arg]
                return {"ref": arg, "origin": "project", "id": arg, "uid": f"monster:{arg}", "name": m["name"]}
            row = _cat_rows(self.catalog, "units").get(str(arg))
            if row:
                return {"ref": arg, "origin": "catalog", "id": arg, "uid": None, "name": row.get("name")}
            return {"ref": arg, "origin": None, "id": arg, "uid": None, "name": None,
                    "unresolved": "not in project" + ("" if self.catalog else "; no catalog supplied")
                                  + (" or catalog" if self.catalog else "")}
        name = str(arg or "")
        ids = self.monsters_by_name.get(name.lower(), [])
        if len(ids) == 1:
            return {"ref": name, "origin": "project", "id": ids[0], "uid": f"monster:{ids[0]}", "name": name}
        return {"ref": name, "origin": None, "id": None, "uid": None, "name": name,
                "unresolved": "ambiguous name" if ids else "name references are only resolved within the project"}

    def ref_site(self, arg: Any) -> dict[str, Any]:
        if isinstance(arg, int):
            if arg in self.sites_by_id:
                return {"ref": arg, "origin": "project", "id": arg, "uid": f"site:{arg}",
                        "name": self.sites_by_id[arg]["name"]}
            row = _cat_rows(self.catalog, "sites").get(str(arg))
            return {"ref": arg, "origin": "catalog" if row else None, "id": arg, "uid": None,
                    "name": row.get("name") if row else None, **({} if row else {"unresolved": "unknown site"})}
        name = str(arg or "")
        ids = self.sites_by_name.get(name.lower(), [])
        if len(ids) == 1:
            return {"ref": name, "origin": "project", "id": ids[0], "uid": f"site:{ids[0]}", "name": name}
        for rid, row in _cat_rows(self.catalog, "sites").items():
            if (row.get("name") or "").strip().lower() == name.lower():
                return {"ref": name, "origin": "catalog", "id": _int(rid), "uid": None, "name": row.get("name")}
        return {"ref": name, "origin": None, "id": None, "uid": None, "name": name,
                "unresolved": "ambiguous name" if ids else "site name not found"}

    def ref_equipment(self, category: str, arg: Any) -> dict[str, Any]:
        rows = _cat_rows(self.catalog, category)
        if isinstance(arg, int):
            row = rows.get(str(arg))
            return {"ref": arg, "id": arg, "name": row.get("name") if row else None,
                    **({} if row else {"unresolved": "not in catalog" if self.catalog else "no catalog supplied"})}
        name = str(arg or "")
        hits = [rid for rid, r in rows.items() if (r.get("name") or "").strip().lower() == name.lower()]
        if len(hits) == 1:
            return {"ref": name, "id": _int(hits[0]), "name": name}
        return {"ref": name, "id": None, "name": name,
                "unresolved": f"name matches {len(hits)} catalog entries" if hits else
                ("name not found in catalog" if self.catalog else "no catalog supplied")}


def _authored(ctx: str, b: Block, effects: dict[int, str]) -> list[dict[str, Any]]:
    out = []
    for st in [b.opener, *b.statements]:
        out.append({"line": st.line, "command": f"#{st.command}", "args": [a.raw for a in st.args],
                    "raw": st.raw, "status": _cmd_status(ctx, st.command),
                    "effect": effects.get(id(st), "opener" if st is b.opener else None)})
    return out


def _field(value: Any, source: str, line: int | None = None, status: str = "resolved", note: str | None = None
           ) -> dict[str, Any]:
    out: dict[str, Any] = {"value": value, "source": source, "line": line, "status": status}
    if note:
        out["note"] = note
    return out


def _cost_field(cmd: str, raw: int | None, source: str, line: int | None) -> dict[str, Any]:
    """An authored or inherited cost component. The effective game cost is never computed: value is null."""
    out: dict[str, Any] = {"value": None, "effective": None, "command": f"#{cmd}", "column": COST_COLUMNS[cmd],
                           "authored_value": raw, "source": source, "line": line, "status": "unresolved"}
    if raw is None:
        out["interpretation"] = "unset"
        out["note"] = "No authored or inherited value; the game default applies and is not modelled."
    elif cmd == "gcost" and raw < GCOST_FIXED_BELOW:
        out["interpretation"] = "fixed"
        out["note"] = (f"{raw} is a fixed gold cost by the inspector's convention (below {GCOST_FIXED_BELOW}). "
                       "Mount and other additions are not modelled, so no final cost is shown.")
    elif cmd == "gcost":
        out["interpretation"] = "autocalc_encoded"
        out["base"] = raw - 10000
        out["note"] = (f"{raw} encodes autocalc with base {raw - 10000}. The game adds leadership, magic, "
                       "spy/assassin and sacred costs, and the result differs for units and commanders; "
                       "not computed.")
    elif cmd == "rcost":
        out["interpretation"] = "component"
        out["note"] = (f"{raw} is the base resource component only. The game adds the resource cost of weapons "
                       "and armour (scaled by size); the final resource cost is not computed.")
    else:
        out["interpretation"] = "conditional"
        out["note"] = ("Recruitment-point value as written. The manual describes 'base price'*1000 values as "
                       "autocalculated; whether and how that applies here is not interpreted.")
    return out


def _resolve_monster(c: _Ctx, b: Block) -> dict[str, Any]:
    """Apply a monster block's commands in order over the donor row, for the modelled fields only."""
    effects: dict[int, str] = {}
    unsupported: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    stats: dict[str, dict[str, Any]] = {f: _field(None, "unset", status="unresolved",
                                                  note="no donor or authored value") for f in STAT_FIELDS}
    leader = _field(None, "unset", status="unresolved", note="no donor or authored value")
    specials: dict[str, dict[str, Any]] = {}
    traits: dict[str, dict[str, Any]] = {}
    paths: dict[str, dict[str, Any]] = {}
    randoms: list[dict[str, Any]] = []
    weapons: list[dict[str, Any]] = []
    armor: list[dict[str, Any]] = []
    # Whether each equipment list is a reliable picture of the unit's equipment.
    eq_status: dict[str, dict[str, Any]] = {"weapons": {"status": "resolved"}, "armor": {"status": "resolved"}}
    armor_cleared = False
    costs: dict[str, dict[str, Any]] = {COST_CMDS[k]: _cost_field(k, None, "unset", None) for k in COST_CMDS}
    god: dict[str, dict[str, Any]] = {f: _field(None, "unset", status="resolved", note="not set")
                                      for f in GOD_FIELDS}
    realms = _field([], "unset", status="resolved", note="no home realm")
    notable: dict[str, dict[str, Any]] = {}
    applied: list[int] = []  # statements whose effect a later #copystats overwrites
    donor: dict[str, Any] | None = None
    sprites: dict[str, Any] = {"idle": None, "attack": None}
    name: str | None = None
    descr: str | None = None
    new = b.new

    def unknown_equipment(reason: str) -> None:
        nonlocal weapons, armor
        weapons, armor = [], []
        for k in eq_status:
            eq_status[k] = {"status": "unresolved", "note": f"inherited {k} unknown: {reason}"}

    def load_donor(row: dict[str, str], line: int) -> None:
        nonlocal stats, leader, specials, traits, paths, randoms, weapons, armor, armor_cleared, realms, notable
        for f in GOD_FIELDS:
            v = _int(row.get(f))
            god[f] = _field(v, "donor", line) if v is not None else _field(None, "donor", line, note="not set")
        rv = [r for r in (_int(row.get(k)) for k in REALM_COLUMNS) if r]
        realms = _field(rv, "donor", line, "resolved" if not rv else "unresolved",
                        None if not rv else "copied from the donor row; whether #copystats copies a home realm "
                                            "is not documented")
        notable = {k: {"value": row[k].strip(), "source": "donor", "line": line,
                       "status": "inherited (not modelled)"}
                   for k in NOTABLE_UNMODELLED if (row.get(k) or "").strip() not in ("", "0")}
        for k in COST_CMDS:
            costs[COST_CMDS[k]] = _cost_field(k, _int(row.get(COST_COLUMNS[k])), "donor", line)
        for f in STAT_FIELDS:
            v = _int(row.get(f))
            stats[f] = _field(v, "donor", line) if v is not None else _field(None, "donor", line, "unresolved",
                                                                              "donor value empty")
        lv = _int(row.get("leader"))
        leader = _field(lv, "donor", line) if lv is not None else _field(None, "donor", line, "unresolved")
        specials = {k: _field(_int(row[k]) if _int(row.get(k)) is not None else row[k], "donor", line)
                    for k in SPECIALS if (row.get(k) or "").strip() not in ("", "0")}
        traits = {k: _field(_int(row[k]) if _int(row.get(k)) is not None else row[k], "donor", line)
                  for k in TRAITS if (row.get(k) or "").strip() not in ("", "0")}
        paths = {p: _field(_int(row[p]), "donor", line) for p in PATHS if (_int(row.get(p)) or 0) > 0}
        randoms = []
        for n in range(1, 7):
            mask, chance = _int(row.get(f"mask{n}")), _int(row.get(f"rand{n}"))
            if mask and chance:
                randoms.append({"source": "donor", "line": line, "mask": mask, "paths": _mask_paths(mask),
                                "chance": chance, "levels": _int(row.get(f"link{n}")),
                                "count": _int(row.get(f"nbr{n}"))})
        weapons = [{"source": "donor", "line": line, **c.ref_equipment("weapons", _int(row[f"wpn{n}"]))}
                   for n in range(1, 8) if _int(row.get(f"wpn{n}"))]
        armor = [{"source": "donor", "line": line, **c.ref_equipment("armors", _int(row[f"armor{n}"]))}
                 for n in range(1, 5) if _int(row.get(f"armor{n}"))]
        eq_status["weapons"] = {"status": "resolved"}
        eq_status["armor"] = {"status": "resolved"}
        armor_cleared = False

    if not new:
        # #selectmonster starts from the existing catalog monster.
        row = _cat_rows(c.catalog, "units").get(str(block_id(b)))
        if row is None and isinstance(block_id(b), str):
            matches = [r for r in _cat_rows(c.catalog, 'units').values() if r.get('name', '').lower() == block_id(b).lower()]
            row = matches[0] if len(matches) == 1 else None
        if row:
            donor = {"command": "#selectmonster", "ref": block_id(b), "line": b.opener.line, "id": block_id(b),
                     "name": row.get("name"), "resolved": True, "catalog_row": _raw_row(row)}
            load_donor(row, b.opener.line)
        else:
            why = "no catalog supplied" if c.catalog is None else "selected monster not in catalog"
            unresolved.append({"line": b.opener.line, "reason": why + "; base stats unknown"})
            unknown_equipment(why)

    from .traits import TRAITS as ALL_TRAITS, statement_args
    authored_traits: list[dict[str, Any]] = []
    for st in b.statements:
        cmd, v = st.command, _arg_value(st)
        ln = st.line
        if cmd in ("copystats", "clear", "clearspec", "clearmagic"):
            for a in authored_traits:
                if a["status"] == "authored" and cmd in ALL_TRAITS[a["command"][1:]].bounds:
                    a["status"] = f"ended by #{cmd} on line {ln}"
        if cmd in ALL_TRAITS:
            t = ALL_TRAITS[cmd]
            args = statement_args(t, st)
            authored_traits.append({"command": f"#{cmd}", "group": t.section, "page": t.page, "line": ln,
                                    "raw": st.raw.strip(), "args": args, "summary": t.summary,
                                    "status": "authored" if args is not None else "malformed (not the documented "
                                                                                    "arguments)",
                                    "repeatable": t.repeat is not None})
        if cmd == "copystats":
            # Manual: #copystats overwrites all previous commands for the monster (costs and presentation
            # included); earlier lines stay in the authored list but are marked overwritten.
            for sid in applied:
                effects[sid] = f"overwritten by #copystats on line {ln}"
            applied.clear()
            for u in unsupported:
                u["reason"] = f"overwritten by #copystats on line {ln}"
            name, descr = None, None
            sprites = {"idle": None, "attack": None}
            costs.update({COST_CMDS[k]: _cost_field(k, None, "unset", None) for k in COST_CMDS})
            row =_cat_rows(c.catalog, "units").get(str(v)) if isinstance(v, int) else None
            if row is not None:
                donor = {"command": "#copystats", "ref": v, "line": ln, "id": v, "name": row.get("name"),
                         "resolved": True, "catalog_row": _raw_row(row)}
                load_donor(row, ln)
                effects[id(st)] = "applied: replaces all modelled fields with the donor's"
            else:
                local = c.monsters_by_id.get(v) if isinstance(v, int) else None
                donor = {"command": "#copystats", "ref": v, "line": ln, "id": v if isinstance(v, int) else None,
                         "name": local["name"] if local else None, "resolved": False, "catalog_row": None,
                         "reason": "donor is a project monster (chained inheritance not modelled)" if local else
                         ("no catalog supplied" if c.catalog is None else "donor not found in catalog")}
                unresolved.append({"line": ln, "reason": f"#copystats {st.args[0].raw if st.args else ''}: "
                                                         + donor["reason"]})
                for f in stats:
                    stats[f] = _field(None, "unresolved_donor", ln, "unresolved", donor["reason"])
                leader = _field(None, "unresolved_donor", ln, "unresolved", donor["reason"])
                specials, traits, paths, randoms, notable = {}, {}, {}, [], {}
                for f in GOD_FIELDS:
                    god[f] = _field(None, "unresolved_donor", ln, "unresolved", donor["reason"])
                realms = _field(None, "unresolved_donor", ln, "unresolved", donor["reason"])
                unknown_equipment(donor["reason"])
                for k in COST_CMDS:
                    costs[COST_CMDS[k]] = {**_cost_field(k, None, "unresolved_donor", ln), "interpretation": "unknown",
                                           "note": f"Donor unresolved ({donor['reason']}); cost component unknown."}
                effects[id(st)] = "unresolved donor"
        elif cmd in STAT_FIELDS and isinstance(v, int):
            stats[cmd] = _field(v, "authored", ln)
            effects[id(st)] = "applied"
        elif cmd in LEADER_CMDS:
            leader = _field(LEADER_CMDS[cmd], "authored", ln)
            effects[id(st)] = "applied"
        elif cmd == "clearspec":
            specials = {}
            for k in traits:
                traits[k] = {**traits[k], "status": "unresolved",
                             "note": "#clearspec effect on creature-type flags is not modelled"}
            for f in GOD_FIELDS:
                if god[f]["value"] is not None or god[f]["status"] == "unresolved":
                    god[f] = _field(None, "cleared", ln, note="#clearspec clears dominion strength and path cost "
                                                              "(manual: they are special abilities)")
            if realms["value"] or realms["status"] == "unresolved":
                realms = {**realms, "status": "unresolved",
                          "note": f"#clearspec on line {ln}: whether it clears a home realm is not documented"}
            for k in notable:
                notable[k] = {**notable[k], "status": f"assumed cleared by #clearspec on line {ln} (not modelled; "
                                                      "verify in game)"}
            effects[id(st)] = "applied: cleared modelled special abilities, dominion and path cost"
        elif cmd in GOD_FIELDS and isinstance(v, int):
            god[cmd] = _field(v, "authored", ln)
            effects[id(st)] = "applied: makes the monster selectable as a god"
        elif cmd == "homerealm" and isinstance(v, int):
            if v == 0:
                realms = _field([], "authored", ln, note="#homerealm 0 clears the home realm")
            elif realms["status"] == "unresolved":
                realms = _field(sorted(set(realms["value"] or []) | {v}), "authored", ln, "unresolved",
                                "adds to an inherited home realm that is itself unresolved")
            else:
                realms = _field(sorted(set(realms["value"] or []) | {v}), "authored", ln)
            effects[id(st)] = "applied"
        elif cmd in TRAITS and not st.args:
            traits[cmd] = _field(1, "authored", ln)
            effects[id(st)] = "applied"
        elif cmd in SPECIALS:
            specials[cmd] = _field(v if v is not None else 1, "authored", ln)
            effects[id(st)] = "applied"
        elif cmd == "clearmagic":
            paths, randoms = {}, []
            effects[id(st)] = "applied: cleared paths and random picks"
        elif cmd == "magicskill" and isinstance(v, int) and 0 <= v <= 9 and isinstance(_arg_value(st, 1), int):
            lvl = _arg_value(st, 1)
            if lvl > 0:
                paths[PATHS[v]] = _field(lvl, "authored", ln)
            else:
                paths.pop(PATHS[v], None)
            effects[id(st)] = "applied"
        elif cmd == "custommagic" and isinstance(v, int) and isinstance(_arg_value(st, 1), int):
            randoms.append({"source": "authored", "line": ln, "mask": v, "paths": _mask_paths(v),
                            "chance": _arg_value(st, 1), "levels": 1, "count": None})
            effects[id(st)] = "applied"
        elif cmd == "clearweapons":
            weapons = []
            eq_status["weapons"] = {"status": "resolved"}
            effects[id(st)] = "applied"
        elif cmd == "cleararmor":
            armor = []
            armor_cleared = True
            eq_status["armor"] = {"status": "resolved"}
            effects[id(st)] = "applied"
        elif cmd == "weapon" and v is not None:
            # Manual: without #clearweapons the old and new weapons are both kept.
            weapons.append({"source": "authored", "line": ln, **c.ref_equipment("weapons", v)})
            effects[id(st)] = ("applied: added to the weapon list" if eq_status["weapons"]["status"] == "resolved"
                               else "listed: inherited weapons unknown")
        elif cmd == "armor" and v is not None:
            inherited = any(a["source"] != "authored" for a in armor)
            armor.append({"source": "authored", "line": ln, **c.ref_equipment("armors", v)})
            if eq_status["armor"]["status"] == "resolved" and inherited and not armor_cleared:
                # Manual: #cleararmor must come first or armor assignment does not work correctly.
                eq_status["armor"] = {"status": "unresolved", "note": (
                    f"#armor on line {ln} adds to inherited armour without #cleararmor; the manual says armour "
                    "assignment then does not work correctly, so the effective armour is unknown.")}
            elif eq_status["armor"]["status"] == "resolved" and len(armor) > 3:
                eq_status["armor"] = {"status": "unresolved", "note": (
                    f"more than three armours by line {ln}; the manual allows one helmet, one body armour and one "
                    "shield, so the effective armour is unknown.")}
            effects[id(st)] = ("applied" if eq_status["armor"]["status"] == "resolved"
                               else "listed: effective armour unresolved")
        elif cmd in COST_CMDS and isinstance(v, int):
            costs[COST_CMDS[cmd]] = _cost_field(cmd, v, "authored", ln)
            effects[id(st)] = "recorded: authored cost component; effective cost not computed"
        elif cmd in PRESENTATION:
            if cmd == "name" and st.args:
                name = str(v)
            elif cmd == "descr" and st.args:
                descr = str(v)
            elif cmd in ("spr1", "spr2") and st.args and st.args[0].kind == "str":
                sprites["idle" if cmd == "spr1" else "attack"] = {"path": v, "url": c.asset_url(v), "line": ln}
            effects[id(st)] = "presentation"
        else:
            unsupported.append({"line": ln, "command": f"#{cmd}", "raw": st.raw,
                                "reason": "modifying effect not modelled; resolved fields may differ in game"})
            effects[id(st)] = "unsupported: not modelled"
        applied.append(id(st))

    if donor is None and new:
        unresolved.append({"line": b.opener.line, "reason": "no #copystats donor: unset fields use game defaults, "
                                                            "which are not modelled"})
    return {
        "name": name, "description": descr, "sprites": sprites, "donor": donor,
        "effects": effects, "unsupported": unsupported, "unresolved": unresolved,
        "resolved": {
            "stats": stats, "leadership": leader, "specials": specials, "creature_traits": traits,
            "magic": {"paths": {p: {**f, "path_name": PATH_NAMES[p]} for p, f in paths.items()},
                      "random": randoms,
                      "note": "Random picks are listed as authored/inherited; their probabilities are not "
                              "expanded here."},
            "equipment": {"weapons": weapons, "armor": armor, "weapons_status": eq_status["weapons"],
                          "armor_status": eq_status["armor"],
                          "note": "Items as listed by the donor and authored commands. Supported equipment "
                                  "modifiers are estimated separately in the equipped sheet."},
            "costs": costs,
            "god": {**god, "homerealm": realms,
                    "note": "#startdom and #pathcost make a monster selectable as a god; #addgod requires both. "
                            "Effective availability is shown in the Pretenders view."},
            "unmodelled_donor_columns": notable,
            "authored_traits": authored_traits,
            "authored_traits_note": ("Every documented trait line written in this block, in order. 'authored' lines "
                                     "are still in effect after the last reset; their combat/economy effect is not "
                                     "computed. Abilities inherited from the donor are only shown for modelled "
                                     "columns above; other inherited abilities are not modelled and may still apply."),
        },
    }


def _monster_model(c: _Ctx, b: Block) -> dict[str, Any]:
    r = _resolve_monster(c, b)
    ident = block_id(b)
    src = _source(c.lines, c.dm_rel, b)
    eff = r.pop("effects")
    # A #selectmonster block without #name keeps the catalog monster's name.
    name = r["name"] if b.new else (r["name"] or (r["donor"] or {}).get("name"))
    return {
        "uid": f"monster:{ident}" if isinstance(ident, int) else f"monster:line{b.opener.line}",
        "kind": "monster", "id": ident if isinstance(ident, int) else None,
        "selector": ident if isinstance(ident, str) else None, "new": b.new,
        "name": name, "role": "unassigned", "recruitment": [], "nations": [],
        **{k: v for k, v in r.items() if k != "name"},
        "authored": _authored("monster", b, eff),
        "source": src,
        "diagnostics": _diag_in(c.validation, src["line"], src["end_line"]),
    }


def _site_model(c: _Ctx, b: Block) -> dict[str, Any]:
    ident = block_id(b)
    src = _source(c.lines, c.dm_rel, b)
    fields: dict[str, Any] = {"name": None, "path": None, "level": None, "rarity": None}
    gems: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    effects: dict[int, str] = {}
    unsupported = []
    for st in b.statements:
        cmd, v = st.command, _arg_value(st)
        if cmd in ("name", "path", "level", "rarity"):
            fields[cmd] = {"value": v, "line": st.line}
            effects[id(st)] = "applied"
        elif cmd == "gems" and isinstance(v, int) and 0 <= v <= 9:
            gems.append({"path": PATHS[v], "path_name": PATH_NAMES[PATHS[v]], "amount": _arg_value(st, 1),
                         "line": st.line})
            effects[id(st)] = "applied"
        elif cmd in SITE_COMMANDER_CMDS | SITE_TROOP_CMDS and v is not None:
            units.append({"command": f"#{cmd}", "line": st.line, "monster": c.ref_monster(v),
                          "role": "commander" if cmd in SITE_COMMANDER_CMDS else "troop"})
            effects[id(st)] = "applied"
        elif cmd == "clear":
            fields = {k: None for k in fields}
            gems, units = [], []
            effects[id(st)] = "applied: cleared modelled fields"
        else:
            unsupported.append({"line": st.line, "command": f"#{cmd}", "raw": st.raw,
                                "reason": "site effect not modelled"})
            effects[id(st)] = "unsupported: not modelled"
    path = fields["path"]["value"] if fields["path"] else None
    base = None
    if not b.new and isinstance(ident, int):
        row = _cat_rows(c.catalog, "sites").get(str(ident))
        base = {"id": ident, "name": row.get("name") if row else None, "catalog_row": _raw_row(row),
                "resolved": row is not None}
    return {
        "uid": f"site:{ident}" if isinstance(ident, int) else f"site:line{b.opener.line}",
        "kind": "site", "id": ident if isinstance(ident, int) else None,
        "selector": ident if isinstance(ident, str) else None, "new": b.new,
        "name": fields["name"]["value"] if fields["name"] else (base or {}).get("name"),
        "path": PATHS[path] if isinstance(path, int) and 0 <= path <= 9 else None,
        "path_name": PATH_NAMES[PATHS[path]] if isinstance(path, int) and 0 <= path <= 9 else None,
        "level": fields["level"]["value"] if fields["level"] else None,
        "rarity": fields["rarity"]["value"] if fields["rarity"] else None,
        "gems": gems, "units": units, "base": base, "unsupported": unsupported, "start_site_of": [],
        "authored": _authored("site", b, effects), "source": src,
        "diagnostics": _diag_in(c.validation, src["line"], src["end_line"]),
    }


def _nation_model(c: _Ctx, b: Block) -> dict[str, Any]:
    ident = block_id(b)
    src = _source(c.lines, c.dm_rel, b)
    info: dict[str, Any] = {k: None for k in ("name", "epithet", "era", "descr", "summary", "brief")}
    flag = None
    colors: dict[str, Any] = {}
    clears: list[dict[str, Any]] = []
    start_sites: list[dict[str, Any]] = []
    recruit: dict[str, list[dict[str, Any]]] = {"troops": [], "commanders": []}
    start_army: dict[str, Any] = {"commander": None, "scout": None, "units": []}
    defence: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    effects: dict[int, str] = {}
    pending_units: dict[str, dict[str, Any]] = {}
    for st in b.statements:
        cmd, v, ln = st.command, _arg_value(st), st.line
        effects[id(st)] = "applied"
        if cmd in info:
            info[cmd] = {"value": v, "line": ln}
        elif cmd in ("clearnation", "clearrec", "clearsites"):
            clears.append({"command": f"#{cmd}", "line": ln})
            if cmd == "clearrec":
                recruit = {"troops": [], "commanders": []}
            elif cmd in ("clearsites", "clearnation"):
                start_sites = []
            effects[id(st)] = "applied: clears inherited " + {"clearnation": "nation settings",
                                                              "clearrec": "recruitment",
                                                              "clearsites": "start sites"}[cmd]
        elif cmd == "flag" and st.args:
            flag = {"path": v, "url": c.asset_url(str(v)), "line": ln}
        elif cmd in ("color", "secondarycolor"):
            colors[cmd] = {"rgb": [a.value for a in st.args], "line": ln}
        elif cmd == "startsite" and v is not None:
            start_sites.append({"line": ln, "site": c.ref_site(v)})
        elif cmd == "addrecunit" and v is not None:
            recruit["troops"].append({"line": ln, "command": "#addrecunit", "monster": c.ref_monster(v)})
        elif cmd == "addreccom" and v is not None:
            recruit["commanders"].append({"line": ln, "command": "#addreccom", "monster": c.ref_monster(v)})
        elif cmd == "startcom" and v is not None:
            # Per the manual #startcom clears the start army set before it (p.45).
            start_army = {"commander": {"line": ln, "monster": c.ref_monster(v)}, "scout": None, "units": []}
            pending_units = {}
        elif cmd == "startscout" and v is not None:
            start_army["scout"] = {"line": ln, "monster": c.ref_monster(v)}
        elif re.fullmatch(r"startunit(type|nbrs)[12]", cmd) and v is not None:
            slot = cmd[-1]
            e = pending_units.setdefault(slot, {"slot": int(slot), "monster": None, "count": None, "lines": []})
            if "type" in cmd:
                e["monster"] = c.ref_monster(v)
            else:
                e["count"] = v
            e["lines"].append(ln)
        elif re.fullmatch(r"(defcom[12]|defunit\w+|defmult\w+|wallcom|wallunit|wallmult|guardcom|guardunit|"
                          r"guardmult)", cmd):
            entry: dict[str, Any] = {"line": ln, "command": f"#{cmd}"}
            if "mult" in cmd:
                entry["count"] = v
            elif v is not None:
                entry["monster"] = c.ref_monster(v)
            defence.append(entry)
        else:
            other.append({"line": ln, "command": f"#{cmd}", "args": [a.raw for a in st.args],
                          "status": _cmd_status("nation", cmd)})
            effects[id(st)] = "listed: not interpreted by the browser"
    start_army["units"] = [pending_units[k] for k in sorted(pending_units)]
    era = info["era"]["value"] if info["era"] else None
    if era is None and isinstance(ident, int):
        era = _int(_cat_rows(c.catalog, "nations").get(str(ident), {}).get("era"))
    return {
        "uid": f"nation:{ident}" if isinstance(ident, int) else f"nation:line{b.opener.line}",
        "kind": "nation", "id": ident if isinstance(ident, int) else None, "new": b.new,
        "name": info["name"]["value"] if info["name"] else None,
        "epithet": info["epithet"]["value"] if info["epithet"] else None,
        "era": era, "era_name": ERA_NAMES.get(era) if isinstance(era, int) else None,
        "description": info["descr"]["value"] if info["descr"] else None,
        "summary": info["summary"]["value"] if info["summary"] else None,
        "brief": info["brief"]["value"] if info["brief"] else None,
        "flag": flag, "colors": colors, "clears": clears, "start_sites": start_sites, "gem_sites": [],
        "recruitment": recruit, "start_army": start_army, "defence": defence, "other_commands": other,
        "authored": _authored("nation", b, effects), "source": src,
        "diagnostics": _diag_in(c.validation, src["line"], src["end_line"]),
    }


def _definition_model(c: _Ctx, b: Block) -> dict[str, Any]:
    ident = block_id(b)
    src = _source(c.lines, c.dm_rel, b)
    kind = b.context if b.context != "unknown" else b.opener.command
    return {
        "uid": f"{kind}:{ident}" if ident is not None else f"{kind}:line{b.opener.line}",
        "kind": kind, "context": b.context, "opener": f"#{b.opener.command}",
        "id": ident if isinstance(ident, int) else None, "selector": ident if isinstance(ident, str) else None,
        "new": b.new, "name": block_name(b),
        "status": "parsed_only: contents are listed verbatim and not interpreted or verified",
        "authored": _authored(b.context, b, {}), "source": src,
        "diagnostics": _diag_in(c.validation, src["line"], src["end_line"]),
    }


def _scan_assets(project, used: dict[str, list[dict[str, Any]]], slug: str) -> tuple[list[dict[str, Any]],
                                                                                       list[dict[str, Any]]]:
    """Files in the mod folder (links skipped) with header info, hash and the definitions that use them."""
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(project.mod_dir, followlinks=False):
        d = Path(dirpath)
        for name in sorted(list(dirnames)):
            if is_link(d / name):
                skipped.append({"path": (d / name).relative_to(project.mod_dir).as_posix(),
                                "reason": "symlink/junction not followed"})
                dirnames.remove(name)
        for name in sorted(filenames):
            p = d / name
            rel = p.relative_to(project.mod_dir).as_posix()
            if is_link(p):
                skipped.append({"path": rel, "reason": "symlink/junction not read"})
                continue
            if rel.endswith(".dm"):
                continue
            data = p.read_bytes()
            entry: dict[str, Any] = {"path": rel, "bytes": len(data), "sha256": sha256_bytes(data),
                                     "url": f"/api/projects/{slug}/assets/{rel}", "used_by": used.get(rel, [])}
            if p.suffix.lower() in (".png", ".tga"):
                info = image_info(p)
                entry.update(format=info["format"], width=info["width"], height=info["height"],
                             depth=info["depth"], problems=info["problems"])
                entry["browser_preview"] = entry["url"] if info["format"] == "png" else (
                    f"{entry['url']}?format=png" if info["format"] == "tga" else None)
            out.append(entry)
    missing = [{"path": ref, "used_by": users, "status": "missing"} for ref, users in used.items()
               if not any(a["path"] == ref for a in out)]
    return out + missing, skipped


READINESS_LIST_LIMIT = 12  # rows per readiness list; the full data stays in the model and the Validation/Assets views


def _live_cmd(u: dict[str, Any], command: str) -> dict[str, Any] | None:
    """The last authored command of this name that a later #copystats did not overwrite."""
    return next((s for s in reversed(u["authored"]) if s["command"] == command
                 and not str(s.get("effect") or "").startswith("overwritten")), None)


def _sprite_status(u: dict[str, Any], files: set[str], catalog_ids: set[int], project_ids: set[int]) -> dict[str, Any]:
    """Where a monster's effective idle sprite comes from, read from the parsed block (never from the game).

    custom   - #spr1 names a file present in the mod folder;
    missing  - #spr1 names a file that is not there, or a new monster has no sprite source at all;
    vanilla  - the game's own sprite via #copyspr, a catalog #copystats donor or a selected vanilla monster;
    inherited- copied from another project monster (chained, not resolved here).
    A vanilla source the catalog cannot confirm (no catalog, or an unknown number) is marked unverified.
    """
    base = {"uid": u["uid"], "id": u["id"], "name": u["name"], "role": u["role"], "line": u["source"]["line"]}
    idle, attack = u["sprites"]["idle"], u["sprites"]["attack"]
    overwritten = [{"command": s["command"], "line": s["line"], "effect": s["effect"]} for s in u["authored"]
                   if s["command"] in ("#spr1", "#spr2") and str(s.get("effect") or "").startswith("overwritten")]
    if idle:
        missing = [f for f in (idle, attack) if f and f["path"] not in files]
        return {**base, "status": "missing" if missing else "custom", "idle": idle["path"],
                "attack": attack["path"] if attack else None, "missing": [f["path"] for f in missing],
                "overwritten": overwritten}
    cs = _live_cmd(u, "#copyspr")
    ref = _int(cs["args"][0]) if cs and cs["args"] else None
    if cs:
        source = {"via": "#copyspr", "ref": cs["args"][0] if cs["args"] else None, "line": cs["line"],
                  "verified": ref in catalog_ids}
        status = "inherited" if ref in project_ids else "vanilla"
    elif u["donor"]:
        d = u["donor"]
        source = {"via": "#copystats", "ref": d["ref"], "name": d["name"], "line": d["line"],
                  "verified": d["id"] in catalog_ids}
        status = "inherited" if d["id"] in project_ids else "vanilla"
    elif not u["new"]:
        source = {"via": "#selectmonster", "ref": u["id"] if u["id"] is not None else u["selector"],
                  "line": u["source"]["line"], "verified": u["id"] in catalog_ids}
        status = "vanilla"
    else:
        source, status = None, "missing"
    return {**base, "status": status, "source": source, "missing": [], "overwritten": overwritten}


def build_readiness(monsters: list[dict[str, Any]], assets: list[dict[str, Any]],
                    validation: dict[str, Any] | None, catalog: Catalog | None) -> dict[str, Any]:
    """Project readiness from the parsed mod and the current mod folder (no fixed demo numbers).

    Shared sprites (one file or identical bytes used by several monsters) and vanilla sprites are informational;
    only referenced-but-absent files, monsters with no sprite source and validation errors need attention."""
    files = {a["path"] for a in assets if "bytes" in a}
    catalog_ids = {i for i in (_int(k) for k in _cat_rows(catalog, "units")) if i is not None}
    project_ids = {u["id"] for u in monsters if u["new"] and u["id"] is not None}
    sprites = [_sprite_status(u, files, catalog_ids, project_ids) for u in monsters]
    by_status: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for s in sprites:
        by_status[s["status"]].append(s)

    # Shared custom sprites: the same idle file named by several monsters, then identical bytes under other names.
    sha = {a["path"]: a["sha256"] for a in assets if "bytes" in a}
    by_file: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for s in by_status["custom"]:
        by_file[s["idle"]].append(s)
    shared = [{"kind": "same_file", "files": [path], "monsters": [_ref(x) for x in group]}
              for path, group in sorted(by_file.items()) if len(group) > 1]
    by_hash: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(by_file):
        by_hash[sha[path]].append(path)
    for paths in by_hash.values():
        if len(paths) > 1:
            shared.append({"kind": "same_content", "files": paths,
                           "monsters": [_ref(x) for p in paths for x in by_file[p]]})

    missing_assets = [{"path": a["path"], "used_by": a["used_by"]} for a in assets if a.get("status") == "missing"]
    errors = (validation or {}).get("errors") or []
    v_counts = (validation or {}).get("counts")
    attention = len(missing_assets) + len(by_status["missing"]) + (len(errors) if validation else 1)
    return {
        "status": "attention" if attention else "ready",
        "sprites": {
            "counts": {k: len(by_status[k]) for k in ("custom", "vanilla", "inherited", "missing")},
            "missing": by_status["missing"][:READINESS_LIST_LIMIT],
            "vanilla": by_status["vanilla"][:READINESS_LIST_LIMIT],
            "inherited": by_status["inherited"][:READINESS_LIST_LIMIT],
            "overwritten": [s for s in sprites if s["overwritten"]][:READINESS_LIST_LIMIT],
            "shared": shared[:READINESS_LIST_LIMIT], "shared_count": len(shared),
        },
        "missing_assets": missing_assets[:READINESS_LIST_LIMIT], "missing_assets_count": len(missing_assets),
        "validation": {"available": validation is not None, "ok": (validation or {}).get("ok"),
                       "counts": v_counts, "sha256": (validation or {}).get("sha256"),
                       "errors": errors[:READINESS_LIST_LIMIT]},
        "limit": READINESS_LIST_LIMIT,
        "note": "Read from the saved .dm and the files now in the mod folder. Shared and vanilla sprites are "
                "informational; the game itself is not consulted.",
    }


def _ref(s: dict[str, Any]) -> dict[str, Any]:
    return {"uid": s["uid"], "id": s["id"], "name": s["name"], "role": s["role"]}


def _toplevel(pr, dm_rel: str) -> dict[str, Any]:
    info: dict[str, Any] = {"modname": None, "description": None, "version": None, "domversion": None,
                            "icon": None}
    other = []
    for st in pr.toplevel:
        if st.command in info and st.args:
            info[st.command] = {"value": st.args[0].value, "raw": st.args[0].raw, "line": st.line, "file": dm_rel}
        else:
            other.append({"line": st.line, "command": f"#{st.command}", "args": [a.raw for a in st.args],
                          "status": _cmd_status("top", st.command)})
    info["other_commands"] = other
    return info


def project_docs(root: Path) -> list[dict[str, Any]]:
    """Markdown files at the project root or in its docs/ folder (links skipped)."""
    out = []
    for sub in (root, root / "docs"):
        if not sub.is_dir() or is_link(sub):
            continue
        for p in sorted(sub.iterdir()):
            if p.suffix.lower() == ".md" and p.is_file() and not is_link(p):
                out.append({"name": p.relative_to(root).as_posix(), "bytes": p.stat().st_size})
    return out


def build_project_model(workspace: Path, slug: str, catalog: Catalog | None) -> dict[str, Any]:
    """The complete read-only browser model of one project (no writes, no caching)."""
    project = open_project(workspace, slug)
    dm_path = resolve_dm_target(project, None)
    data, text, enc = read_dm(dm_path)
    dm_rel = project.rel(dm_path)
    sha = sha256_bytes(data)
    diagnostics: list[dict[str, Any]] = []
    try:
        validation = validate_project(workspace, slug, catalog)
    except KosmoError as exc:
        validation = None
        diagnostics.append({"severity": "error", "code": f"validate_failed:{exc.code}", "message": exc.message})
    try:
        inspected = inspect_mod(workspace, slug)
    except KosmoError as exc:
        inspected = None
        diagnostics.append({"severity": "error", "code": f"inspect_failed:{exc.code}", "message": exc.message})
    for label, other in (("validation", validation), ("inspection", inspected)):
        if other and other.get("sha256") != sha:
            diagnostics.append({"severity": "warning", "code": "changed_during_read",
                                "message": f"The .dm changed while reading; {label} may describe another version."})
    pr = parse(text)
    from .resolution import relationships, layers, overlay_catalog
    from .equipped import equipped_sheet
    graph, compatibility = relationships(workspace, project, text, catalog)
    ordered = layers(workspace, project, text)
    prior = ordered[:-1]
    c = _Ctx(slug, dm_rel, text.splitlines(), overlay_catalog(catalog, prior) if prior else catalog, validation)

    # Index names/ids first so references inside any block resolve regardless of order.
    for b in pr.blocks:
        ident, nm = block_id(b), block_name(b)
        if b.context == "monster":
            if isinstance(ident, int):
                c.monsters_by_id[ident] = {"name": nm}
            if nm:
                c.monsters_by_name.setdefault(nm.lower(), []).append(ident)
        elif b.context == "site":
            if isinstance(ident, int):
                c.sites_by_id[ident] = {"name": nm}
            if nm:
                c.sites_by_name.setdefault(nm.lower(), []).append(ident)

    monsters, sites, nations, others = [], [], [], []
    nation_blocks: list[Block] = []
    for b in pr.blocks:
        c.catalog = overlay_catalog(catalog, prior) if prior else catalog
        if b.context == "monster":
            unit = _monster_model(c, b)
            unit['resolved']['equipped'] = equipped_sheet(unit, b, c.catalog)
            monsters.append(unit)
        elif b.context == "site":
            sites.append(_site_model(c, b))
        elif b.context == "nation":
            nations.append(_nation_model(c, b))
            nation_blocks.append(b)
        else:
            others.append(_definition_model(c, b))
        prior.append(('project', text[b.opener.start:b.end.end] if b.end else text[b.opener.start:]))

    graph_objects = {o['key']: o for o in graph['objects']}
    for obj in [*monsters, *sites, *nations, *others]:
        key = f"{obj.get('context', obj['kind'])}:line:{obj['source']['line']}"
        obj['uses'] = graph['outgoing'].get(key, [])
        obj['used_by'] = graph['incoming'].get(key, [])
        obj['identity'] = graph_objects.get(key, {}).get('identity')

    # Roles and recruitment come from nation and site commands that reference project monsters. A monster's
    # "nations" lists only explicit ties: nation-block commands and #homecom/#homemon/#com/#mon on that nation's
    # #startsite. Donor (#copystats) recruitment is never inferred.
    by_id = {m["id"]: m for m in monsters if m["id"] is not None}
    roles: dict[int, set[str]] = collections.defaultdict(set)
    god_refs: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for n in nations:
        # Keep cleared/overwritten commands in Source, but do not revive their roster ties after an edit.
        last_rec_reset = max((s["line"] for s in n["authored"] if s["command"] == "#clearrec"), default=0)
        last_god_reset = max((s["line"] for s in n["authored"]
                              if s["command"] in ("#clearnation", "#cleargods")), default=0)
        hero_reset = max((s["line"] for s in n["authored"] if s["command"] == "#clearnation"), default=0)
        hero_lines = {cmd: max((s["line"] for s in n["authored"] if s["command"] == "#" + cmd), default=0)
                      for cmd in NATION_HERO_CMDS}
        start_lines = {s["line"] for s in n["authored"]
                       if s["command"] in ("#startcom", "#startscout", "#startunittype1", "#startunittype2")}
        live_start = {x["line"] for x in (n["start_army"]["commander"], n["start_army"]["scout"]) if x}
        last_start_com = max((s["line"] for s in n["authored"] if s["command"] == "#startcom"), default=0)
        for command in ("#startunittype1", "#startunittype2"):
            live_start.add(max((s["line"] for s in n["authored"]
                                if s["command"] == command and s["line"] > last_start_com), default=0))
        for st in n["authored"]:
            cmd = st["command"][1:]
            if cmd in NATION_HERO_CMDS and (st["line"] <= hero_reset or st["line"] != hero_lines[cmd]):
                continue
            if cmd in ("addrecunit", "addreccom") and st["line"] < last_rec_reset:
                continue
            if cmd == "addgod" and st["line"] < last_god_reset:
                continue
            if st["line"] in start_lines and st["line"] not in live_start:
                continue
            mid = _int(st["args"][0]) if st["args"] else None
            if mid is None and st["args"]:
                named = c.monsters_by_name.get(st["args"][0].strip('"').lower(), [])
                mid = named[0] if len(named) == 1 else None
            if mid in by_id:
                if cmd in NATION_COMMANDER_CMDS | NATION_TROOP_CMDS | NATION_GOD_CMDS:
                    by_id[mid]["nations"].append({"nation": n["uid"], "via": st["command"], "line": st["line"]})
                if cmd in NATION_COMMANDER_CMDS:
                    roles[mid].add("commander")
                elif cmd in NATION_TROOP_CMDS:
                    roles[mid].add("troop")
                if cmd in NATION_GOD_CMDS:
                    god_refs[mid].append({"via": st["command"], "line": st["line"], "nation": n["uid"]})
                if cmd in RECRUIT_WHERE:
                    by_id[mid]["recruitment"].append({"via": st["command"], "line": st["line"],
                                                      "nation": n["uid"], "where": RECRUIT_WHERE[cmd]})
    site_by_uid = {s["uid"]: s for s in sites}
    for n in nations:
        for ss in n["start_sites"]:
            uid = ss["site"].get("uid")
            if uid in site_by_uid:
                site_by_uid[uid]["start_site_of"].append(n["uid"])
                s = site_by_uid[uid]
                if s["gems"]:
                    n["gem_sites"].append({"site": uid, "name": s["name"], "gems": s["gems"]})
    for s in sites:
        for u in s["units"]:
            mid = u["monster"].get("id") if u["monster"].get("origin") == "project" else None
            if mid in by_id:
                roles[mid].add(u["role"])
                where = RECRUIT_WHERE.get(u["command"][1:], "Recruitable where this site is")
                if s["start_site_of"]:
                    where += f"; start site of {', '.join(s['start_site_of'])}"
                by_id[mid]["recruitment"].append({"via": u["command"], "line": u["line"], "site": s["uid"],
                                                  "site_name": s["name"], "where": where})
                for nuid in s["start_site_of"]:
                    by_id[mid]["nations"].append({"nation": nuid, "via": u["command"], "line": u["line"],
                                                  "site": s["uid"]})
    # Associate explicit national summons without treating them as recruitable units.
    spell_effects = {}
    if catalog is not None:
        from .catalog import _read_table
        effects_path = catalog.gamedata / "effects_spells.csv"
        if effects_path.is_file():
            spell_effects = {row.get("record_id"): row for row in _read_table(effects_path)}
    for block in pr.blocks:
        if block.context != "spell":
            continue
        effect, target, restrictions = None, None, []
        for statement in block.statements:
            cmd, value = statement.command, _arg_value(statement)
            if cmd in ("clear", "copyspell"):
                effect, target, restrictions = None, None, []
                row = catalog.row("spells", value) if cmd == "copyspell" and catalog is not None else None
                if row:
                    raw_effect = spell_effects.get(row.get("effect_record_id"), {})
                    effect = _int(raw_effect.get("effect_number"))
                    if effect is not None and raw_effect.get("ritual") == "1" and effect < 10000:
                        effect += 10000
                    target = _int(raw_effect.get("raw_argument"))
            elif cmd == "effect":
                effect = _int(value)
            elif cmd == "damage":
                target = _int(value)
            elif cmd == "restricted":
                restrictions.append(value)
        if effect not in (1, 31, 43, 126, 10001, 10021, 10037, 10038) or target not in by_id:
            continue
        for nation in nations:
            if nation["id"] in restrictions or nation["name"] in restrictions:
                by_id[target]["nations"].append({"nation": nation["uid"], "via": "national spell",
                                                "line": block.opener.line, "spell": block_name(block)})
                by_id[target].setdefault("summoning", []).append({"nation": nation["uid"],
                    "spell": block_name(block), "line": block.opener.line, "effect": effect})
                roles[target].add("commander" if effect == 10021 else "troop")
    for mid, r in roles.items():
        by_id[mid]["role"] = "commander" if "commander" in r else "troop"
    for mid, refs in god_refs.items():
        # A monster only named by god commands is a pretender form, never a recruitable troop or commander.
        by_id[mid]["god_commands"] = refs
        if mid not in roles and any(x["via"] == "#addgod" for x in refs):
            by_id[mid]["role"] = "pretender"

    used: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for b in pr.blocks:
        for st in b.statements:
            if st.command in GENERIC_ASSETS and st.args and st.args[0].kind == "str":
                ident = block_id(b)
                ctx = b.context if b.context != "unknown" else b.opener.command
                used[str(st.args[0].value)].append({
                    "uid": f"{ctx}:{ident}" if ident is not None else f"{ctx}:line{b.opener.line}",
                    "name": block_name(b), "command": f"#{st.command}", "line": st.line})
    for st in pr.toplevel:
        if st.command in GENERIC_ASSETS and st.args and st.args[0].kind == "str":
            used[str(st.args[0].value)].append({"uid": "mod", "name": None, "command": f"#{st.command}",
                                                "line": st.line})
    assets, skipped = _scan_assets(project, dict(used), slug)
    c.asset_index = {a["path"] for a in assets if "bytes" in a}
    pretenders = build_pretenders(c, nation_blocks, nations, monsters)

    counts = {"nations": len(nations), "monsters": len(monsters),
              "troops": sum(m["role"] == "troop" for m in monsters),
              "commanders": sum(m["role"] == "commander" for m in monsters),
              "unassigned_monsters": sum(m["role"] == "unassigned" for m in monsters),
              "pretender_forms": sum(m["role"] == "pretender" for m in monsters),
              "roster_units": sum(m["role"] != "pretender" for m in monsters),
              "pretender_candidates": pretenders["counts"]["listed_for_first_nation"],
              "pretender_gods": pretenders["counts"]["gods"],
              "sites": len(sites), "other_definitions": len(others),
              "sprite_frames": sum(1 for m in monsters for k in ("idle", "attack") if m["sprites"][k]),
              "flags": sum(1 for n in nations if n["flag"]), "asset_files": sum(1 for a in assets if "bytes" in a)}
    top = _toplevel(pr, dm_rel)
    lead = nations[0] if nations else None
    banner = None  # the mod's #icon banner (shown on project cards and the project heading, never a nation flag)
    if top["icon"] and isinstance(top["icon"]["value"], str):
        ref = top["icon"]["value"]
        found = next((a for a in assets if a["path"] == ref and "bytes" in a), None)
        banner = {"path": ref, "line": top["icon"]["line"], "url": c.asset_url(ref),
                  "status": "ok" if found else "missing",
                  "preview": found.get("browser_preview") if found else None,
                  "width": found.get("width") if found else None, "height": found.get("height") if found else None}
    model = {
        "schema": SCHEMA,
        "provenance": {
            "tool": "kosmokrator", "tool_version": __version__, "manual_version": MANUAL_VERSION,
            "generated_utc": _now(), "project": slug, "file": dm_rel, "sha256": sha, "encoding": enc,
            "catalog": catalog.meta if catalog else None,
            "catalog_dataset_version": catalog.meta.get("dataset_version") if catalog else None,
            "catalog_revision": catalog.meta.get("revision") if catalog else None,
        },
        "project": {
            "slug": slug, "name": project.meta.get("name"), "mod_name": (top["modname"] or {}).get("value"),
            "version": (top["version"] or {}).get("raw"), "era": lead["era"] if lead else None,
            "era_name": lead["era_name"] if lead else None,
            "target_game_version": project.meta.get("target_game_version"),
            "manual_version": project.meta.get("manual_version"), "dm_path": dm_rel,
            "dependencies": project.meta.get("dependencies") or [], "docs": project_docs(project.root),
            "banner": banner,
        },
        "mod_info": top, "counts": counts,
        "relationships": {k: v for k, v in graph.items() if k not in ('incoming', 'outgoing')},
        "compatibility": compatibility,
        "validation": validation, "inspection": {k: inspected[k] for k in (
            "statement_count", "syntax_issues", "stray_text", "unverified_commands", "limitations")}
        if inspected else None,
        "nations": nations, "monsters": monsters, "sites": sites, "other_definitions": others,
        "pretenders": pretenders, "assets": assets, "assets_skipped": skipped, "diagnostics": diagnostics,
        "readiness": build_readiness(monsters, assets, validation, catalog),
        "limitations": [
            "Read-only static view. This is not a Dominions interpreter: only the listed fields are resolved, "
            "by applying the block's commands in order over the #copystats donor.",
            "Equipped values are static estimates from supported base fields and catalog equipment. Conditional abilities, spells and combat states are not simulated.",
            "Autocalculated or mounted costs remain unresolved; fixed components and equipment resources are shown where supported.",
            "Commands marked unsupported may change values that are shown as resolved.",
            "Donor data comes from the supplied third-party catalog and may differ from the installed game.",
        ],
    }


    from .inheritance import inheritance_report
    from .balance import balance_report
    model['inheritance'] = inheritance_report(model, catalog)
    model['balance'] = balance_report(model, catalog)
    return model


# Raw dom6inspector nation tables that list a monster by nation (the inspector's own table names).
CATALOG_RECRUIT_TABLES = {"fort_troop_types_by_nation.csv": "fort troop", "fort_leader_types_by_nation.csv": "fort commander",
                          "nonfort_troop_types_by_nation.csv": "non-fort troop",
                          "nonfort_leader_types_by_nation.csv": "non-fort commander"}


def _as_catalog(x: Any) -> Any:
    """Relabel resolver output for a bare catalog unit: 'donor' values are the catalog row; no .dm lines."""
    if isinstance(x, dict):
        out = {k: _as_catalog(v) for k, v in x.items()}
        if out.get("source") == "donor":
            out["source"], out["line"] = "catalog", None
        return out
    if isinstance(x, list):
        return [_as_catalog(v) for v in x]
    return x


def catalog_unit_view(catalog: Catalog | None, slug: str, mid: int) -> dict[str, Any]:
    """One catalog unit through the same resolver as project monsters (a synthetic #selectmonster), read-only.

    For side-by-side comparison only: base values, equipment, magic, abilities, raw cost components and the raw
    nation tables that list it. Final costs and equipped combat values are not computed."""
    if catalog is None:
        raise KosmoError("catalog_missing", "No game-data catalog: vanilla units cannot be compared.")
    row = _cat_rows(catalog, "units").get(str(mid))
    if row is None:
        raise KosmoError("object_missing", f"Unit {mid} is not in the catalog.")
    text = f"#selectmonster {mid}\n#end\n"
    c = _Ctx(slug, "catalog", text.splitlines(), catalog, None)
    r = _resolve_monster(c, parse(text).blocks[0])
    nations = _cat_rows(catalog, "nations")
    recruit = []
    for table, label in CATALOG_RECRUIT_TABLES.items():
        for t in _table(catalog, table):
            if _int(t.get("monster_number")) == mid:
                nid = _int(t.get("nation_number"))
                n = nations.get(str(nid)) or {}
                recruit.append({"table": table, "kind": label, "nation_id": nid, "nation": n.get("name"),
                                "era": _int(n.get("era")), "era_name": ERA_NAMES.get(_int(n.get("era")) or 0)})
    base = f"/api/projects/{slug}/catalog-units/{mid}/sprite"
    return {
        "uid": f"catalog-unit:{mid}", "id": mid, "source": "catalog", "name": row.get("name"),
        "resolved": _as_catalog(r["resolved"]), "unresolved": r["unresolved"],
        "sprites": {k: ({"url": f"{base}/{k}"} if catalog_sprite_path(catalog, mid, k) else None)
                    for k in ("idle", "attack")},
        "recruitment": recruit, "catalog_row": _raw_row(row),
        "provenance": {"catalog": catalog.meta, "dataset_version": catalog.meta.get("dataset_version"),
                       "revision": catalog.meta.get("revision")},
        "limitations": ["Raw dom6inspector data through the browser's resolver; it may differ from the installed game.",
                        "Recruitment lists only the inspector's nation tables (fort/non-fort); capital-only start-site "
                        "recruitment of vanilla nations is not shown.",
                        "Final gold, resource and recruitment-point costs and equipped combat values are not computed."],
    }


def project_fingerprint(workspace: Path, slug: str) -> str:
    """Cheap change detector: sizes/mtimes of metadata and every file under the mod folder."""
    root = contained(workspace, slug, what="project directory")
    h = hashlib.sha256()
    for p in (root / META_FILE,):
        try:
            st = p.stat()
            h.update(f"{p.name}:{st.st_size}:{st.st_mtime_ns};".encode())
        except OSError:
            h.update(b"meta-missing;")
    mod = root / "mod"
    project = open_project(workspace, slug)
    from .project import dependency_texts
    for label, source in dependency_texts(workspace, project.meta.get('dependencies')):
        h.update(label.encode())
        h.update(source.encode())
    for dirpath, dirnames, filenames in os.walk(mod, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                st = os.lstat(p)
            except OSError:
                continue
            h.update(f"{p.relative_to(root).as_posix()}:{st.st_size}:{st.st_mtime_ns};".encode())
    return h.hexdigest()


class ModelCache:
    """Small LRU of built models keyed by project fingerprint, so edited mods are rebuilt on next request."""

    def __init__(self, size: int = 6) -> None:
        self.size = size
        self._data: collections.OrderedDict[tuple[str, str, str], dict[str, Any]] = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, workspace: Path, slug: str, catalog: Catalog | None) -> dict[str, Any]:
        key = (slug, project_fingerprint(workspace, slug), str(catalog.gamedata) if catalog else "")
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
        model = build_project_model(workspace, slug, catalog)
        with self._lock:
            self._data[key] = model
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)
        return model


def list_projects(workspace: Path, cache: ModelCache, catalog: Catalog | None) -> dict[str, Any]:
    """Every directory holding kosmokrator.json; a broken project yields an error entry, not a failure."""
    projects = []
    for entry in sorted(workspace.iterdir(), key=lambda p: p.name):
        if is_link(entry) or not entry.is_dir() or not (entry / META_FILE).exists():
            continue
        slug = entry.name
        item: dict[str, Any] = {"slug": slug, "ok": False}
        try:
            if not SLUG_RE.match(slug):
                raise KosmoError("bad_slug", "Directory name is not a valid project slug")
            m = cache.get(workspace, slug, catalog)
            v = m["validation"]
            lead = m["nations"][0] if m["nations"] else None
            item.update(ok=True, name=m["project"]["name"], mod_name=m["project"]["mod_name"],
                        version=m["project"]["version"], era=m["project"]["era"],
                        era_name=m["project"]["era_name"], nation=lead["name"] if lead else None,
                        flag=(lead or {}).get("flag"),
                        flag_preview=f"/api/projects/{slug}/assets/{lead['flag']['path']}?format=png"
                        if lead and lead.get("flag") else None,
                        banner=m["project"].get("banner"),
                        banner_preview=(m["project"].get("banner") or {}).get("preview"),
                        counts=m["counts"],
                        validation={"ok": v["ok"], "counts": v["counts"]} if v else None,
                        sha256=m["provenance"]["sha256"])
        except KosmoError as exc:
            item["error"] = exc.to_dict()
        except (OSError, ValueError, UnicodeError) as exc:
            item["error"] = {"code": "read_error", "message": str(exc)}
        projects.append(item)
    return {"schema": SCHEMA, "workspace": str(workspace), "projects": projects,
            "catalog": catalog.meta if catalog else None}


def asset_path(workspace: Path, slug: str, ref: str) -> Path:
    """Resolve an asset request inside the project's mod folder: exact case, no '..', no links."""
    project = open_project(workspace, slug)
    problems = mod_relpath_problems(ref)
    if problems:
        raise KosmoError("bad_asset_path", "; ".join(problems), path=ref)
    contained(project.mod_dir, ref, what="asset")
    found, why = exact_case_lookup(project.mod_dir, ref)
    if found is None:
        raise KosmoError("asset_" + (why or "missing"), f"Asset not available: {why}", path=ref)
    return contained(project.mod_dir, found, what="asset")


def project_doc_path(workspace: Path, slug: str, name: str) -> Path:
    project = open_project(workspace, slug)
    allowed = {d["name"] for d in project_docs(project.root)}
    if name not in allowed:
        raise KosmoError("doc_missing", "No such project document", name=name)
    return contained(project.root, name, what="document")
