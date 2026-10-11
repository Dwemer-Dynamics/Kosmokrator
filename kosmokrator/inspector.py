"""Read-only vanilla inspector over the catalog one project reads (its reference snapshot, or the live catalog).

Browses units, sites, events, mercenaries, items, spells, weapons, armour and nations without a query: counts,
bounded pages, name/id search, up to MAX_CONDITIONS AND-ed column conditions (numeric comparisons compare numbers,
never text), sorting by id, name or any column, and per-category filter metadata built from the catalog's own
values. Details reuse the existing resolvers (the catalog unit view, the reference detail of
spells/sites/weapons/armour) and add readable mercenary companies and events.
Nothing here writes; images are served only by the existing id-based sprite and icon routes.
"""

from __future__ import annotations

import re
from typing import Any

from .catalog import ALL_CATEGORIES, Catalog
from .errors import KosmoError

CATS: dict[str, str] = {
    "units": "Units", "sites": "Sites", "events": "Events", "mercs": "Mercenaries", "items": "Items",
    "spells": "Spells", "weapons": "Weapons", "armors": "Armour", "nations": "Nations",
}
MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 40
MAX_QUERY = 60
FILTER_OPS = ("has", "eq", "contains")  # the original single raw-column filter (field/op/value), kept as it was
# Conditions (repeatable `c=field:op[:value]`). Numeric operators compare numbers; a blank cell counts as 0 for them
# because the catalog leaves zero values blank. eq/ne compare numbers when the column and value are both numeric.
COND_OPS = {"has": "has a value", "none": "is blank or 0", "eq": "equals", "ne": "does not equal",
            "contains": "contains", "gt": "greater than", "gte": "at least", "lt": "less than", "lte": "at most",
            "between": "between"}
NUMERIC_OPS = ("gt", "gte", "lt", "lte", "between")
VALUE_OPS = ("eq", "ne", "contains", *NUMERIC_OPS)
MAX_CONDITIONS = 8
SORT_ORDERS = ("asc", "desc")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
ATTRIBUTION = ("Vanilla game data from dom6inspector by larzm42 (https://github.com/larzm42/dom6inspector, GPL-3.0). "
               "Dominions 6 and its artwork belong to Illwinter Game Design. Third-party extraction: values may differ "
               "from the installed game. Read-only; never exported with the mod.")
MANUAL_MERC = {"document": "Dominions 6 Modding Manual", "version": "6.36", "page": 63}
# Manual p.63, quoted as documented.
MERC_LEVELS = {0: "Level 0: appears early in the game", 1: "Level 1: appears later", 2: "Level 2: appears last of all"}
ERA_MASKS = {1: "Early era", 2: "Middle era", 3: "Early + middle", 4: "Late era", 5: "Early + late", 6: "Middle + late",
             7: "All eras"}
RANDEQUIP = {0: "0: none", 1: "1", 2: "2", 3: "3: extremely powerful"}
ITEM_TYPES = {"1-h wpn": "One-handed weapon", "2-h wpn": "Two-handed weapon", "missile": "Missile weapon",
              "helm": "Helmet", "crown": "Crown", "armor": "Body armour", "barding": "Barding", "shield": "Shield",
              "boots": "Boots", "misc": "Miscellaneous"}


def _int(v: Any) -> int | None:
    s = str(v).strip() if v is not None else ""
    return int(s) if s.lstrip("-").isdigit() else None


def _need(catalog: Catalog | None, cat: str) -> Catalog:
    if cat not in CATS:
        raise KosmoError("bad_category", f"category must be one of {', '.join(CATS)}.")
    if catalog is None:
        raise KosmoError("catalog_missing", "No game-data catalog: this project has no reference snapshot and the "
                                            "server has no live catalog.")
    if not catalog.has_table(cat):
        raise KosmoError("catalog_incomplete", f"The catalog has no {ALL_CATEGORIES[cat][0]} table. Refresh the "
                                               "project's reference snapshot from a complete dom6inspector checkout.")
    return catalog


def provenance(catalog: Catalog) -> dict[str, Any]:
    meta = catalog.meta or {}
    snap = meta.get("reference_snapshot")
    return {"source": meta.get("source"), "source_url": meta.get("source_url"), "revision": meta.get("revision"),
            "dataset_version": meta.get("dataset_version"), "dataset_version_source": meta.get("dataset_version_source"),
            "reference_snapshot": snap, "reads": "project reference snapshot" if snap else "live catalog",
            "disclaimer": meta.get("disclaimer"), "attribution": ATTRIBUTION, "read_only": True}


def summary(catalog: Catalog | None) -> dict[str, Any]:
    """Row counts for every inspector category (None when a table is absent)."""
    if catalog is None:
        raise KosmoError("catalog_missing", "No game-data catalog: this project has no reference snapshot and the "
                                            "server has no live catalog.")
    cats = []
    for key, label in CATS.items():
        present = catalog.has_table(key)
        cats.append({"key": key, "label": label, "file": ALL_CATEGORIES[key][0],
                     "count": len(catalog.table(key)) if present else None, "available": present})
    return {"categories": cats, "provenance": provenance(catalog)}


# ---------- names shared by lists and details ----------

def _names(catalog: Catalog, cat: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for r in catalog.table(cat):
        i = _int(r.get("id"))
        if i is not None and i not in out:
            out[i] = (r.get("name") or "").strip()
    return out


def _unit_ref(units: dict[int, str], raw: Any) -> dict[str, Any] | None:
    i = _int(raw)
    if i is None or i <= 0:
        return None
    return {"id": i, "name": units.get(i), "in_catalog": i in units}


def _item_ref(items_by_name: dict[str, int], name: str) -> dict[str, Any] | None:
    n = (name or "").strip()
    if not n:
        return None
    return {"name": n, "id": items_by_name.get(n.lower())}


def _items_by_name(catalog: Catalog) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in catalog.table("items"):
        i = _int(r.get("id"))
        n = (r.get("name") or "").strip().lower()
        if i is not None and n and n not in out:
            out[n] = i
    return out


def _merc_items(r: dict[str, str]) -> list[str]:
    return [(r.get(k) or "").strip() for k in sorted(r, key=str) if k and k.startswith("item") and (r.get(k) or "").strip()]


# ---------- nation membership of catalog units ----------

AGES = {1: "Early", 2: "Middle", 3: "Late"}
ERA_BITS = {1: 1, 2: 2, 3: 4}  # mercenary #eramask bits per age (manual p.63)
NATION_FILTERS = ("national", "none")
UNIT_ROLES = {"troop": "Troops", "commander": "Commanders", "capital": "Capital-only", "hero": "Heroes"}
# dom6inspector nation tables that list recruitable monsters: (file, role, where).
_ROSTER_TABLES = tuple((f"{where}_{kind}_types_by_nation.csv", role, where) for where in ("fort", "nonfort", "coast")
                       for kind, role in (("troop", "troop"), ("leader", "commander")))
# attributes_by_nation codes (attribute_keys.csv) whose raw_value is a monster id.
_ATTR_UNITS = {**{a: ("hero", "hero") for a in range(139, 147)},
               **{a: ("commander", "underwater") for a in (172, 186, 187, 188)},
               **{a: ("troop", "underwater") for a in (189, 190, 191, 213)},
               **{a: ("troop" if a % 2 == 0 else "commander", "terrain") for a in range(294, 304)}}
_ATTR_CAPITAL = ("52", "100")  # capital magic site (#startsite): its hmon/hcom are capital-only recruits
MEMBERSHIP_NOTE = ("Nation membership comes from the catalog's fort, non-fort and coastal recruitment tables, "
                   "terrain and underwater recruits, national heroes and the capital site's recruits. Pretender "
                   "gods, summons, mercenaries and event units are not counted as national.")


def _aux(catalog: Catalog, name: str) -> list[dict[str, str]]:
    from .pretenders import _table
    return _table(catalog, name)


def nations_by_age(catalog: Catalog) -> dict[int, dict[str, Any]]:
    """Playable catalog nations (Early, Middle or Late) by id."""
    out: dict[int, dict[str, Any]] = {}
    for r in catalog.table("nations"):
        i, era = _int(r.get("id")), _int(r.get("era"))
        if i is not None and era in AGES:
            out[i] = {"id": i, "name": (r.get("name") or "").strip(), "epithet": (r.get("epithet") or "").strip(),
                      "era": era}
    return out


def unit_memberships(catalog: Catalog) -> dict[int, dict[int, dict[str, set[str]]]]:
    """unit id -> nation id -> {"roles": {...}, "where": {...}} from explicit catalog relations only. Memoized."""
    def build() -> dict[int, dict[int, dict[str, set[str]]]]:
        nations = nations_by_age(catalog)
        out: dict[int, dict[int, dict[str, set[str]]]] = {}

        def add(mid: int | None, nid: int | None, role: str, where: str) -> None:
            if mid is None or mid <= 0 or nid not in nations:
                return
            e = out.setdefault(mid, {}).setdefault(nid, {"roles": set(), "where": set()})
            e["roles"].add(role)
            e["where"].add(where)

        for name, role, where in _ROSTER_TABLES:
            for r in _aux(catalog, name):
                add(_int(r.get("monster_number")), _int(r.get("nation_number")), role, where)
        sites = {i: r for r in catalog.table("sites") if (i := _int(r.get("id"))) is not None}
        for r in _aux(catalog, "attributes_by_nation.csv"):
            a, nid, raw = _int(r.get("attribute")), _int(r.get("nation_number")), r.get("raw_value")
            if a in _ATTR_UNITS:
                role, where = _ATTR_UNITS[a]
                add(_int(raw), nid, role, where)
            elif str(a) in _ATTR_CAPITAL:
                site = sites.get(_int(raw) or -1) or {}
                for prefix, role in (("hmon", "troop"), ("hcom", "commander")):
                    for k in range(1, 6):
                        add(_int(site.get(f"{prefix}{k}")), nid, role, "capital")
        return out
    return catalog.memoized(("inspector-memberships",), build)


def _unit_scope(catalog: Catalog, age: str, nation: str, role: str) -> dict[str, Any] | None:
    """Validated age/nation/role unit filter, or None when none is set."""
    age, nation, role = (age or "").strip(), (nation or "").strip(), (role or "").strip()
    if not (age or nation or role):
        return None
    if age and _int(age) not in AGES:
        raise KosmoError("bad_query", "age must be 1 (Early), 2 (Middle) or 3 (Late).", field="age")
    if role and role not in UNIT_ROLES:
        raise KosmoError("bad_query", f"role must be one of {', '.join(UNIT_ROLES)}.", field="role")
    nations = nations_by_age(catalog)
    nid = _int(nation)
    if nation and nation not in NATION_FILTERS and nid not in nations:
        raise KosmoError("bad_query", "nation must be a catalog nation id, national or none.", field="nation")
    if nation == "none" and (age or role):
        raise KosmoError("bad_query", "Units without a nation have no age or national role.", field="nation")
    if nid in nations and age and nations[nid]["era"] != _int(age):
        raise KosmoError("bad_query", f"{nations[nid]['name']} is not a {AGES[_int(age)]} Age nation.", field="nation")
    return {"age": _int(age) if age else None, "nation": nid if nid in nations else nation or None, "role": role or None,
            "nations": nations, "members": unit_memberships(catalog)}


def _in_scope(uid: int, s: dict[str, Any]) -> bool:
    ties = s["members"].get(uid) or {}
    if s["nation"] == "none":
        return not ties
    for nid, e in ties.items():
        if isinstance(s["nation"], int) and nid != s["nation"]:
            continue
        if s["age"] and s["nations"][nid]["era"] != s["age"]:
            continue
        role = s["role"]
        if (not role or (role == "capital" and e["where"] == {"capital"}) or (role == "hero" and "hero" in e["where"])
                or (role in ("troop", "commander") and role in e["roles"] and e["where"] != {"hero"})):
            return True
    return False


_HOW = {"fort": "fort", "nonfort": "outside forts", "coast": "coastal fort", "underwater": "underwater fort",
        "terrain": "terrain recruit", "capital": "capital only", "hero": "hero"}


def unit_nation_ties(catalog: Catalog, uid: int) -> list[dict[str, Any]]:
    """Each nation that explicitly lists a unit, with readable roles and recruitment places."""
    nations = nations_by_age(catalog)
    out = []
    for nid, e in (unit_memberships(catalog).get(uid) or {}).items():
        where = e["where"] - {"capital"} if e["where"] != {"capital"} else e["where"]
        how = [r for r in ("commander", "troop") if r in e["roles"]] + [_HOW[w] for w in sorted(where) if w in _HOW]
        if "capital" in e["where"] and e["where"] != {"capital"}:
            how.append("also at capital")
        out.append({"id": nid, "name": nations[nid]["name"], "era": nations[nid]["era"], "roles": sorted(e["roles"]),
                    "where": sorted(e["where"]), "how": how})
    return sorted(out, key=lambda n: (n["era"], n["name"]))


def _unit_nations(catalog: Catalog, uid: int, age: int | None = None) -> list[dict[str, Any]]:
    nations = nations_by_age(catalog)
    ties = unit_memberships(catalog).get(uid) or {}
    out = [{"id": n, "name": nations[n]["name"], "era": nations[n]["era"]} for n in sorted(ties)
           if not age or nations[n]["era"] == age]
    return sorted(out, key=lambda n: (n["era"], n["name"]))


# ---------- list ----------

def _row_fields(cat: str, r: dict[str, str], ctx: dict[str, Any]) -> dict[str, Any]:
    """Compact list fields: the catalog's own search columns, plus readable merc and event columns."""
    extra = ALL_CATEGORIES[cat][1]
    fields: dict[str, Any] = {k: r[k] for k in extra if r.get(k) not in (None, "", "0")}
    if cat == "mercs":
        fields = {"bossname": r.get("bossname"), "nrunits": r.get("nrunits"), "level": r.get("level"),
                  "minpay": r.get("minpay"), "eramask": r.get("eramask")}
        units = ctx["units"]
        return {"fields": fields, "commander": _unit_ref(units, r.get("com")),
                "troop": _unit_ref(units, r.get("unit")), "items": _merc_items(r)}
    if cat == "events":
        return {"fields": fields, "description": (r.get("description") or "")[:240],
                "description_truncated": len(r.get("description") or "") > 240}
    return {"fields": fields}


def _summary(cat: str, r: dict[str, str]) -> list[str]:
    """A few readable list facts per row. Raw cost encodings (basecost) are left to the detail view."""
    from .content import ARMOR_TYPES, RARITY, SCHOOLS, SPELL_PATHS
    g = lambda k: (r.get(k) or "").strip()  # noqa: E731
    nz = lambda k: g(k) not in ("", "0")  # noqa: E731
    if cat == "units":
        paths = " ".join(f"{k}{g(k)}" for k in PATH_LETTERS if nz(k) and (_num(g(k)) or 0) > 0)
        return [f"HP {g('hp')}" if nz("hp") else None, f"Size {g('size')}" if nz("size") else None,
                f"Prot {g('prot')}" if nz("prot") else None, paths or None]
    if cat == "sites":
        return [g("path") or None, f"Level {g('level')}" if g("level") else None,
                dict(RARITY).get(_int(g("rarity")) if g("rarity") else -99)]
    if cat == "spells":
        path = dict(SPELL_PATHS).get(_int(g("path1")) if g("path1") else -1)
        return [dict(SCHOOLS).get(_int(g("school")) if g("school") else -2),
                f"{path} {g('pathlevel1')}" if path and path != "None" else None,
                f"Research {g('researchlevel')}" if g("researchlevel") and g("school") != "-1" else None]
    if cat == "items":
        main = PATH_LETTERS.get(g("mainpath"))
        sec = PATH_LETTERS.get(g("secondarypath"))
        return [ITEM_TYPES.get(g("type"), g("type") or None),
                " + ".join(x for x in (main and f"{main} {g('mainlevel')}", sec and f"{sec} {g('secondarylevel')}") if x)
                or None, f"Construction {g('constlevel')}" if g("constlevel") else None]
    if cat == "weapons":
        return [f"Att {g('att') or 0}", f"Def {g('def') or 0}", f"Len {g('len') or 0}",
                f"{g('nratt')} attacks" if nz("nratt") and g("nratt") != "1" else None]
    if cat == "armors":
        return [dict(ARMOR_TYPES).get(_int(g("type")) if g("type") else -1), f"Def {g('def') or 0}",
                f"Enc {g('enc') or 0}"]
    if cat == "nations":
        era = _int(g("era"))
        return [f"{AGES[era]} Age" if era in AGES else None, g("epithet") or None]
    if cat == "events":
        return [f"Rarity {g('rarity') or 0}"]
    return []


def _num(raw: Any) -> float | None:
    s = str(raw).strip() if raw is not None else ""
    return float(s) if _NUM_RE.match(s) else None


def _cell_num(raw: Any) -> float | None:
    """A cell as a number for numeric conditions and sorting: blank counts as 0, text is None (never matches)."""
    s = (raw or "").strip()
    return 0.0 if not s else float(s) if _NUM_RE.match(s) else None


def _fmt(x: float | None) -> str | None:
    return None if x is None else str(int(x)) if x == int(x) else format(x, "g")


def _columns(catalog: Catalog, cat: str) -> list[str]:
    rows = catalog.table(cat)
    return [c for c in (rows[0].keys() if rows else []) if c and c != "end"]


def column_info(catalog: Catalog, cat: str) -> dict[str, dict[str, Any]]:
    """Per column: kind (number, text or empty), non-blank count and numeric range. Memoized per catalog object."""
    def build() -> dict[str, dict[str, Any]]:
        rows = catalog.table(cat)
        keys = _columns(catalog, cat)
        if rows and None not in rows[0] and all(len(r) == len(rows[0]) for r in rows):
            # Transpose once (C loops) instead of 500+ Python passes over every row.
            by_col = dict(zip(rows[0].keys(), zip(*(r.values() for r in rows))))
        else:
            by_col = {k: tuple(r.get(k) or "" for r in rows) for k in keys}
        out: dict[str, dict[str, Any]] = {}
        for k in keys:
            vals = by_col.get(k, ())
            distinct = {v.strip() for v in set(vals) if v and v.strip()}
            filled = sum(1 for v in vals if v and v.strip()) if distinct else 0
            nums = [float(v) for v in distinct if _NUM_RE.match(v)]
            kind = "empty" if not distinct else "number" if len(nums) == len(distinct) else "text"
            info: dict[str, Any] = {"kind": kind, "filled": filled, "distinct": len(distinct)}
            if kind == "number":
                lo, hi = min(nums), max(nums)
                if filled < len(rows):  # blank cells count as 0
                    lo, hi = min(lo, 0.0), max(hi, 0.0)
                info.update(min=_fmt(lo), max=_fmt(hi))
            out[k] = info
        return out
    return catalog.memoized(("inspector-columns", cat), build)


def parse_condition(text: str) -> dict[str, str]:
    """`field:op[:value]`; between takes `low..high` (for example `size:between:2..3`, `rarity:between:-2..0`)."""
    parts = str(text).split(":", 2)
    if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
        raise KosmoError("bad_query", "Write a condition as column:op or column:op:value.", field="c")
    field, op, value = parts[0].strip(), parts[1].strip(), parts[2] if len(parts) == 3 else ""
    cond = {"field": field, "op": op, "value": value}
    if op == "between":
        lo, _sep, hi = value.partition("..")
        cond.update(value=lo, value2=hi)
    return cond


def _check(cond: Any, columns: list[str], info: dict[str, dict[str, Any]], index: int, cat: str) -> dict[str, Any]:
    if isinstance(cond, str):
        cond = parse_condition(cond)
    if not isinstance(cond, dict):
        raise KosmoError("bad_query", "A condition needs field, op and value.", field="c", index=index)
    field, op = str(cond.get("field") or "").strip(), str(cond.get("op") or "").strip()
    value, value2 = str(cond.get("value") or "").strip(), str(cond.get("value2") or "").strip()
    where = {"field": "c", "index": index}
    if field not in columns:
        raise KosmoError("bad_query", f"Unknown column {field!r} for {cat}.", **where)
    if op not in COND_OPS:
        raise KosmoError("bad_query", f"Condition {index + 1}: op must be one of {', '.join(COND_OPS)}.", **where)
    if len(value) > MAX_QUERY or len(value2) > MAX_QUERY:
        raise KosmoError("bad_query", f"Filter values are limited to {MAX_QUERY} characters.", **where)
    kind = info[field]["kind"]
    out: dict[str, Any] = {"field": field, "op": op, "value": value if op in VALUE_OPS else ""}
    if op in VALUE_OPS and not value:
        raise KosmoError("bad_query", f"Condition {index + 1} ({field}): enter a value.", **where)
    if op in NUMERIC_OPS:
        if kind == "text":
            raise KosmoError("bad_query", f"Column {field!r} holds text, so it has no numeric comparison. Use equals "
                                          "or contains.", **where)
        lo = _num(value)
        if lo is None:
            raise KosmoError("bad_query", f"Condition {index + 1} ({field}): {value!r} is not a number.", **where)
        out["lo"] = lo
        if op == "between":
            hi = _num(value2)
            if hi is None:
                raise KosmoError("bad_query", f"Condition {index + 1} ({field}): enter a number for the upper bound.",
                                 **where)
            if hi < lo:
                raise KosmoError("bad_query", f"Condition {index + 1} ({field}): the lower bound is above the upper "
                                              "bound.", **where)
            out.update(hi=hi, value2=value2)
    if op in ("eq", "ne"):
        out["num"] = _num(value) if kind != "text" else None
    return out


def _matches(r: dict[str, str], c: dict[str, Any]) -> bool:
    raw = (r.get(c["field"]) or "").strip()
    op = c["op"]
    if c.get("legacy"):  # the original single filter: raw text semantics, unchanged
        v = c["value"].lower()
        return raw not in ("", "0") if op == "has" else raw.lower() == v if op == "eq" else v in raw.lower()
    if op in ("has", "none"):
        x = _cell_num(raw)
        present = bool(raw) and (x is None or x != 0)
        return present if op == "has" else not present
    if op in ("eq", "ne"):
        x = _cell_num(raw) if c.get("num") is not None else None
        same = x == c["num"] if x is not None else raw.lower() == c["value"].lower()
        return same if op == "eq" else not same
    if op == "contains":
        return c["value"].lower() in raw.lower()
    x = _cell_num(raw)
    if x is None:
        return False
    lo = c["lo"]
    return (x > lo if op == "gt" else x >= lo if op == "gte" else x < lo if op == "lt" else x <= lo if op == "lte"
            else lo <= x <= c["hi"])


def _cond_text(c: dict[str, Any]) -> str:
    op = c["op"]
    if op in ("has", "none"):
        return f"{c['field']} {COND_OPS[op]}"
    if op == "between":
        return f"{c['field']} between {c['value']} and {c['value2']}"
    return f"{c['field']} {COND_OPS[op]} {c['value']}"


def list_rows(catalog: Catalog | None, cat: str, q: str = "", field: str = "", op: str = "", value: str = "",
              page: Any = 1, per_page: Any = DEFAULT_PER_PAGE, conditions: list[Any] | None = None,
              sort: str = "", order: str = "", age: str = "", nation: str = "", role: str = "") -> dict[str, Any]:
    """One bounded page of a category, narrowed by name/id and AND-ed column conditions, sorted by id, name or a column.

    field/op/value is the original single raw-text filter and keeps its meaning; `conditions` adds numeric-aware
    ones. `age` (1-3) narrows units (by nation membership), mercenaries (#eramask) and nations (era); `nation` (a
    catalog nation id, national or none) and `role` narrow units by explicit catalog nation relations."""
    catalog = _need(catalog, cat)
    q = (q or "").strip()
    if len(q) > MAX_QUERY or len(value or "") > MAX_QUERY:
        raise KosmoError("bad_query", f"Search text and filter values are limited to {MAX_QUERY} characters.")
    try:
        page_n = max(1, int(page or 1))
        per = max(1, min(int(per_page or DEFAULT_PER_PAGE), MAX_PER_PAGE))
    except (TypeError, ValueError) as exc:
        raise KosmoError("bad_query", "page and per_page must be whole numbers.") from exc
    rows = catalog.table(cat)
    columns = _columns(catalog, cat)
    field = (field or "").strip()
    op = (op or "").strip() or ("has" if field and not value else "eq" if field else "")
    conds: list[dict[str, Any]] = []
    if field:
        if field not in columns:
            raise KosmoError("bad_query", f"Unknown column {field!r} for {cat}.", field="field")
        if op not in FILTER_OPS:
            raise KosmoError("bad_query", "op must be has, eq or contains.", field="op")
        if op != "has" and not (value or "").strip():
            raise KosmoError("bad_query", "Enter a value for this filter.", field="value")
        conds.append({"field": field, "op": op, "value": (value or "").strip(), "legacy": True})
    extra = list(conditions or [])
    if len(extra) > MAX_CONDITIONS:
        raise KosmoError("bad_query", f"At most {MAX_CONDITIONS} conditions.", field="c")
    sort = (sort or "id").strip()
    order = (order or "asc").strip()
    if sort not in ("id", "name") and sort not in columns:
        raise KosmoError("bad_query", f"Cannot sort {cat} by unknown column {sort!r}.", field="sort")
    if order not in SORT_ORDERS:
        raise KosmoError("bad_query", "order must be asc or desc.", field="order")
    info = column_info(catalog, cat) if extra or sort not in ("id", "name") else {}
    age, nation, role = (str(age or "").strip(), str(nation or "").strip(), str(role or "").strip())
    if (nation or role) and cat != "units":
        raise KosmoError("bad_query", "nation and role filter units only.", field="nation" if nation else "role")
    if age and cat not in ("units", "mercs", "nations"):
        raise KosmoError("bad_query", "age filters units, mercenaries and nations only.", field="age")
    scope = _unit_scope(catalog, age, nation, role) if cat == "units" else None
    age_n = _int(age) if age else None
    if age and cat != "units" and age_n not in AGES:
        raise KosmoError("bad_query", "age must be 1 (Early), 2 (Middle) or 3 (Late).", field="age")
    conds += [_check(c, columns, info, i, cat) for i, c in enumerate(extra)]
    ql = q.lstrip("#").lower()
    want_id = int(ql) if ql.lstrip("-").isdigit() else None
    hits = []
    for r in rows:
        rid = (r.get("id") or "").strip()
        if not rid.lstrip("-").isdigit():
            continue
        if ql:
            hay = (r.get("name") or "").lower()
            if cat == "events":
                hay += " " + (r.get("description") or "").lower()
            if not (want_id is not None and int(rid) == want_id) and ql not in hay:
                continue
        if scope and not _in_scope(int(rid), scope):
            continue
        if age_n and cat == "mercs" and not (_int(r.get("eramask")) or 0) & ERA_BITS[age_n]:
            continue
        if age_n and cat == "nations" and _int(r.get("era")) != age_n:
            continue
        if all(_matches(r, c) for c in conds):
            hits.append(r)
    # Ties keep id order in both directions: stable sorts over the id-ordered list.
    hits.sort(key=lambda r: int(r["id"].strip()))
    desc = order == "desc"
    sort_kind = "number" if sort == "id" else "text" if sort == "name" else info[sort]["kind"]
    if sort == "id":
        if desc:
            hits.reverse()
    elif sort_kind == "text":
        hits.sort(key=lambda r: (r.get(sort) or "").strip().casefold(), reverse=desc)
    else:  # numeric (or entirely blank) column: numbers, blank as 0
        hits.sort(key=lambda r: _cell_num(r.get(sort)) or 0.0, reverse=desc)
    pages = max(1, -(-len(hits) // per))
    page_n = min(page_n, pages)
    start = (page_n - 1) * per
    chunk = hits[start: start + per]
    ctx = {"units": _names(catalog, "units")} if cat == "mercs" else {}
    shown = list(dict.fromkeys([*(c["field"] for c in conds), *([sort] if sort not in ("id", "name") else [])]))
    results = []
    for r in chunk:
        rid = int(r["id"].strip())
        item = {"id": rid, "name": (r.get("name") or "").strip(), **_row_fields(cat, r, ctx),
                "summary": [x for x in _summary(cat, r) if x]}
        if cat == "units":
            item["nations"] = _unit_nations(catalog, rid, scope["age"] if scope else None)
        if field:
            item["filter_value"] = r.get(field)
        if shown:
            item["values"] = {k: r.get(k) or "" for k in shown}
        results.append(item)
    public = [{**{k: c[k] for k in ("field", "op", "value", "value2") if k in c}, "text": _cond_text(c)}
              for c in conds if not c.get("legacy")]
    return {"category": cat, "label": CATS[cat], "total": len(rows), "matches": len(hits), "page": page_n,
            "per_page": per, "pages": pages, "range": [start + 1 if chunk else 0, start + len(chunk)],
            "results": results, "columns": columns,
            "query": q, "filter": {"field": field, "op": op, "value": value} if field else None,
            "conditions": public, "sort": {"key": sort, "order": order, "kind": sort_kind},
            "scope": {"age": age_n, "nation": scope["nation"] if scope else None, "role": scope["role"] if scope else None},
            "semantics": ("Search matches an exact id or text in the name" + (" or description" if cat == "events" else "")
                          + ". Conditions are combined with AND. Numeric comparisons compare numbers, with a blank "
                            "cell counted as 0 (the catalog leaves zero values blank); equals compares numbers on "
                            "numeric columns and text (case-insensitive) otherwise; 'has a value' means non-blank and "
                            "not 0. The single field/op/value filter keeps its raw-text meaning. Raw values are the "
                            "catalog's encoding, not interpreted game values."
                          + (" " + MEMBERSHIP_NOTE if cat == "units" else "")),
            "provenance": provenance(catalog)}


# ---------- filter metadata ----------

PATH_LETTERS = {"F": "Fire", "A": "Air", "W": "Water", "E": "Earth", "S": "Astral", "D": "Death", "N": "Nature",
                "G": "Glamour", "B": "Blood", "H": "Holy"}
# Readable common filters per category: (column, label). Only columns present and non-blank in the catalog are offered.
COMMON: dict[str, tuple[tuple[str, str], ...]] = {
    "units": (("hp", "Hit points"), ("size", "Size"), ("prot", "Protection"), ("mr", "Magic resistance"),
              ("mor", "Morale"), ("str", "Strength"), ("att", "Attack"), ("def", "Defence"), ("prec", "Precision"),
              ("enc", "Encumbrance"), ("ap", "Combat speed"), ("mapmove", "Map move"), ("leader", "Leadership"),
              ("basecost", "Gold cost (raw)"), ("rcost", "Resource cost"), ("holy", "Sacred"), ("flying", "Flying"),
              ("stealthy", "Stealthy"), ("aquatic", "Aquatic"), ("amphibian", "Amphibian"),
              *((k, f"{v} magic") for k, v in PATH_LETTERS.items())),
    "sites": (("path", "Path"), ("level", "Level"), ("rarity", "Rarity"), ("gold", "Gold"), ("res", "Resources"),
              *((k, f"{v} gems") for k, v in PATH_LETTERS.items() if k not in ("B", "H"))),
    "events": (("rarity", "Rarity"),),
    "mercs": (("level", "Level"), ("eramask", "Eras"), ("nrunits", "Number of troops"), ("minpay", "Minimum pay"),
              ("xp", "Experience"), ("randequip", "Random equipment"), ("recrate", "Recruitment rate")),
    "items": (("type", "Type"), ("constlevel", "Construction level"), ("mainpath", "Main path"),
              ("mainlevel", "Main level"), ("secondarypath", "Secondary path")),
    "spells": (("school", "School"), ("researchlevel", "Research level"), ("path1", "Path"),
               ("pathlevel1", "Path level"), ("gemcost", "Gem cost"), ("fatiguecost", "Fatigue cost")),
    "weapons": (("att", "Attack"), ("def", "Defence"), ("len", "Length"), ("nratt", "Attacks"), ("ammo", "Ammo"),
                ("rcost", "Resource cost")),
    "armors": (("type", "Type"), ("def", "Defence"), ("enc", "Encumbrance"), ("rcost", "Resource cost")),
    "nations": (("era", "Era"),),
}
FLAG_FIELDS = {("units", "holy"), ("units", "flying"), ("units", "stealthy"), ("units", "aquatic"),
               ("units", "amphibian")}
CHOICE_FIELDS = {("sites", "path"), ("sites", "rarity"), ("events", "rarity"), ("mercs", "level"),
                 ("mercs", "eramask"), ("mercs", "randequip"), ("items", "type"), ("items", "mainpath"),
                 ("items", "secondarypath"), ("spells", "school"), ("spells", "path1"), ("armors", "type"),
                 ("nations", "era")}


def _choice_labels(cat: str, field: str) -> dict[str, str]:
    from .content import RARITY, SCHOOLS, SPELL_PATHS
    labels: dict[tuple[str, str], Any] = {
        ("mercs", "level"): MERC_LEVELS, ("mercs", "eramask"): ERA_MASKS, ("mercs", "randequip"): RANDEQUIP,
        ("items", "type"): ITEM_TYPES, ("items", "mainpath"): PATH_LETTERS, ("items", "secondarypath"): PATH_LETTERS,
        ("spells", "school"): dict(SCHOOLS), ("spells", "path1"): dict(SPELL_PATHS), ("sites", "rarity"): dict(RARITY),
        ("nations", "era"): {1: "Early era", 2: "Middle era", 3: "Late era"},
    }
    return {str(k): str(v) for k, v in (labels.get((cat, field)) or {}).items()}


# The few everyday filters per category: a list parameter (age, nation, role) or one column condition per choice.
SIMPLE: dict[str, tuple[tuple[str, str], ...]] = {
    "units": (("age", "Age"), ("nation", "Nation"), ("role", "Role"), ("magic", "Magic")),
    "sites": (("path", "Path"), ("rarity", "Rarity")),
    "events": (("rarity", "Rarity"),),
    "mercs": (("age", "Age"), ("level", "Availability")),
    "items": (("type", "Slot"), ("mainpath", "Path"), ("constlevel", "Construction")),
    "spells": (("school", "School"), ("path1", "Path"), ("researchlevel", "Research")),
    "armors": (("type", "Type"),),
    "nations": (("age", "Age"),),
}
MERC_AVAILABILITY = {"0": "Early game", "1": "Later", "2": "Last"}


def _simple(catalog: Catalog, cat: str, info: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    from .content import ARMOR_TYPES, RARITY
    rows = catalog.table(cat)
    out: list[dict[str, Any]] = []
    for key, label in SIMPLE.get(cat, ()):
        if key == "age":
            out.append({"key": key, "label": label, "param": "age",
                        "choices": [{"value": str(k), "label": v} for k, v in AGES.items()]})
        elif key == "nation":
            members = unit_memberships(catalog)
            counts: dict[int, int] = {}
            for ties in members.values():
                for nid in ties:
                    counts[nid] = counts.get(nid, 0) + 1
            nations = sorted(nations_by_age(catalog).values(), key=lambda n: (n["era"], n["name"].casefold()))
            unit_ids = {i for r in rows if (i := _int(r.get("id"))) is not None}
            national = sum(1 for i in unit_ids if members.get(i))
            out.append({"key": key, "label": label, "param": "nation", "special": [
                {"value": "national", "label": "Any nation", "count": national},
                {"value": "none", "label": "No nation", "count": len(unit_ids) - national}],
                "choices": [{"value": str(n["id"]), "label": n["name"], "era": n["era"], "epithet": n["epithet"],
                             "count": counts.get(n["id"], 0)} for n in nations if counts.get(n["id"])]})
        elif key == "role":
            out.append({"key": key, "label": label, "param": "role",
                        "choices": [{"value": k, "label": v} for k, v in UNIT_ROLES.items()]})
        elif key == "magic":
            out.append({"key": key, "label": label, "choices": [
                {"value": k, "label": v, "cond": f"{k}:gt:0", "count": None} for k, v in PATH_LETTERS.items()
                if (info.get(k) or {}).get("kind") == "number"]})
        elif (info.get(key) or {}).get("kind") not in (None, "empty"):
            names = {**_choice_labels(cat, key)}
            if cat == "sites" and key == "rarity":
                names = {str(k): v for k, v in RARITY}
            if cat == "armors" and key == "type":
                names = {str(k): v for k, v in ARMOR_TYPES}
            if cat == "mercs" and key == "level":
                names = MERC_AVAILABILITY
            counts2: dict[str, int] = {}
            for r in rows:
                v = (r.get(key) or "").strip() or ("0" if info[key]["kind"] == "number" else "")
                if v:
                    counts2[v] = counts2.get(v, 0) + 1
            ordered = sorted(counts2, key=lambda v: (_num(v) is None, _num(v) or 0, v))[:40]
            out.append({"key": key, "label": label, "choices": [
                {"value": v, "label": names.get(v) or v, "cond": f"{key}:eq:{v}", "count": counts2[v]}
                for v in ordered]})
    return out


def filter_meta(catalog: Catalog | None, cat: str) -> dict[str, Any]:
    """Common filters (with value choices and ranges taken from the catalog), every column with its kind, and sorts."""
    catalog = _need(catalog, cat)

    def build() -> dict[str, Any]:
        info = column_info(catalog, cat)
        rows = catalog.table(cat)
        common: list[dict[str, Any]] = []
        labels_of: dict[str, str] = {}
        for key, label in COMMON.get(cat, ()):
            ci = info.get(key)
            if not ci or ci["kind"] == "empty":
                continue
            labels_of[key] = label
            kind = ("flag" if (cat, key) in FLAG_FIELDS else "choice" if (cat, key) in CHOICE_FIELDS
                    else "number" if ci["kind"] == "number" else "choice" if ci["distinct"] <= 24 else "text")
            entry: dict[str, Any] = {"field": key, "label": label, "kind": kind, "column_kind": ci["kind"],
                                     "filled": ci["filled"], "min": ci.get("min"), "max": ci.get("max")}
            if kind == "choice":
                names = _choice_labels(cat, key)
                counts: dict[str, int] = {}
                for r in rows:
                    v = (r.get(key) or "").strip()
                    if v:
                        counts[v] = counts.get(v, 0) + 1
                ordered = sorted(counts, key=lambda v: (_num(v) is None, _num(v) or 0, v))
                entry["choices"] = [{"value": v, "label": names.get(v), "count": counts[v]} for v in ordered[:40]]
            common.append(entry)
        columns = [{"key": k, "label": labels_of.get(k), **info[k]} for k in _columns(catalog, cat)
                   if k not in ("id", "name")]
        sorts = [{"key": "id", "label": "Id", "kind": "number"}, {"key": "name", "label": "Name", "kind": "text"},
                 *({"key": c["field"], "label": c["label"], "kind": c["column_kind"]} for c in common
                   if c["column_kind"] == "number" and c["kind"] != "flag")]
        return {"category": cat, "label": CATS[cat], "simple": _simple(catalog, cat, info), "common": common,
                "columns": columns, "sorts": sorts,
                "ops": [{"op": k, "label": v, "numeric": k in NUMERIC_OPS, "needs_value": k in VALUE_OPS}
                        for k, v in COND_OPS.items()],
                "max_conditions": MAX_CONDITIONS, "max_per_page": MAX_PER_PAGE,
                "note": "Choices and ranges are read from this catalog. Blank cells count as 0 in numeric "
                        "conditions. Labels quote the modding manual where one exists; values stay raw."
                        + (" " + MEMBERSHIP_NOTE if cat == "units" else "")}

    return {**catalog.memoized(("inspector-filters", cat), build), "provenance": provenance(catalog)}


# ---------- details ----------

def _raw(r: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in r.items() if k and k != "end" and (v or "").strip() != ""}


def _row(catalog: Catalog, cat: str, ident: int) -> dict[str, str]:
    r = catalog.row(cat, ident)
    if r is None:
        raise KosmoError("object_missing", f"No catalog {CATS[cat].lower()} entry {ident}.")
    return r


def mercs_using(catalog: Catalog, *, unit: int | None = None, item: str | None = None) -> list[dict[str, Any]]:
    if not catalog.has_table("mercs"):
        return []
    out = []
    for r in catalog.table("mercs"):
        mid = _int(r.get("id"))
        if mid is None:
            continue
        roles = []
        if unit is not None:
            if _int(r.get("com")) == unit:
                roles.append("commander")
            if _int(r.get("unit")) == unit:
                roles.append("troop")
        if item is not None and item.strip().lower() in (x.lower() for x in _merc_items(r)):
            roles.append("item")
        if roles:
            out.append({"id": mid, "name": (r.get("name") or "").strip(), "roles": roles})
    return out


def merc_detail(catalog: Catalog, ident: int) -> dict[str, Any]:
    r = _row(catalog, "mercs", ident)
    units = _names(catalog, "units")
    by_name = _items_by_name(catalog)
    lvl, era, rq = _int(r.get("level")), _int(r.get("eramask")), _int(r.get("randequip"))
    labelled = [
        {"key": "bossname", "label": "Boss name", "value": r.get("bossname"), "command": "#bossname"},
        {"key": "nrunits", "label": "Number of troops", "value": r.get("nrunits"), "command": "#nrunits"},
        {"key": "minmen", "label": "Minimum men", "value": r.get("minmen"), "command": "#minmen",
         "note": "Below this many troops, recruitment of new troops starts (manual p.63)."},
        {"key": "minpay", "label": "Minimum pay", "value": r.get("minpay"), "command": "#minpay",
         "note": "Minimum gold the band can be hired for (manual p.63)."},
        {"key": "xp", "label": "Experience", "value": r.get("xp"), "command": "#xp",
         "note": "Starting troop experience; the commander has twice this amount (manual p.63)."},
        {"key": "recrate", "label": "Recruitment rate", "value": r.get("recrate"), "command": "#recrate",
         "note": "100 means one new troop per month (manual p.63)."},
        {"key": "randequip", "label": "Random equipment", "value": r.get("randequip"), "command": "#randequip",
         "meaning": RANDEQUIP.get(rq) if rq is not None else None},
        {"key": "level", "label": "Level", "value": r.get("level"), "command": "#level",
         "meaning": MERC_LEVELS.get(lvl) if lvl is not None else None},
        {"key": "eramask", "label": "Era mask", "value": r.get("eramask"), "command": "#eramask",
         "meaning": ERA_MASKS.get(era) if era is not None else None},
    ]
    return {"category": "mercs", "id": ident, "name": (r.get("name") or "").strip(),
            "commander": _unit_ref(units, r.get("com")), "troop": _unit_ref(units, r.get("unit")),
            "items": [_item_ref(by_name, n) for n in _merc_items(r)], "labelled": labelled,
            "catalog_row": _raw(r), "manual": MANUAL_MERC,
            "note": "Catalog columns com and unit hold monster ids; a mod's #com and #unit take monster names (manual "
                    "p.63). Meanings are quoted from the manual; values are the catalog's.",
            "provenance": provenance(catalog)}


def _tokens(raw: str, section: str, catalog: Catalog, units: dict[int, str]) -> list[dict[str, Any]]:
    from .manual_commands import commands
    manual = commands("event")
    out = []
    for part in (raw or "").split("|"):
        part = part.strip()
        if not part:
            continue
        bits = part.split()
        name, args = bits[0], bits[1:]
        tok: dict[str, Any] = {"raw": part, "token": name, "args": args, "section": section}
        spec = manual.get(name.lower())
        if spec:
            tok["manual"] = {"command": "#" + spec["command"], "signature": spec.get("signature"),
                             "summary": spec.get("summary"), "page": (spec.get("source") or {}).get("page"),
                             "document": (spec.get("source") or {}).get("document")}
            specs = spec.get("args") or []
            if specs and specs[0].get("type") in ("mon", "monid") and args:
                ref = _unit_ref(units, args[0])
                if ref and ref["in_catalog"]:
                    tok["unit"] = ref
        out.append(tok)
    return out


def event_detail(catalog: Catalog, ident: int) -> dict[str, Any]:
    r = _row(catalog, "events", ident)
    units = _names(catalog, "units")
    return {"category": "events", "id": ident, "name": (r.get("name") or "").strip(),
            "name_note": "The catalog's event name is the first 30 characters of the description.",
            "rarity": r.get("rarity"), "description": r.get("description") or "",
            "requirements": _tokens(r.get("requirements") or "", "requirement", catalog, units),
            "effects": _tokens(r.get("effects") or "", "effect", catalog, units),
            "catalog_row": _raw(r),
            "note": "Requirements and effects are the catalog's raw tokens, split on '|' and shown as recorded "
                    "(including hex codes). A token whose name equals an Event Modding Manual command shows that "
                    "entry for reference; the browser does not interpret what any token does in game.",
            "provenance": provenance(catalog)}


def item_detail(catalog: Catalog, ident: int) -> dict[str, Any]:
    r = _row(catalog, "items", ident)
    labelled = []
    for key, label in (("type", "Type"), ("constlevel", "Construction level"), ("mainpath", "Main path"),
                       ("mainlevel", "Main level"), ("secondarypath", "Secondary path"),
                       ("secondarylevel", "Secondary level"), ("weapon", "Weapon id"), ("armor", "Armour id")):
        v = (r.get(key) or "").strip()
        if v:
            labelled.append({"key": key, "label": label, "value": v,
                             "meaning": ITEM_TYPES.get(v) if key == "type" else None})
    name = (r.get("name") or "").strip()
    return {"category": "items", "id": ident, "name": name, "labelled": labelled, "catalog_row": _raw(r),
            "icon": {"url_tail": f"item-icons/{ident}.png"} if 0 < ident < 10000 else None,
            "mercs": mercs_using(catalog, item=name),
            "note": "Raw catalog columns. Effects are listed as the catalog's column names and values, not "
                    "interpreted game values.", "provenance": provenance(catalog)}


def detail(catalog: Catalog | None, slug: str, cat: str, ident: int) -> dict[str, Any]:
    catalog = _need(catalog, cat)
    if cat == "units":
        from .browse import catalog_unit_view
        out = catalog_unit_view(catalog, slug, ident)
        return {**out, "category": "units", "mercs": mercs_using(catalog, unit=ident),
                "nations": unit_nation_ties(catalog, ident), "inspector_provenance": provenance(catalog)}
    if cat == "mercs":
        return merc_detail(catalog, ident)
    if cat == "events":
        return event_detail(catalog, ident)
    if cat == "items":
        return item_detail(catalog, ident)
    if cat in ("spells", "sites", "weapons", "armors"):
        from .content import reference_detail
        return {**reference_detail(catalog, cat, ident), "provenance": provenance(catalog)}
    r = _row(catalog, cat, ident)
    return {"category": cat, "id": ident, "name": (r.get("name") or "").strip(), "catalog_row": _raw(r),
            "labelled": [{"key": k, "label": k, "value": r.get(k)} for k in ALL_CATEGORIES[cat][1] if r.get(k)],
            "provenance": provenance(catalog)}
