"""Bounded authoring of magic sites, national spells (including summons), weapons, armour and nation heroes.

Shared by the web server, the CLI and the MCP server. Every write follows the author.py transaction: project lock,
expected SHA-256 of the .dm, id reservation from the shared allocator (sites, weapons, armour; #newspell takes no
number in the manual), a candidate that is re-parsed and re-read, and the core backup + atomic replace.

Edits touch only the managed commands of one block: an existing statement has only its own span rewritten (comments,
spacing, unknown commands and line endings around it are kept), a removed statement deletes its line (or only the
statement when other text shares the line), and new statements go just before #end. The candidate must keep every
byte outside the block, add no syntax problems, pass the curated argument checks where the registry covers the
command, and read back the requested values.

Command syntax and ranges come from the Dominions 6 Modding Manual (.local/references/dom6modman.txt). Where the
manual gives no range a "sanity bound" is used and labelled. Spell effects are never invented: a new spell always
starts from #copyspell of a catalog spell, and the monster of a summon is changed only when the template's effect is
one the manual documents as "damage = monster number".
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from pathlib import Path
from typing import Any

from .author import _diff, _end_pos, _nl, _preview_flag, _sha, _text, _transaction
from .browse import build_project_model
from .catalog import Catalog, search
from .dmparse import Block, Statement, block_id, block_name, parse
from .errors import KosmoError
from .project import open_project, project_lock, read_dm, resolve_dm_target, sha256_bytes, write_dm_locked
from .validate import Report, _check_statement

KINDS = ("sites", "spells", "weapons", "armors")
CAT = {"sites": "sites", "spells": "spells", "weapons": "weapons", "armors": "armors"}
ALLOC = {"sites": "site", "weapons": "weapon", "armors": "armor"}
OPENERS = {"sites": ("newsite", "selectsite"), "spells": ("newspell", "selectspell"),
           "weapons": ("newweapon", "selectweapon"), "armors": ("newarmor", "selectarmor")}
CONTEXT = {"sites": "site", "spells": "spell", "weapons": "weapon", "armors": "armor"}
COPY_CMD = {"sites": "copysite", "spells": "copyspell", "weapons": "copyweapon", "armors": "copyarmor"}
MAN = "Dominions 6 Modding Manual"
SPELL_PATHS = [(-1, "None"), (0, "Fire"), (1, "Air"), (2, "Water"), (3, "Earth"), (4, "Astral"), (5, "Death"),
               (6, "Nature"), (7, "Glamour"), (8, "Blood"), (9, "Priest")]
SITE_PATHS = [(0, "Fire"), (1, "Air"), (2, "Water"), (3, "Earth"), (4, "Astral"), (5, "Death"), (6, "Nature"),
              (7, "Glamour"), (8, "Blood"), (9, "Holy")]
SCHOOLS = [(-1, "Cannot be researched"), (0, "Conjuration"), (1, "Alteration"), (2, "Evocation"),
           (3, "Construction"), (4, "Enchantment"), (5, "Thaumaturgy"), (6, "Blood"), (7, "Divine")]
RARITY = [(0, "Common"), (1, "Uncommon"), (2, "Rare"), (5, "Never random"), (11, "Throne level 1"),
          (12, "Throne level 2"), (13, "Throne level 3")]
ARMOR_TYPES = [(4, "Shield"), (5, "Body armour"), (6, "Helmet"), (9, "Barding")]
# Effects the manual documents with "damage = monster number" (Combat / Ritual spell effects tables).
SUMMON_EFFECTS = {1: "Summon monster", 31: "Summon independent", 43: "Border summon",
                  126: "Border summon independent", 10001: "Summon monster (ritual)",
                  10021: "Summon commander (ritual)", 10037: "Farsummon (ritual)",
                  10038: "Indep. farsummon (ritual)"}
MAX_SPELL_RESTRICTED = 12
MAX_LIST = 12


def _f(key: str, label: str, typ: str, cmd: str, src: str, lo: int | None = None, hi: int | None = None,
       choices: list[tuple[int, str]] | None = None, prefix: tuple[int, ...] = (), multi: bool = False,
       sanity: bool = False, help: str = "") -> dict[str, Any]:
    return {"key": key, "label": label, "type": typ, "cmd": cmd, "prefix": prefix, "multi": multi,
            "min": lo, "max": hi, "choices": [{"value": v, "label": t} for v, t in choices] if choices else None,
            "source": f"{MAN}, {src}" + ("; range is a Kosmokrator sanity bound, not from the manual" if sanity else ""),
            "help": help}


FIELDS: dict[str, list[dict[str, Any]]] = {
    "sites": [
        _f("name", "Name", "text", "name", "Basic Site Modding #name (p.37)"),
        _f("path", "Path", "choice", "path", "#path (p.37)", choices=SITE_PATHS),
        _f("level", "Level (magic needed to find)", "int", "level", "#level 0-4 (p.38)", 0, 4,
           help="0 is discovered automatically."),
        _f("rarity", "Rarity", "choice", "rarity", "#rarity (p.38)", choices=RARITY),
        _f("loc", "Locmask", "int", "loc", "#loc (p.37), Magic site locmasks table", 0, 32767, sanity=True,
           help="Sum of terrain bits: 735 any land, 288 any sea, 1023 anywhere, +16384 unique."),
        _f("gems", "Gem income", "gems", "gems", "#gems <path 0-8> <amount> (p.38)", 1, 10, multi=True, sanity=True,
           help="Amount upper bound is a sanity bound."),
        _f("gold", "Gold", "int", "gold", "#gold (p.38)", -1000, 1000, sanity=True),
        _f("res", "Resources", "int", "res", "#res (p.38)", -1000, 1000, sanity=True),
        _f("homemon", "Capital-only troops (#homemon)", "monsters", "homemon", "#homemon (p.38)", multi=True),
        _f("homecom", "Capital-only commanders (#homecom)", "monsters", "homecom", "#homecom (p.38)", multi=True),
        _f("summon", "Summonable by a mage of the site's path (#summon)", "monsters", "summon", "#summon (p.38)",
           multi=True),
    ],
    "spells": [
        _f("name", "Name", "text", "name", "#name (p.50)", help="Set before #descr: changing the name removes "
                                                                "the description."),
        _f("descr", "Description", "text", "descr", "#descr (p.50)"),
        _f("details", "Details (yellow text)", "text", "details", "#details (p.50)"),
        _f("school", "School", "choice", "school", "#school, Magic schools table (p.50)", choices=SCHOOLS),
        _f("researchlevel", "Research level", "int", "researchlevel", "#researchlevel 0-9 (p.50)", 0, 9),
        _f("path0", "First path", "choice", "path", "#path <reqnr> <path>, Magic path numbers for spells (p.50)",
           choices=SPELL_PATHS, prefix=(0,)),
        _f("pathlevel0", "First path level", "int", "pathlevel", "#pathlevel <reqnr> <level> (p.50)", 0, 10,
           prefix=(0,), sanity=True),
        _f("path1", "Second path", "choice", "path", "#path 1 <path> (p.50)", choices=SPELL_PATHS, prefix=(1,)),
        _f("pathlevel1", "Second path level", "int", "pathlevel", "#pathlevel 1 <level> (p.50)", 0, 10, prefix=(1,),
           sanity=True),
        _f("fatiguecost", "Fatigue / gem cost", "int", "fatiguecost", "#fatiguecost (p.50)", 0, 10000, sanity=True,
           help="Every 100 raises the gem or blood slave cost by one; rituals set their gem cost this way."),
        _f("damage", "Damage (raw)", "int", "damage", "#damage (p.51)", -100000, 100000, sanity=True,
           help="Meaning depends on the copied effect. For a summon use 'Summoned monster' instead."),
        _f("summon_monster", "Summoned monster", "monster", "damage", "#damage = monster number for the summon "
           "effects of the Combat/Ritual spell effects tables (p.51)",
           help="Only for templates whose effect the manual documents as a monster summon."),
        _f("nreff", "Number of effects", "int", "nreff", "#nreff (p.51)", 1, 5000, sanity=True,
           help="For summons: how many creatures. +1000/2000/3000 or +500 scale with caster level."),
        _f("restricted", "Restricted to nation", "nation", "restricted", "#restricted (p.53)", multi=False,
           help="National spell: only this nation can research it."),
    ],
    "weapons": [
        _f("name", "Name", "text", "name", "#name (p.6)"),
        _f("dmg", "Damage", "int", "dmg", "#dmg (p.6)", -50, 200, sanity=True),
        _f("att", "Attack", "int", "att", "#att (p.6)", -20, 20, sanity=True),
        _f("def", "Defence", "int", "def", "#def (p.6)", -20, 20, sanity=True),
        _f("len", "Length", "int", "len", "#len 0 (fist) - 5 (pike) (p.6)", 0, 5),
        _f("nratt", "Attacks per round", "int", "nratt", "#nratt (p.6); -2/-3 = every 2nd/3rd round", -3, 10,
           sanity=True),
        _f("range", "Range (makes it a missile weapon)", "int", "range", "#range (p.7)", 1, 200, sanity=True,
           help="Turns the weapon into a missile weapon that cannot be used in melee."),
        _f("ammo", "Ammunition", "int", "ammo", "#ammo (p.7): default 12, normal max 30, >1000 fatigue cost",
           0, 2000, sanity=True),
        _f("rcost", "Resource cost", "int", "rcost", "#rcost (p.7)", 0, 200, sanity=True),
        _f("twohanded", "Two-handed", "flag", "twohanded", "#twohanded (p.6)"),
    ],
    "armors": [
        _f("name", "Name", "text", "name", "#name (p.12)"),
        _f("type", "Type", "choice", "type", "#type (p.12)", choices=ARMOR_TYPES),
        _f("prot", "Protection", "int", "prot", "#prot (p.12)", 0, 50, sanity=True),
        _f("def", "Defence (parry for shields)", "int", "def", "#def (p.12)", -20, 20, sanity=True),
        _f("enc", "Encumbrance", "int", "enc", "#enc (p.12)", 0, 20, sanity=True),
        _f("rcost", "Resource cost", "int", "rcost", "#rcost (p.12)", 0, 200, sanity=True),
        _f("magicarmor", "Magic armour", "flag", "magicarmor", "#magicarmor (p.12)"),
        _f("ironarmor", "Iron", "flag", "ironarmor", "#ironarmor (p.12)"),
        _f("woodenarmor", "Wooden", "flag", "woodenarmor", "#woodenarmor (p.12)"),
    ],
}
NOTES = {
    "sites": ["A magic site may hold at most 15 different attributes (manual p.37); this is not counted here.",
              "#homemon/#homecom only matter on a nation's start sites (capital)."],
    "spells": ["#newspell takes no number; Kosmokrator identifies named project spells by a stable name fingerprint. Other "
               "definitions must refer to them by name.",
               "A new spell copies a catalog spell with #copyspell; its effect, area, range and sounds stay the "
               "template's. Kosmokrator never sets #effect.",
               "Spell ids: the spell section says 1300-3999, the Modding Number Limits table says 2000+ of 0-7999."],
    "weapons": ["The manual says both '#name must be the first command' and '#copyweapon ... should be the first "
                "command after #newweapon'. Kosmokrator writes #copyweapon first, then #name, so the copy cannot "
                "overwrite the name; check in game."],
    "armors": ["The #newarmor text says 300-999; the Modding Number Limits table says 400+ of 0-1999. Kosmokrator "
               "allocates 400-1999.",
               "Same #name/#copyarmor ordering conflict as weapons: #copyarmor is written first."],
}


# ---------- statement helpers ----------
def _matches(st: Statement, spec: dict[str, Any]) -> bool:
    if st.command != spec["cmd"]:
        return False
    pre = spec["prefix"]
    return len(st.args) >= len(pre) and all(st.args[i].kind == "int" and st.args[i].value == v
                                            for i, v in enumerate(pre))


def _value(st: Statement, spec: dict[str, Any]) -> Any:
    args = st.args[len(spec["prefix"]):]
    if spec["type"] == "flag":
        return True
    if spec["type"] == "gems":
        return {"path": args[0].value if args else None, "amount": args[1].value if len(args) > 1 else None}
    if not args:
        return None
    return args[0].value


def _render(spec: dict[str, Any], v: Any) -> str:
    pre = " ".join(str(p) for p in spec["prefix"])
    pre = pre + " " if pre else ""
    if spec["type"] == "flag":
        return f"#{spec['cmd']}"
    if spec["type"] == "text":
        return f'#{spec["cmd"]} {pre}"{v}"'
    if spec["type"] == "gems":
        return f"#{spec['cmd']} {v['path']} {v['amount']}"
    return f"#{spec['cmd']} {pre}{v}"


def _live(b: Block, spec: dict[str, Any], specs: list[dict[str, Any]]) -> list[Statement]:
    resets = {"clear", "copyspell", "copyweapon", "copyarmor", "copysite"}
    if b.context == "nation":
        resets = {"clearnation"}
    last_reset = max((s.start for s in b.statements if s.command in resets), default=-1)
    out = [s for s in b.statements if _matches(s, spec)]
    if spec["key"] == "damage" or spec["key"] == "summon_monster":
        out = [s for s in b.statements if s.command == "damage"]
    return [s for s in out if s.start > last_reset]


def _check_int(v: Any, spec: dict[str, Any], field: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise KosmoError("bad_value", f"{spec['label']}: whole number expected.", field=field)
    if spec.get("choices") and v not in {c["value"] for c in spec["choices"]}:
        raise KosmoError("bad_value", f"{spec['label']}: choose one of the listed values.", field=field)
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None and not lo <= v <= hi:
        raise KosmoError("bad_value", f"{spec['label']} must be {lo}-{hi}" +
                         (" (sanity bound)." if "sanity" in spec["source"] else " (manual range)."), field=field)
    return v


# ---------- model helpers ----------
def _project_monsters(m: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {x["id"]: x for x in m["monsters"] if x.get("new") and isinstance(x.get("id"), int)}


def _monster_ok(m: dict[str, Any], catalog: Catalog | None, mid: Any, field: str, project_only: bool = False) -> int:
    if isinstance(mid, bool) or not isinstance(mid, int):
        raise KosmoError("bad_value", "Choose a monster by number.", field=field)
    if mid in _project_monsters(m):
        return mid
    if not project_only and catalog is not None and catalog.row("units", mid) is not None:
        return mid
    raise KosmoError("bad_value", f"Monster {mid} is not a project #newmonster" +
                     ("" if project_only else " or a catalog unit") + ".", field=field)


def _normalize(kind: str, key: str, v: Any, m: dict[str, Any], catalog: Catalog | None) -> Any:
    spec = next((s for s in FIELDS[kind] if s["key"] == key), None)
    if spec is None:
        raise KosmoError("bad_request", f"Unknown field {key!r} for {kind}.", field=key)
    if v is None:
        return None
    t = spec["type"]
    if t == "text":
        return _text({key: v}, key, True, "descr" if key in ("descr", "details") else "name")
    if t == "flag":
        if not isinstance(v, bool):
            raise KosmoError("bad_value", f"{spec['label']}: true or false.", field=key)
        return v
    if t in ("int", "choice"):
        return _check_int(v, spec, key)
    if t == "monster":
        return _monster_ok(m, catalog, v, key)
    if t == "nation":
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 499:
            raise KosmoError("bad_value", "Choose a nation number 0-499.", field=key)
        known = {n.get("id") for n in m["nations"]}
        if v not in known and (catalog is None or catalog.row("nations", v) is None):
            raise KosmoError("bad_value", f"Nation {v} is neither a project nation nor a catalog nation.", field=key)
        return v
    if t == "monsters":
        if not isinstance(v, list) or len(v) > MAX_LIST or len(set(map(repr, v))) != len(v):
            raise KosmoError("bad_value", f"{spec['label']}: at most {MAX_LIST} different monsters.", field=key)
        return [_monster_ok(m, catalog, x, key) for x in v]
    if t == "gems":
        if not isinstance(v, list) or len(v) > 9:
            raise KosmoError("bad_value", "Gems: at most 9 entries.", field=key)
        out, seen = [], set()
        for g in v:
            if not isinstance(g, dict) or set(g) != {"path", "amount"}:
                raise KosmoError("bad_value", "Each gem entry needs path and amount.", field=key)
            p = g["path"]
            if isinstance(p, bool) or not isinstance(p, int) or not 0 <= p <= 8 or p in seen:
                raise KosmoError("bad_value", "Gem path must be 0-8 (manual), each path once.", field=key)
            seen.add(p)
            out.append({"path": p, "amount": _check_int(g["amount"], spec, key)})
        return out
    raise KosmoError("internal", f"Unhandled field type {t}.")


def _spell_template(catalog: Catalog | None, sid: int) -> dict[str, Any]:
    if catalog is None:
        raise KosmoError("catalog_missing", "No game-data catalog: spell templates cannot be checked.")
    row = catalog.row("spells", sid)
    if row is None:
        raise KosmoError("bad_value", f"Spell {sid} is not in the catalog.", field="template")
    effects = _effects_for(catalog, row)
    eff = effects[0] if effects else None
    summon = None
    if eff is not None:
        num = _int(eff.get("effect_number"))
        code = (num or 0) + (10000 if (eff.get("ritual") or "").strip() == "1" and num is not None and num < 10000 else 0)
        arg = _int(eff.get("raw_argument"))
        if code in SUMMON_EFFECTS and arg is not None and arg > 0:
            mon = catalog.row("units", arg)
            summon = {"effect": code, "effect_label": SUMMON_EFFECTS[code], "monster_id": arg,
                      "monster_name": mon.get("name") if mon else None}
    return {"id": sid, "name": row.get("name"), "row": dict(row), "effects": effects, "summon": summon}


def _int(s: Any) -> int | None:
    s = (s or "").strip() if isinstance(s, str) else s
    if isinstance(s, int):
        return s
    return int(s) if isinstance(s, str) and s.lstrip("-").isdigit() else None


def _effects_for(catalog: Catalog, row: dict[str, str]) -> list[dict[str, str]]:
    rid = (row.get("effect_record_id") or "").strip()
    try:
        tab = catalog._effects  # type: ignore[attr-defined]
    except AttributeError:
        from .catalog import _read_table
        path = catalog.gamedata / "effects_spells.csv"
        tab = _read_table(path) if path.is_file() else []
        catalog._effects = tab  # type: ignore[attr-defined]
    return [dict(r) for r in tab if (r.get("record_id") or "").strip() == rid][:5]


# ---------- block lookup ----------
def _blocks(pr: Any, kind: str) -> list[Block]:
    return [b for b in pr.blocks if b.opener.command in OPENERS[kind]]


def _key(kind: str, b: Block) -> str:
    if kind == "spells":
        if b.opener.command == "selectspell" and isinstance(block_id(b), int):
            return f"spell-id:{block_id(b)}"
        name = block_name(b)
        return "spell-name:" + hashlib.sha256(name.lower().encode()).hexdigest() if name else f"line:{b.opener.line}"
    return str(block_id(b))


def _find(pr: Any, kind: str, key: Any, text: str) -> Block:
    if not isinstance(key, str) or not re.fullmatch(r"(?:line:|spell-id:)?\d{1,6}|spell-name:[a-f0-9]{64}", key):
        raise KosmoError("bad_request", "target must be an item key from the list.", field="target")
    hits = [b for b in _blocks(pr, kind) if _key(kind, b) == key]
    if len(hits) != 1:
        raise KosmoError("object_missing" if not hits else "ambiguous_block",
                         f"Expected exactly one block for {key}, found {len(hits)}. Reload the list.",
                         lines=[b.opener.line for b in hits])
    b = hits[0]
    if kind == "spells" and key.startswith("line:"):
        raise KosmoError("not_editable", "Name this spell through the source patch tool before editing it here.")
    if b.end is None or text[text.rfind("\n", 0, b.end.start) + 1:b.end.start].strip():
        raise KosmoError("not_editable", "Block is not closed by #end on its own line.", lines=[b.opener.line])
    if kind != "spells" and not isinstance(block_id(b), int):
        raise KosmoError("not_editable", "Only blocks with a numeric id can be edited here.", lines=[b.opener.line])
    return b


def _item(kind: str, b: Block, text: str, lines: list[str], catalog: Catalog | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    value_lines: dict[str, int] = {}
    managed_ids: set[int] = set()
    blocked = None
    for spec in FIELDS[kind]:
        if spec["key"] == "summon_monster":
            continue
        sts = _live(b, spec, FIELDS[kind])
        managed_ids.update(id(s) for s in sts)
        if spec["multi"]:
            values[spec["key"]] = [_value(s, spec) for s in sts]
            if sts:
                value_lines[spec["key"]] = sts[0].line
        elif sts:
            values[spec["key"]] = _value(sts[-1], spec)
            value_lines[spec["key"]] = sts[-1].line
            if len(sts) > 1:
                blocked = f"#{spec['cmd']} appears {len(sts)} times; fix the source first."
    cp = [s for s in b.statements if s.command == COPY_CMD[kind]]
    template = None
    last_clear = max((s.start for s in b.statements if s.command == "clear"), default=-1)
    if cp and cp[-1].args and cp[-1].start > last_clear:
        tid = cp[-1].args[0].value
        row = catalog.row(CAT[kind], tid) if (catalog and isinstance(tid, int)) else None
        template = {"source": "catalog" if row else ("project" if isinstance(tid, int) else "name"), "id": tid,
                    "name": row.get("name") if row else None, "line": cp[-1].line,
                    "catalog_row": dict(row) if row else None}
        if kind == "spells" and isinstance(tid, int) and catalog is not None and row is not None:
            t = _spell_template(catalog, tid)
            template["summon"] = t["summon"]
            template["effects"] = t["effects"]
            if any(s.command == "effect" and s.start > cp[-1].start for s in b.statements):
                template["summon"] = None
                template["note"] = "An authored #effect overrides the copied template; use raw fields with care."
    managed_cmds = {s["cmd"] for s in FIELDS[kind]} | {COPY_CMD[kind], "end"}
    unmanaged = [{"line": s.line, "raw": s.raw} for s in b.statements if id(s) not in managed_ids
                 and s.command not in managed_cmds]
    if kind == "spells" and len([s for s in b.statements if s.command == "path"]) > len(
            [s for s in b.statements if _matches(s, FIELDS["spells"][5]) or _matches(s, FIELDS["spells"][7])]):
        blocked = blocked or "A #path line has an unexpected requirement number."
    end_line = b.end.line if b.end else b.opener.line
    ident = block_id(b)
    return {"key": _key(kind, b), "id": ident if isinstance(ident, int) else None,
            "selector": ident if isinstance(ident, str) else None, "new": b.new,
            "name": values.get("name") or (template or {}).get("name") or block_name(b), "line": b.opener.line, "end_line": end_line,
            "values": values, "value_lines": value_lines, "template": template, "unmanaged": unmanaged,
            "source_text": "\n".join(lines[b.opener.line - 1:end_line]), "first_line": b.opener.line,
            "editable": blocked is None and b.end is not None and not (kind == "spells" and _key(kind, b).startswith("line:")) and (kind == "spells" or isinstance(ident, int)),
            "blocked_reason": ("Spell has no stable name or numeric selector; name it through a source patch first." if kind == "spells" and _key(kind, b).startswith("line:") else blocked) if b.end is not None else "Block is not closed by #end."}


def content_state(workspace: Path, slug: str, kind: str, catalog: Catalog | None) -> dict[str, Any]:
    """Read-only list of project blocks of one kind with their managed values, template and unmanaged lines."""
    if kind not in KINDS:
        raise KosmoError("bad_kind", f"kind must be one of {', '.join(KINDS)}.")
    project = open_project(workspace, slug)
    path = resolve_dm_target(project, None)
    data, text, _enc = read_dm(path)
    pr = parse(text)
    lines = text.splitlines()
    m = build_project_model(workspace, slug, catalog)
    items = [_item(kind, b, text, lines, catalog) for b in _blocks(pr, kind)]
    keys = [item["key"] for item in items]
    for item in items:
        if keys.count(item["key"]) > 1:
            item["editable"] = False
            item["blocked_reason"] = "Multiple definitions share this identity; resolve the source ambiguity first."
    fields = [{k: v for k, v in s.items() if k not in ("cmd", "prefix")} | {"command": f"#{s['cmd']}"}
              for s in FIELDS[kind]]
    return {"kind": kind, "sha256": sha256_bytes(data), "dm": project.rel(path), "fields": fields, "items": items,
            "options": _options(m), "template_search": f"/api/projects/{slug}/reference?cat={CAT[kind]}&q=",
            "notes": NOTES[kind],
            "limitations": ["Only the listed commands are editable; other lines are kept verbatim and listed as "
                            "not modelled.",
                            "Template values are raw catalog columns of the copied object, not effective in-game "
                            "values after this mod.",
                            "Static checks only: nothing here proves the mod loads or is balanced."]}


def _options(m: dict[str, Any]) -> dict[str, Any]:
    return {"monsters": [{"id": x["id"], "name": x.get("name"), "role": x.get("role")}
                         for x in m["monsters"] if x.get("new") and isinstance(x.get("id"), int)],
            "nations": [{"id": n["id"], "name": n.get("name")} for n in m["nations"] if isinstance(n.get("id"), int)]}


# ---------- block edit engine ----------
def _line_span(text: str, st: Statement) -> tuple[int, int]:
    ls = text.rfind("\n", 0, st.start) + 1
    le = text.find("\n", st.end)
    le = len(text) if le == -1 else le + 1
    if text[ls:st.start].strip() or text[st.end:le].strip():
        return st.start, st.end
    return ls, le


def _plan(text: str, b: Block, kind: str, specs: list[dict[str, Any]], values: dict[str, Any]
          ) -> tuple[list[tuple[int, int, str]], list[dict[str, Any]]]:
    nl = _nl(text)
    end = _end_pos(text, b)
    spans: list[tuple[int, int, str]] = []
    appends: list[str] = []
    changes: list[dict[str, Any]] = []
    for spec in specs:
        if spec["key"] not in values:
            continue
        want = values[spec["key"]]
        sts = _live(b, spec, specs)
        if spec["multi"]:
            want_list = list(want or [])
            for i, w in enumerate(want_list):
                new = _render(spec, w)
                if i < len(sts):
                    if sts[i].raw.strip() != new:
                        spans.append((sts[i].start, sts[i].end, new))
                        changes.append({"field": spec["key"], "action": "replace", "before": sts[i].raw.strip(),
                                        "after": new, "line": sts[i].line})
                else:
                    appends.append(new)
                    changes.append({"field": spec["key"], "action": "add", "before": None, "after": new,
                                    "line": None})
            for st in sts[len(want_list):]:
                a, z = _line_span(text, st)
                spans.append((a, z, ""))
                changes.append({"field": spec["key"], "action": "remove", "before": st.raw.strip(), "after": None,
                                "line": st.line})
            continue
        if len(sts) > 1:
            raise KosmoError("edit_blocked", f"#{spec['cmd']} appears {len(sts)} times in this block; fix the "
                                             "source first.", field=spec["key"], lines=[s.line for s in sts])
        cur = sts[0] if sts else None
        if want is None or want is False:
            if cur is not None:
                a, z = _line_span(text, cur)
                spans.append((a, z, ""))
                changes.append({"field": spec["key"], "action": "remove", "before": cur.raw.strip(), "after": None,
                                "line": cur.line})
            continue
        new = _render(spec, want)
        if cur is None:
            appends.append(new)
            changes.append({"field": spec["key"], "action": "add", "before": None, "after": new, "line": None})
        elif cur.raw.strip() != new:
            spans.append((cur.start, cur.end, new))
            changes.append({"field": spec["key"], "action": "replace", "before": cur.raw.strip(), "after": new,
                            "line": cur.line})
    if appends:
        spans.append((end, end, "".join(a + nl for a in appends)))
    return spans, changes


def _apply_spans(text: str, spans: list[tuple[int, int, str]]) -> str:
    out = text
    last = None
    for a, z, rep in sorted(spans, key=lambda s: (s[0], s[1]), reverse=True):
        if last is not None and z > last:
            raise KosmoError("internal", "Overlapping edits; nothing was written.")
        out = out[:a] + rep + out[z:]
        last = a
    return out


def _verify(text: str, cand: str, kind: str, key: str, b: Block, specs: list[dict[str, Any]],
            values: dict[str, Any], rel: str, finder: Any) -> None:
    """Bytes outside the block are identical, no new syntax problems, curated checks pass, values read back."""
    a = b.opener.start
    z = b.end.end  # type: ignore[union-attr]
    if not (cand[:a] == text[:a] and cand.endswith(text[z:])):
        raise KosmoError("preflight_failed", "Internal check: text outside the block would change; nothing written.")
    pr0, pr1 = parse(text), parse(cand)
    if len(pr1.issues) != len(pr0.issues):
        raise KosmoError("preflight_failed", "The edit would add syntax problems; nothing was written.")
    nb = finder(pr1)
    rep = Report()
    cmds = {s["cmd"] for s in specs}
    for st in nb.statements:
        if st.command in cmds:
            _check_statement(nb.context, st, rep, rel, [], [])
    errs = rep.of("error")
    if errs:
        raise KosmoError("preflight_failed", "Generated commands fail the curated argument checks.",
                         problems=[i["message"] for i in errs][:10])
    for spec in specs:
        if spec["key"] not in values:
            continue
        sts = _live(nb, spec, specs)
        got: Any = [_value(s, spec) for s in sts] if spec["multi"] else (_value(sts[-1], spec) if sts else None)
        want = values[spec["key"]]
        if spec["type"] == "flag":
            got, want = bool(sts), bool(want)
        if spec["multi"]:
            want = list(want or [])
        if got != want:
            raise KosmoError("preflight_failed", f"Read-back of {spec['label']} does not match; nothing was written.",
                             field=spec["key"])


def _write(workspace: Path, slug: str, sha: str, preview: bool, mutate: Any) -> dict[str, Any]:
    project = open_project(workspace, slug)
    with project_lock(project) if not preview else contextlib.nullcontext():
        path = resolve_dm_target(project, None)
        data, text, enc = read_dm(path)
        if sha256_bytes(data).lower() != sha:
            raise KosmoError("sha_mismatch", "The .dm changed since this page loaded. Reload; your form values are "
                                             "kept.", expected=sha, actual=sha256_bytes(data))
        rel = project.rel(path)
        cand, info = mutate(text, rel)
        try:
            new_data = cand.encode(enc)
        except UnicodeEncodeError as exc:
            raise KosmoError("encoding", f"The new text cannot be written in the file's {enc} encoding.",
                             field="name") from exc
        out = {"project": slug, "preview": preview, "diff": _diff(text, cand, rel), "before_sha256": sha256_bytes(data),
               **info}
        if not info.get("changes"):
            return {**out, "written": False, "note": "No changes: the requested values are already in the file."}
        if preview:
            return {**out, "written": False, "note": "Preview only; nothing was written."}
        backup = write_dm_locked(project, path, data, new_data)
    return {**out, "written": True, "after_sha256": sha256_bytes(new_data), "backup": backup}


# ---------- public operations ----------
def save_content(workspace: Path, slug: str, kind: str, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    """Create (mode new) or edit (mode edit) one site, spell, weapon or armour. Preview first, then save."""
    if kind not in KINDS:
        raise KosmoError("bad_kind", f"kind must be one of {', '.join(KINDS)}.")
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "preview", "mode", "target", "template",
                                                  "values"}:
        raise KosmoError("bad_request", "Body must be {expected_sha256, preview, mode, target?, template?, values}.")
    sha, preview = _sha(body), _preview_flag(body)
    mode = body.get("mode")
    if mode not in ("new", "edit"):
        raise KosmoError("bad_request", "mode must be 'new' or 'edit'.")
    raw_values = body.get("values") or {}
    if not isinstance(raw_values, dict) or len(raw_values) > 30:
        raise KosmoError("bad_request", "values must be an object of field: value.")
    m = build_project_model(workspace, slug, catalog)
    if m["provenance"]["sha256"].lower() != sha:
        raise KosmoError("sha_mismatch", "The .dm changed since this page loaded. Reload; your form values are kept.",
                         expected=sha, actual=m["provenance"]["sha256"])
    values = {k: _normalize(kind, k, v, m, catalog) for k, v in raw_values.items()}
    warnings: list[str] = []
    specs = FIELDS[kind]
    if kind == "spells":
        values, warnings = _spell_rules(values, body, mode, catalog, m, warnings)
    if mode == "new":
        return _create(workspace, slug, kind, catalog, body, values, sha, preview, warnings, m)
    target = body.get("target")
    if body.get("template") is not None:
        raise KosmoError("bad_request", "A template applies only to new definitions.", field="template")
    if not values:
        raise KosmoError("bad_request", "Nothing to change.")
    if values.get("name", "") is None:
        raise KosmoError("bad_value", "The name cannot be removed.", field="name")

    def mutate(text: str, rel: str) -> tuple[str, dict[str, Any]]:
        pr = parse(text)
        b = _find(pr, kind, target, text)
        if kind == "spells" and "summon_monster" in values:
            _summon_template_check(b, catalog, values)
        use = {k: v for k, v in values.items()}
        if "summon_monster" in use:
            use["damage"] = use.pop("summon_monster")
        spans, changes = _plan(text, b, kind, [s for s in specs if s["key"] != "summon_monster"], use)
        cand = _apply_spans(text, spans)
        start_line = b.opener.line
        _verify(text, cand, kind, target, b, [s for s in specs if s["key"] != "summon_monster"], use, rel,
                lambda p: next(x for x in _blocks(p, kind) if x.opener.line == start_line))
        return cand, {"kind": kind, "mode": "edit", "key": target, "id": block_id(b) if kind != "spells" else None,
                      "name": use.get("name") or block_name(b), "changes": changes, "warnings": warnings,
                      "explanation": ["Only the listed fields changed; every other line of the block (comments, "
                                      "unknown commands, spacing) is kept."]}

    return _write(workspace, slug, sha, preview, mutate)


def _summon_template_check(b: Block, catalog: Catalog | None, values: dict[str, Any]) -> None:
    copies = [s for s in b.statements if s.command == "copyspell"]
    if copies and any(s.command in ("effect", "clear") and s.start > copies[-1].start for s in b.statements):
        raise KosmoError("bad_value", "An effect override or clear invalidates the copied summon template.", field="summon_monster")
    cp = [s for s in b.statements if s.command == "copyspell"]
    tid = cp[-1].args[0].value if cp and cp[-1].args else None
    t = _spell_template(catalog, tid) if isinstance(tid, int) else None
    if t is None or t["summon"] is None:
        raise KosmoError("bad_value", "This spell's #copyspell template is not a documented single-monster summon; "
                                      "set Damage (raw) only if you know what it means for the copied effect.",
                         field="summon_monster")


def _spell_rules(values: dict[str, Any], body: dict[str, Any], mode: str, catalog: Catalog | None,
                 m: dict[str, Any], warnings: list[str]) -> tuple[dict[str, Any], list[str]]:
    if "summon_monster" in values and "damage" in values:
        raise KosmoError("bad_value", "Set either Summoned monster or Damage (raw), not both.", field="damage")
    if values.get("summon_monster") is None and "summon_monster" in values:
        raise KosmoError("bad_value", "A summon needs a monster; remove the raw damage instead.",
                         field="summon_monster")
    if "descr" in values and "name" not in values and mode == "edit":
        warnings.append("The manual says changing a spell's name removes its description; #descr stays after #name.")
    if mode == "new" and values.get("restricted") is None:
        raise KosmoError("bad_value", "A national spell needs the nation that may research it (#restricted).",
                         field="restricted")
    if "school" in values and values["school"] == -1:
        warnings.append("School -1 means the spell cannot be researched.")
    if values.get("summon_monster") is not None and values["summon_monster"] not in _project_monsters(m):
        warnings.append("The summoned monster is a vanilla unit, not one of this project's monsters.")
    return values, warnings


def _create(workspace: Path, slug: str, kind: str, catalog: Catalog | None, body: dict[str, Any],
            values: dict[str, Any], sha: str, preview: bool, warnings: list[str], m: dict[str, Any]) -> dict[str, Any]:
    if not values.get("name"):
        raise KosmoError("bad_value", "A name is required.", field="name")
    tpl = body.get("template")
    tid = None
    explain: list[str] = []
    if tpl is not None:
        if not isinstance(tpl, dict) or set(tpl) - {"source", "id"} or tpl.get("source") not in ("catalog", "project") \
                or isinstance(tpl.get("id"), bool) or not isinstance(tpl.get("id"), int):
            raise KosmoError("bad_value", "template must be {source: catalog|project, id}.", field="template")
        tid = tpl["id"]
        if tpl["source"] == "catalog":
            if catalog is None or catalog.row(CAT[kind], tid) is None:
                raise KosmoError("bad_value", f"{tid} is not a catalog {kind[:-1]}.", field="template")
        else:
            if kind == "spells":
                raise KosmoError("bad_value", "Spells copy a catalog spell (project spells have no number).",
                                 field="template")
            ids = {d["id"] for d in _project_ids(workspace, slug, kind)}
            if tid not in ids:
                raise KosmoError("bad_value", f"{tid} is not a numbered {kind[:-1]} in this project.", field="template")
            warnings.append("Project template: the copy reflects the template as the game has read it at this point "
                            "of the file; the new block is appended after it.")
    elif kind == "spells":
        raise KosmoError("bad_value", "Choose a catalog spell to copy (#copyspell). Kosmokrator does not invent "
                                      "spell effects.", field="template")
    summon = None
    if kind == "spells":
        t = _spell_template(catalog, tid)  # type: ignore[arg-type]
        summon = t["summon"]
        if "summon_monster" in values and summon is None:
            raise KosmoError("bad_value", f"Template {t['name']} is not a documented single-monster summon (its "
                                          "effect is not one of the manual's 'damage = monster number' effects).",
                             field="summon_monster")
        if summon and "summon_monster" not in values:
            warnings.append(f"Template summons {summon['monster_name'] or summon['monster_id']}; choose Summoned "
                            "monster to summon a project unit instead.")
        if "descr" not in values:
            warnings.append("No description: the manual says setting #name removes the copied description.")
        explain.append(f"#copyspell {tid} ({t['name']}) copies the template's effect, area, range, sounds and costs; "
                       "the fields below override only what you set.")
        if values.get("summon_monster") is not None:
            values["damage"] = values.pop("summon_monster")
            explain.append(f"#damage {values['damage']} replaces the summoned monster ({summon['effect_label']}).")
        name_l = values["name"].lower()
        if catalog is not None and name_l in catalog.names("spells"):
            warnings.append("A vanilla spell has the same name; references by name may become ambiguous.")
    specs = [s for s in FIELDS[kind] if s["key"] not in ("name", "summon_monster")]
    order = ["descr"] if kind == "spells" else []
    alloc = ALLOC.get(kind)

    def build(text: str, ids: dict[str, list[int]]) -> tuple[list[tuple[int, str]], dict[str, Any]]:
        nl = _nl(text)
        nid = ids[alloc][0] if alloc else None
        opener = f"#{OPENERS[kind][0]}" + (f" {nid}" if nid is not None else "")
        lines = [opener]
        if tid is not None:
            lines.append(f"#{COPY_CMD[kind]} {tid}")
        lines.append(f'#name "{values["name"]}"')
        for spec in sorted(specs, key=lambda s: 0 if s["key"] in order else 1):
            v = values.get(spec["key"])
            if v is None or v is False:
                continue
            if spec["multi"]:
                lines += [_render(spec, x) for x in v]
            else:
                lines.append(_render(spec, v))
        lines.append("#end")
        pre = nl if text and not text.endswith("\n") else ""
        return [(len(text), f"{pre}{nl}-- Created in the Kosmokrator browser{nl}" + nl.join(lines) + nl)], {
            "kind": kind, "mode": "new", "id": nid, "key": str(nid) if nid is not None else None,
            "name": values["name"], "warnings": warnings,
            "changes": [{"field": "block", "action": "add", "before": None, "after": opener, "line": None}],
            "explanation": explain or [("Copies the template, then sets only the fields you filled in."
                                        if tid is not None else "A new definition with only the fields you filled "
                                                                "in; everything else is the game's default.")]}

    kinds = {alloc: 1} if alloc else {}
    res = _transaction(workspace, slug, sha, preview, kinds, {alloc: [values["name"]]} if alloc else {}, catalog, build)
    if kind == "spells" and res.get("written"):
        res["key"] = None
        res["note"] = "Saved. Reload the spell list to edit it (named spells keep their identity when source lines move)."
    return res


def _project_ids(workspace: Path, slug: str, kind: str) -> list[dict[str, Any]]:
    project = open_project(workspace, slug)
    _d, text, _e = read_dm(resolve_dm_target(project, None))
    return [{"id": block_id(b)} for b in _blocks(parse(text), kind) if b.new and isinstance(block_id(b), int)]


# ---------- heroes ----------
HERO_SLOTS = {"heroes": ("hero", 10), "multiheroes": ("multihero", 7)}


def _hero_specs() -> list[dict[str, Any]]:
    out = []
    for group, (cmd, n) in HERO_SLOTS.items():
        for i in range(1, n + 1):
            out.append(_f(f"{group}:{i}", f"{'Multihero' if cmd == 'multihero' else 'Hero'} {i}", "int",
                          f"{cmd}{i}", f"#{cmd}1...{n} (p.45)", -1, 19999))
    return out


def _nation_block(pr: Any, nid: int, text: str) -> Block:
    hits = [b for b in pr.blocks if b.opener.command == "selectnation" and block_id(b) == nid]
    if len(hits) != 1:
        raise KosmoError("object_missing" if not hits else "ambiguous_block",
                         f"Expected exactly one #selectnation {nid} block, found {len(hits)}.",
                         lines=[b.opener.line for b in hits])
    b = hits[0]
    if b.end is None or text[text.rfind("\n", 0, b.end.start) + 1:b.end.start].strip():
        raise KosmoError("not_editable", "The nation block is not closed by #end on its own line.")
    return b


def heroes_state(workspace: Path, slug: str, nid: int, catalog: Catalog | None) -> dict[str, Any]:
    project = open_project(workspace, slug)
    data, text, _e = read_dm(resolve_dm_target(project, None))
    pr = parse(text)
    b = _nation_block(pr, nid, text)
    m = build_project_model(workspace, slug, catalog)
    pm = _project_monsters(m)
    out: dict[str, Any] = {"heroes": [], "multiheroes": []}
    for spec in _hero_specs():
        group, slot = spec["key"].split(":")
        sts = _live(b, spec, _hero_specs())
        st = sts[-1] if sts else None
        mid = st.args[0].value if st and st.args and st.args[0].kind == "int" else None
        name = pm[mid].get("name") if mid in pm else (catalog.row("units", mid) or {}).get("name") \
            if (catalog and isinstance(mid, int) and mid > 0) else None
        out[group].append({"slot": int(slot), "monster": mid, "name": name, "line": st.line if st else None,
                           "duplicate": len(sts) > 1, "project": mid in pm})
    vanilla = nid < 150 or (catalog is not None and catalog.row("nations", nid) is not None)
    return {"sha256": sha256_bytes(data), "nation": {"id": nid, "name": block_name(b), "vanilla": vanilla},
            **out, "options": _options(m),
            "notes": ["#hero1-10 and #multihero1-7 (manual p.45). A multihero never runs out.",
                      "Removing a hero writes #heroN -1 on a vanilla nation (the manual's removal) and deletes the "
                      "line on a new nation.",
                      "Heroes appear as random events in game; when and how often is not modelled here. Use "
                      "#fixedname/#latehero on the monster (Edit values does not cover them yet)."]}


def save_heroes(workspace: Path, slug: str, nid: int, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "preview", "heroes", "multiheroes"}:
        raise KosmoError("bad_request", "Body must be {expected_sha256, preview, heroes?, multiheroes?}.")
    sha, preview = _sha(body), _preview_flag(body)
    m = build_project_model(workspace, slug, catalog)
    pm = _project_monsters(m)
    vanilla = nid < 150 or (catalog is not None and catalog.row("nations", nid) is not None)
    values: dict[str, Any] = {}
    for group, (_cmd, n) in HERO_SLOTS.items():
        g = body.get(group, {})
        if not isinstance(g, dict):
            raise KosmoError("bad_value", f"{group} must map slot numbers to monster ids or null.", field=group)
        for slot, v in g.items():
            if not re.fullmatch(r"\d{1,2}", str(slot)) or not 1 <= int(slot) <= n:
                raise KosmoError("bad_value", f"{group}: slot must be 1-{n}.", field=f"{group}:{slot}")
            key = f"{group}:{int(slot)}"
            if v is None:
                values[key] = -1 if vanilla else None
            else:
                if isinstance(v, bool) or not isinstance(v, int) or v not in pm:
                    raise KosmoError("bad_value", "Heroes must be monsters defined in this project.", field=key)
                values[key] = v
    if not values:
        raise KosmoError("bad_request", "Nothing to change.")
    chosen = [v for v in values.values() if isinstance(v, int) and v > 0]
    warnings = []
    if len(chosen) != len(set(chosen)):
        warnings.append("The same monster is assigned to more than one hero slot.")
    for v in chosen:
        if pm[v].get("recruitment"):
            warnings.append(f"{pm[v].get('name') or v} is also recruitable; heroes are usually unique monsters.")
    specs = _hero_specs()

    def mutate(text: str, rel: str) -> tuple[str, dict[str, Any]]:
        pr = parse(text)
        b = _nation_block(pr, nid, text)
        spans, changes = _plan(text, b, "nation", specs, values)
        cand = _apply_spans(text, spans)
        _verify(text, cand, "nation", str(nid), b, specs, values, rel, lambda p: _nation_block(p, nid, cand))
        return cand, {"kind": "heroes", "mode": "edit", "id": nid, "key": str(nid), "name": block_name(b),
                      "changes": changes, "warnings": warnings,
                      "explanation": ["Only #heroN/#multiheroN lines of this nation block change."]}

    return _write(workspace, slug, sha, preview, mutate)


# ---------- reference ----------
REF_CATS = ("spells", "sites", "weapons", "armors")
REF_LABELS = {
    "spells": [("school", "School"), ("researchlevel", "Research level"), ("path1", "Path 1"),
               ("pathlevel1", "Path level 1"), ("path2", "Path 2"), ("pathlevel2", "Path level 2"),
               ("fatiguecost", "Fatigue cost"), ("gemcost", "Gem cost"), ("damage", "Damage"),
               ("effects_count", "Effects"), ("next_spell", "Next spell")],
    "sites": [("path", "Path"), ("level", "Level"), ("rarity", "Rarity"), ("loc", "Locmask"), ("gold", "Gold"),
              ("res", "Resources"), ("F", "Fire gems"), ("A", "Air gems"), ("W", "Water gems"), ("E", "Earth gems"),
              ("S", "Astral gems"), ("D", "Death gems"), ("N", "Nature gems"), ("G", "Glamour gems"),
              ("B", "Blood slaves")],
    "weapons": [("att", "Attack"), ("def", "Defence"), ("len", "Length"), ("nratt", "Attacks"), ("ammo", "Ammo"),
                ("rcost", "Resource cost"), ("secondaryeffect", "Secondary effect")],
    "armors": [("type", "Type"), ("def", "Defence"), ("enc", "Encumbrance"), ("rcost", "Resource cost")],
}


def reference_search(catalog: Catalog | None, cat: str, query: str) -> dict[str, Any]:
    if cat not in REF_CATS:
        raise KosmoError("bad_category", f"cat must be one of {', '.join(REF_CATS)}.")
    if catalog is None:
        raise KosmoError("catalog_missing", "No game-data catalog configured.")
    q = (query or "").strip()
    if not q or len(q) > 60:
        raise KosmoError("bad_query", "Type 1-60 characters of a name or an id.")
    r = search(catalog, q, cat, 30)
    return {"query": q, "category": cat, "results": [{"id": x["id"], "name": x["name"], "fields": x["fields"]}
                                                      for x in r["results"]],
            "total_matches": r["total_matches"], "truncated": r["truncated"]}


def reference_detail(catalog: Catalog | None, cat: str, ident: int) -> dict[str, Any]:
    if cat not in REF_CATS:
        raise KosmoError("bad_category", f"cat must be one of {', '.join(REF_CATS)}.")
    if catalog is None:
        raise KosmoError("catalog_missing", "No game-data catalog configured.")
    row = catalog.row(cat, ident)
    if row is None:
        raise KosmoError("object_missing", f"No catalog {cat[:-1]} {ident}.")
    labelled = [{"label": lab, "value": row.get(col), "note": "raw catalog column"}
                for col, lab in REF_LABELS[cat] if (row.get(col) or "").strip() not in ("",)]
    out: dict[str, Any] = {"category": cat, "id": ident, "name": row.get("name"), "catalog_row": dict(row),
                           "labelled": labelled, "effects": [], "summon": None, "catalog": catalog.meta,
                           "note": "Raw columns of the third-party dom6inspector catalog. They are the vanilla "
                                   "values the catalog extracted, not effective values after any mod, and may "
                                   "differ from your game version."}
    if cat == "spells":
        t = _spell_template(catalog, ident)
        out["effects"] = t["effects"]
        out["summon"] = t["summon"]
        out["note"] += (" Effect numbers: catalog effect_number plus its ritual flag; only the manual-documented "
                        "summon effects are interpreted.")
    return out
