"""Mercenary companies (#newmerc, manual p.63) as first-class project content.

merc_state reads this project's #newmerc blocks into readable company records (keyed by their opener line, the same
stable key the advanced command editor uses) and resolves #com/#unit names against project and catalog monsters.
save_merc turns a structured company into documented #newmerc lines and writes them through the advanced editor's
guarded writer (command_edit.save_commands): expected SHA-256, preview first, parser/command preflight, project lock
and a backup. The manual's #com, #unit and #item take names, so references chosen by id are written as their exact
name; a #newmerc block has no numeric id. Unknown lines and every other block stay byte for byte.
"""

from __future__ import annotations

import re
from typing import Any

from .catalog import Catalog
from .dmparse import parse, block_id, block_name
from .errors import KosmoError
from .project import open_project, read_dm, resolve_dm_target, sha256_bytes

MANUAL = {"document": "Dominions 6 Modding Manual", "version": "6.36", "page": 63}
INT_FIELDS = {  # key -> (command, minimum, maximum or None)
    "level": ("level", 0, 2), "nrunits": ("nrunits", 0, None), "minmen": ("minmen", 0, None),
    "minpay": ("minpay", 0, None), "xp": ("xp", 0, None), "randequip": ("randequip", 0, 3),
    "recrate": ("recrate", 0, None), "eramask": ("eramask", 1, 7),
}
# Manual order of the documented commands; the structured form writes them in this order.
ORDER = ("name", "level", "bossname", "com", "unit", "nrunits", "minmen", "minpay", "xp", "randequip", "recrate",
         "item", "eramask")
MAX_ITEMS = 4  # "A maximum four items per band can be assigned." (manual p.63)
KEY_RE = re.compile(r"^(monster|item):line:\d{1,7}$")
MAX_TEXT = 200


def _effective(text: str, catalog: Catalog | None, category: str, context: str
               ) -> tuple[dict[str, list[dict[str, Any]]], dict[Any, dict[str, Any]]]:
    """Names in effect for this project: catalog names, renamed or added by project blocks of one context.

    Returns (lower-case name -> candidates, ref -> candidate); a ref is ("catalog", id) or the project block key
    "<context>:line:N". A #select block with #name renames the catalog entry it selects."""
    by_ref: dict[Any, dict[str, Any]] = {}
    if catalog is not None:
        for r in catalog.table(category):
            v = (r.get("id") or "").strip()
            if v.isdigit() and (r.get("name") or "").strip():
                by_ref[("catalog", int(v))] = {"origin": "catalog", "id": int(v), "name": r["name"].strip(), "key": None}
    for b in parse(text).blocks:
        if b.context != context:
            continue
        ident, name = block_id(b), block_name(b)
        key = f"{context}:line:{b.opener.line}"
        if not b.new and isinstance(ident, int) and ("catalog", ident) in by_ref:
            if name:
                by_ref[("catalog", ident)] = {**by_ref[("catalog", ident)], "name": name, "renamed_by": key}
            continue
        if name:
            by_ref[key] = {"origin": "project", "id": ident if isinstance(ident, int) else None, "name": name, "key": key}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for cand in by_ref.values():
        by_name.setdefault(cand["name"].lower(), []).append(cand)
    return by_name, by_ref


def _resolve_name(by_name: dict[str, list[dict[str, Any]]], value: Any) -> dict[str, Any]:
    """How one written #com/#unit/#item argument resolves: by name (manual form) or a bare number (not documented)."""
    if isinstance(value, int):
        return {"written": value, "status": "number", "candidates": [],
                "note": "Written as a number; the manual documents a name for this command."}
    hits = by_name.get(str(value).lower(), [])
    status = "resolved" if len(hits) == 1 else "ambiguous" if hits else "unresolved"
    return {"written": value, "status": status, "candidates": hits[:8], "candidate_count": len(hits)}


def merc_state(workspace: Any, slug: str, catalog: Catalog | None) -> dict[str, Any]:
    project = open_project(workspace, slug)
    path = resolve_dm_target(project, None)
    data, text, _enc = read_dm(path)
    pr = parse(text)
    mons, _ = _effective(text, catalog, "units", "monster")
    items, _ = _effective(text, catalog, "items", "item")
    companies = []
    for b in pr.blocks:
        if b.context != "merc":
            continue
        fields: dict[str, Any] = {}
        lines: dict[str, int] = {}
        company_items, other = [], []
        for s in b.statements:
            v = s.args[0].value if s.args else None
            if s.command == "item":
                company_items.append({"line": s.line, **_resolve_name(items, v)})
            elif s.command in ORDER:
                fields[s.command] = v
                lines[s.command] = s.line
            else:
                other.append({"line": s.line, "command": "#" + s.command, "raw": s.raw})
        companies.append({
            "key": f"merc:line:{b.opener.line}", "line": b.opener.line, "end_line": b.end.line if b.end else None,
            "closed": b.end is not None, "name": fields.get("name") or block_name(b), "fields": fields, "lines": lines,
            "commander": _resolve_name(mons, fields["com"]) if "com" in fields else None,
            "troop": _resolve_name(mons, fields["unit"]) if "unit" in fields else None,
            "items": company_items, "other_commands": other,
        })
    clears = [s.line for s in pr.statements if s.command == "clearmercs"]
    monsters = []
    for b in pr.blocks:
        if b.context == "monster" and b.new and block_name(b):
            ident = block_id(b)
            monsters.append({"key": f"monster:line:{b.opener.line}", "id": ident if isinstance(ident, int) else None,
                             "name": block_name(b), "line": b.opener.line,
                             "name_shared_by": len(mons.get(block_name(b).lower(), []))})
    project_items = [{"key": f"item:line:{b.opener.line}", "id": block_id(b) if isinstance(block_id(b), int) else None,
                      "name": block_name(b), "line": b.opener.line}
                     for b in pr.blocks if b.context == "item" and b.new and block_name(b)]
    return {"sha256": sha256_bytes(data), "dm": project.rel(path), "companies": companies, "clearmercs_lines": clears,
            "options": {"monsters": monsters, "items": project_items,
                        "levels": [{"value": 0, "label": "0: appears early"}, {"value": 1, "label": "1: appears later"},
                                   {"value": 2, "label": "2: appears last of all"}],
                        "eramasks": [{"value": k, "label": f"{k}: {v}"} for k, v in (
                            (1, "Early era"), (2, "Middle era"), (3, "Early + middle"), (4, "Late era"),
                            (5, "Early + late"), (6, "Middle + late"), (7, "All eras"))],
                        "randequip": [{"value": 0, "label": "0: none"}, {"value": 1, "label": "1"},
                                      {"value": 2, "label": "2"}, {"value": 3, "label": "3: extremely powerful"}],
                        "max_items": MAX_ITEMS},
            "catalog_available": catalog is not None, "manual": MANUAL,
            "notes": ["#com, #unit and #item take names (manual p.63). The form writes the exact name of the monster "
                      "or item you pick; if several monsters share that name the game's choice is not documented, so "
                      "the review warns.",
                      "A company references existing or new monster definitions; it has no sprite command of its own. "
                      "New monsters used by a company need their own original artwork.",
                      "Omitted lines use the game's defaults; the manual's default era mask is all eras.",
                      "Edit or remove existing companies with the advanced command editor (Create & edit → "
                      "Mercenaries)."]}


def _text(value: Any, label: str, required: bool) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise KosmoError("bad_value", f"{label} is required.", field=label.lower().replace(" ", "_"))
        return None
    if not isinstance(value, str) or '"' in value or "\x00" in value or "\n" in value or "\r" in value \
            or len(value.strip()) > MAX_TEXT:
        raise KosmoError("bad_value", f"{label}: up to {MAX_TEXT} characters on one line, without double quotes.",
                         field=label.lower().replace(" ", "_"))
    return value.strip()


def _pick(ref: Any, by_ref: dict[Any, dict[str, Any]], by_name: dict[str, list[dict[str, Any]]], label: str,
          kind: str) -> tuple[dict[str, Any], list[str]]:
    """A {origin: catalog, id} or {origin: project, key} reference -> (candidate, warnings)."""
    if not isinstance(ref, dict) or set(ref) - {"origin", "id", "key"}:
        raise KosmoError("bad_value", f"{label}: choose a project or catalog {kind}.", field=label.lower())
    if ref.get("origin") == "catalog" and type(ref.get("id")) is int:
        cand = by_ref.get(("catalog", ref["id"]))
    elif ref.get("origin") == "project" and isinstance(ref.get("key"), str) and KEY_RE.match(ref["key"]) \
            and ref["key"].startswith(kind):
        cand = by_ref.get(ref["key"])
    else:
        raise KosmoError("bad_value", f"{label}: choose a project or catalog {kind}.", field=label.lower())
    if cand is None:
        raise KosmoError("bad_value", f"{label}: that {kind} is not in this project or its catalog.",
                         field=label.lower())
    warnings = []
    shared = len(by_name.get(cand["name"].lower(), []))
    if shared > 1:
        cmd = {"Commander": "#com", "Troop": "#unit"}.get(label, "#item")
        warnings.append(f"{label}: {shared} {kind}s are named \"{cand['name']}\". {cmd} takes a name (manual p.63) and "
                        "which one the game picks is not documented. A unique name avoids the doubt.")
    return cand, warnings


def save_merc(workspace: Any, slug: str, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    """Preview or append one new #newmerc company built from structured, manual-documented fields."""
    from .author import _preview_flag, _sha
    from .command_edit import save_commands
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "preview", "company"}:
        raise KosmoError("bad_request", "Body must be {expected_sha256, preview, company}.")
    sha, preview = _sha(body), _preview_flag(body)
    company = body.get("company")
    allowed = {"name", "bossname", "commander", "troop", "items", *INT_FIELDS}
    if not isinstance(company, dict) or set(company) - allowed:
        raise KosmoError("bad_request", f"company accepts only: {', '.join(sorted(allowed))}.")
    project = open_project(workspace, slug)
    data, text, _enc = read_dm(resolve_dm_target(project, None))
    if sha256_bytes(data).lower() != sha:
        raise KosmoError("sha_mismatch", "The .dm changed since this page loaded. Reload; your form values are kept.",
                         expected=sha, actual=sha256_bytes(data))
    mon_names, mon_refs = _effective(text, catalog, "units", "monster")
    item_names, item_refs = _effective(text, catalog, "items", "item")
    name = _text(company.get("name"), "Name", True)
    boss = _text(company.get("bossname"), "Boss name", True)
    commander, warnings = _pick(company.get("commander"), mon_refs, mon_names, "Commander", "monster")
    values: dict[str, Any] = {"name": name, "bossname": boss, "com": commander["name"]}
    troop = None
    if company.get("troop") is not None:
        troop, w = _pick(company["troop"], mon_refs, mon_names, "Troop", "monster")
        warnings += w
        values["unit"] = troop["name"]
    for key, (_cmd, lo, hi) in INT_FIELDS.items():
        v = company.get(key)
        if v is None or v == "":
            continue
        if type(v) is not int or v < lo or (hi is not None and v > hi):
            raise KosmoError("bad_value", f"{key}: a whole number {lo}{f'-{hi}' if hi is not None else ' or more'}.",
                             field=key)
        values[key] = v
    items_in = company.get("items") or []
    if not isinstance(items_in, list) or len(items_in) > MAX_ITEMS:
        raise KosmoError("bad_value", f"items: at most {MAX_ITEMS} items per band (manual p.63).", field="items")
    chosen_items = []
    for ref in items_in:
        cand, w = _pick(ref, item_refs, item_names, "Item", "item")
        warnings += w
        chosen_items.append(cand)
    if troop is None and values.get("nrunits"):
        raise KosmoError("bad_value", "Choose a troop type, or set the number of troops to 0.", field="troop")
    if troop is not None and not values.get("nrunits"):
        warnings.append("A troop type is set but the number of troops is 0 or omitted.")
    changes = []
    for cmd in ORDER:
        if cmd == "item":
            changes += [{"op": "add", "command": "item", "args": [c["name"]]} for c in chosen_items]
        elif cmd in values:
            changes.append({"op": "add", "command": cmd, "args": [values[cmd]]})
    result = save_commands(workspace, slug, catalog, {"expected_sha256": sha, "preview": preview, "context": "merc",
                                                      "mode": "new", "opener": {"command": "newmerc", "args": []},
                                                      "changes": changes})
    refs = {"commander": commander, "troop": troop, "items": chosen_items}
    return {**result, "warnings": [*warnings, *(result.get("warnings") or [])], "resolved": refs,
            "company": {"name": name, "bossname": boss, **{k: v for k, v in values.items() if k in INT_FIELDS}},
            "explanation": ["A #newmerc block has no numeric id; it is addressed by its opener line.",
                            "Names are written exactly as the chosen monster or item is named now."]}
