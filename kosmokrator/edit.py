"""Bounded in-place editor for one project monster block, used by the local web browser.

Stats, leadership, magic paths and pretender fields, plus every documented monster trait in traits.py (typed
arguments, references and repeatable lines) can be set, changed, added or removed. Edits are computed in memory as
small text spans inside the selected #newmonster/#selectmonster block; everything else in the .dm (unknown
commands, comments, donor lines, sprites, order, newlines, encoding) is left byte-for-byte as it was. The
candidate text is re-parsed and re-checked before anything is written, and the write itself goes through
project.apply_mod_patch (project lock, expected SHA-256, backup, lossless self-check).

Never generated: #clearspec, #clearmagic, #clear or #copystats. Removing an ability that is only inherited
from the donor needs one of those and would remove other abilities too, so it is refused with an explanation.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from . import commands as cmdreg
from . import traits as tr
from .browse import LEADER_CMDS, PATHS, PATH_NAMES, _Ctx, _resolve_monster
from .catalog import Catalog
from .dmparse import Block, Statement, block_id, block_name, definitions, newline_style, parse
from .errors import KosmoError
from .project import apply_mod_patch, open_project, read_dm, resolve_dm_target, sha256_bytes
from .validate import Report, _check_statement

MAX_CHANGES = 64
# Resets that end the effect of earlier lines (Clearing & Copying, Modding Manual p.13).
B_STATS = ("copystats", "clear")
B_MAGIC = ("copystats", "clear", "clearmagic")
B_SPEC = ("copystats", "clear", "clearspec")
B_COST = ("copystats",)

# key -> label, group, kind, (lo, hi), zero allowed, boundaries, note. Ranges come from the curated registry
# where the manual states one; otherwise they are Kosmokrator sanity bounds and are labelled as such.
_STATS = [("hp", "Hit points", 1, 9999), ("str", "Strength", 0, 999), ("att", "Attack skill", 0, 999),
          ("def", "Defence skill", 0, 999), ("prec", "Precision", 0, 999), ("prot", "Natural protection", 0, 99),
          ("size", "Size", 1, 10), ("mr", "Magic resistance", 0, 99), ("mor", "Morale", 0, 99),
          ("enc", "Encumbrance", 0, 99), ("mapmove", "Map move", 0, 99), ("ap", "Combat speed (AP)", 1, 99)]
def _doc(cmd: str) -> str:
    spec = cmdreg.get("monster", cmd)
    if spec:
        return f"curated: {spec.section}, p.{spec.page}"
    if cmd in cmdreg.DOCUMENTED["monster"]:
        return "documented in the manual; arguments not in the curated registry"
    raise RuntimeError(f"editor field #{cmd} is not documented")  # guards the tables above at import


def _schema() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for k, label, lo, hi in _STATS:
        out[k] = {"label": label, "group": "stats", "kind": "int", "command": k, "min": lo, "max": hi,
                  "zero": lo <= 0, "bounds": B_STATS, "doc": _doc(k)}
    out["mapmove"]["note"] = "Manual: 0 makes the unit unable to move on the world map."
    out["leader"] = {"label": "Leadership", "group": "leadership", "kind": "leader", "command": None,
                     "choices": list(LEADER_CMDS), "bounds": B_STATS, "doc": _doc("goodleader")}
    for n, p in enumerate(PATHS):
        out[f"magic:{n}"] = {"label": f"{PATH_NAMES[p]} ({p})", "group": "magic", "kind": "magic",
                             "command": "magicskill", "path": n, "min": 1, "max": 10, "zero": False,
                             "bounds": B_MAGIC, "doc": _doc("magicskill"),
                             **({"note": "Units with Holy (path 9) magic must also have #holy."} if n == 9 else {})}
    out["startdom"] = {"label": "Starting dominion", "group": "god", "kind": "int", "command": "startdom", "min": 1,
                       "max": 10, "zero": False, "bounds": B_SPEC, "doc": _doc("startdom"),
                       "note": "Manual: standard is 1 (arch mage) to 4 (oracle). Makes the monster a selectable god."}
    out["pathcost"] = {"label": "New path cost", "group": "god", "kind": "int", "command": "pathcost", "min": 1,
                       "max": 200, "zero": False, "bounds": B_SPEC, "doc": _doc("pathcost"),
                       "note": "Manual: standard is 10 (arch mage) to 80 (dragon)."}
    out["gcost"] = {"label": "Gold / design cost", "group": "god", "kind": "int", "command": "gcost", "min": 0,
                    "max": 19999, "zero": True, "bounds": B_COST, "doc": _doc("gcost"),
                    "note": "10000 + base means autocalc. The game computes the final cost."}
    for f in out.values():
        if f["kind"] in ("int", "magic"):
            spec = cmdreg.get("monster", f["command"])
            arg = spec.args[1 if f["kind"] == "magic" else 0] if spec else None
            f["range_source"] = ("manual" if arg is not None and arg.lo is not None and arg.hi is not None
                                 else "sanity bound (the manual states no range)")
    return out


SCHEMA = _schema()
KEY_ORDER = list(SCHEMA)


def _public_schema() -> dict[str, Any]:
    return {k: {kk: vv for kk, vv in v.items() if kk != "bounds"} for k, v in SCHEMA.items()}


def _matches(key: str, st: Statement) -> bool:
    f = SCHEMA[key]
    if f["kind"] == "leader":
        return st.command in LEADER_CMDS
    if f["kind"] == "magic":
        return st.command == "magicskill" and bool(st.args) and st.args[0].kind == "int" and st.args[0].value == f["path"]
    return st.command == f["command"]


def _live(block: Block, key: str) -> tuple[list[Statement], list[Statement], Statement | None]:
    """(statements after the last reset, earlier dead ones, the last reset) for one field."""
    bounds = SCHEMA[key]["bounds"]
    last = None
    for st in block.statements:
        if st.command in bounds:
            last = st
    after = [st for st in block.statements if _matches(key, st) and (last is None or st.start > last.start)]
    dead = [st for st in block.statements if _matches(key, st) and last is not None and st.start < last.start]
    return after, dead, last


def _authored_value(key: str, st: Statement) -> Any:
    f = SCHEMA[key]
    if f["kind"] == "leader":
        return st.command
    if f["kind"] == "flag":
        return True if not st.args else None
    i = 1 if f["kind"] == "magic" else 0
    want = 2 if f["kind"] == "magic" else 1
    if len(st.args) != want or st.args[i].kind != "int":
        return None
    return st.args[i].value


def _find_block(text: str, mid: int) -> tuple[Any, Block]:
    pr = parse(text)
    hits = [b for b in pr.blocks if b.context == "monster" and b.opener.command in ("newmonster", "selectmonster")
            and block_id(b) == mid]
    if not hits:
        raise KosmoError("object_missing", f"No #newmonster/#selectmonster {mid} block in this project.")
    if len(hits) > 1:
        raise KosmoError("ambiguous_block", f"Monster {mid} is opened by {len(hits)} blocks; edit the source instead.",
                         lines=[b.opener.line for b in hits])
    b = hits[0]
    name = block_name(b)
    by_name = [x.opener.line for x in pr.blocks if x.context == "monster" and isinstance(block_id(x), str)
               and name and str(block_id(x)).lower() == name.lower()]
    if by_name:
        raise KosmoError("ambiguous_block", "Another #selectmonster block selects this monster by name; "
                                            "edit the source instead.", lines=by_name)
    if b.end is None:
        raise KosmoError("not_editable", "This block is not closed with #end.", lines=[b.opener.line])
    if text[text.rfind("\n", 0, b.end.start) + 1:b.end.start].strip():
        raise KosmoError("not_editable", "#end does not start its own line.", lines=[b.end.line])
    bad = [i for i in pr.issues if b.opener.line <= i["line"] <= b.end.line]
    if bad:
        raise KosmoError("not_editable", "The block has syntax problems; fix them in the source first.",
                         lines=[i["line"] for i in bad])
    return pr, b


def _ctx(text: str, slug: str, dm_rel: str, catalog: Catalog | None, pr: Any) -> _Ctx:
    c = _Ctx(slug, dm_rel, text.splitlines(), catalog, None)
    for b in pr.blocks:
        if b.context == "monster" and isinstance(block_id(b), int):
            c.monsters_by_id[block_id(b)] = {"name": block_name(b)}
    return c


def _effective(res: dict[str, Any], key: str) -> dict[str, Any]:
    """The browser model's view of a field: {value, source, line, status}. value None means not present."""
    r = res["resolved"]
    f = SCHEMA[key]
    if f["group"] == "stats":
        x = r["stats"][key]
    elif key == "leader":
        x = r["leadership"]
    elif f["kind"] == "magic":
        x = r["magic"]["paths"].get(PATHS[f["path"]]) or {"value": None, "source": "none", "status": "resolved"}
    elif key in ("startdom", "pathcost"):
        x = r["god"][key]
    elif key == "gcost":
        g = r["costs"]["gold"]
        x = {"value": g["authored_value"], "source": g["source"], "line": g["line"],
             "status": "resolved" if g["source"] != "unresolved_donor" else "unresolved"}
    else:
        x = r["specials"].get(key) or r["creature_traits"].get(key)
        if x is None:
            modelled = key in _modelled_specials()
            x = {"value": None, "source": "none" if modelled else "not_modelled",
                 "status": "resolved" if modelled else "unresolved"}
    return {k: x.get(k) for k in ("value", "source", "line", "status", "note") if x.get(k) is not None or k == "value"}


def _modelled_specials() -> set[str]:
    from .browse import SPECIALS, TRAITS
    return set(SPECIALS) | set(TRAITS)


def _donor_value(res: dict[str, Any], key: str) -> Any:
    d = res.get("donor") or {}
    row = d.get("catalog_row") or {}
    f = SCHEMA[key]
    col = {"leader": "leader", "gcost": "basecost"}.get(key) or (PATHS[f["path"]] if f["kind"] == "magic" else key)
    v = row.get(col)
    return v if v not in (None, "", "0") else None


def _field_state(block: Block, res: dict[str, Any], key: str) -> dict[str, Any]:
    after, dead, last = _live(block, key)
    eff = _effective(res, key)
    st = after[-1] if after else None
    out: dict[str, Any] = {"key": key, "effective": eff, "donor": _donor_value(res, key),
                           "authored": None, "duplicates": [s.line for s in after] if len(after) > 1 else [],
                           "dead_lines": [s.line for s in dead]}
    if st is not None:
        out["authored"] = {"value": _authored_value(key, st), "line": st.line, "raw": st.raw}
        if out["authored"]["value"] is None:
            out["malformed"] = st.line
    if last is not None:
        out["reset"] = {"command": f"#{last.command}", "line": last.line}
    return out


# ---- full trait catalogue (traits.py) ----------------------------------------------------------------------------

def _refs(pr: Any, catalog: Catalog | None) -> tr.RefIndex:
    local: dict[str, tuple[set[int], set[str]]] = {}
    kinds = {"monster": "mon", "spell": "spell", "site": "site", "item": "item"}
    for d in definitions(pr):
        k = kinds.get(d["kind"])
        if not k:
            continue
        ids, names = local.setdefault(k, (set(), set()))
        if d["id"] is not None:
            ids.add(d["id"])
        for n in (d["name"], d["selector"]):
            if isinstance(n, str):
                names.add(n.lower())
    return tr.RefIndex(local, catalog)


def _trait_lines(block: Block, t: tr.Trait) -> tuple[list[Statement], list[Statement], Statement | None]:
    last = None
    for st in block.statements:
        if st.command in t.bounds:
            last = st
    mine = [st for st in block.statements if st.command == t.command]
    after = [st for st in mine if last is None or st.start > last.start]
    return after, [st for st in mine if st not in after], last


def _trait_effective(res: dict[str, Any], cmd: str, live: list[Statement]) -> dict[str, Any]:
    r = res["resolved"]
    x = r["specials"].get(cmd) or r["creature_traits"].get(cmd)
    if x is not None:
        return {k: x.get(k) for k in ("value", "source", "line", "status", "note") if x.get(k) is not None or k == "value"}
    if live:
        args = tr.statement_args(tr.TRAITS[cmd], live[-1])
        value = True if args == [] else args[0] if args and len(args) == 1 else args
        return {"value": value, "source": "authored", "line": live[-1].line, "status": "unresolved",
                "note": "Authored arguments are listed; the effective gameplay value is not modelled."}
    from .browse import SPECIALS, TRAITS as BTRAITS
    if cmd in SPECIALS or cmd in BTRAITS:
        return {"value": None, "source": "none", "status": "resolved"}
    return {"value": None, "source": "not_modelled", "status": "unresolved",
            "note": "Whether the donor already has this ability is not modelled (not a catalog column here)."}


def _trait_state(block: Block, res: dict[str, Any], t: tr.Trait) -> dict[str, Any]:
    live, dead, last = _trait_lines(block, t)
    out: dict[str, Any] = {"key": t.command, "effective": _trait_effective(res, t.command, live),
                           "lines": [{"line": st.line, "raw": st.raw.strip(), "args": tr.statement_args(t, st),
                                      "malformed": tr.statement_args(t, st) is None} for st in live],
                           "dead_lines": [st.line for st in dead]}
    if t.repeat is None and len(live) > 1:
        out["duplicates"] = [st.line for st in live]
    if last is not None:
        out["reset"] = {"command": f"#{last.command}", "line": last.line}
    return out


def _present_traits(block: Block, res: dict[str, Any]) -> list[str]:
    r = res["resolved"]
    seen = {st.command for st in block.statements} | set(r["specials"]) | set(r["creature_traits"])
    return [k for k in tr.TRAITS if k in seen]


def editor_state(workspace: Path, slug: str, mid: int, catalog: Catalog | None) -> dict[str, Any]:
    """Everything the web form needs: schema, current SHA-256 and per-field authored/effective state."""
    project = open_project(workspace, slug)
    path = resolve_dm_target(project, None)
    data, text, _enc = read_dm(path)
    pr, b = _find_block(text, mid)
    res = _resolve_monster(_ctx(text, slug, project.rel(path), catalog, pr), b)
    fields = {k: _field_state(b, res, k) for k in KEY_ORDER}
    return {"project": slug, "id": mid, "uid": f"monster:{mid}", "name": res["name"] or block_name(b),
            "opener": f"#{b.opener.command}", "line": b.opener.line, "end_line": b.end.line if b.end else None,
            "sha256": sha256_bytes(data), "file": project.rel(path),
            "donor": {k: (res["donor"] or {}).get(k) for k in ("command", "ref", "id", "name", "line", "resolved")}
            if res["donor"] else None,
            "schema": _public_schema(), "fields": fields, "traits": tr.public_catalogue(),
            "trait_fields": {k: _trait_state(b, res, tr.TRAITS[k]) for k in _present_traits(b, res)},
            "limits": ["Only the listed fields and documented traits can be edited here; everything else (names, "
                       "sprites, equipment, resets, unknown commands) stays as written.",
                       "Kosmokrator never adds #clearspec, #clearmagic, #clear or #copystats for you, so a trait "
                       "inherited from the donor cannot be removed here.",
                       "Inherited abilities are only shown for modelled donor columns; others are labelled "
                       "'not modelled' rather than guessed.",
                       "Ranges marked 'sanity bound' are not from the manual. Test in Dominions 6."]}


def _check_change(ch: Any) -> tuple[str, str, Any, int | None]:
    if not isinstance(ch, dict) or set(ch) - {"key", "op", "value", "line"}:
        raise KosmoError("bad_change", "Each change is an object with key, op, value and (for repeatable traits) line.")
    key, op, value, line = ch.get("key"), ch.get("op"), ch.get("value"), ch.get("line")
    if isinstance(key, str) and key not in SCHEMA and key in tr.TRAITS:
        t = tr.TRAITS[key]
        ops = ("add", "remove", "replace") if t.repeat is not None else ("set", "remove")
        if op not in ops:
            raise KosmoError("bad_change", f"#{key}: op must be one of {', '.join(ops)}.", field=key)
        needs_line = t.repeat is not None and op in ("remove", "replace")
        if needs_line != (line is not None) or (line is not None and (isinstance(line, bool) or not isinstance(line, int))):
            raise KosmoError("bad_change", f"#{key}: {'give the line number of the authored line' if needs_line else 'line is only used to remove or replace a repeatable line'}.", field=key)
        if (op == "remove") != (value is None):
            raise KosmoError("bad_change", "A remove change takes no value; other changes need one.", field=key)
        return key, op, value, line
    if line is not None:
        raise KosmoError("bad_change", "line is only used for repeatable traits.", field=str(key)[:40])
    if not isinstance(key, str) or key not in SCHEMA:
        raise KosmoError("unsupported_field", f"{key!r} is not an editable field or documented trait.", field=str(key)[:40])
    f = SCHEMA[key]
    if op == "remove":
        if value is not None:
            raise KosmoError("bad_change", "A remove change takes no value.", field=key)
        return key, op, None, None
    if op != "set":
        raise KosmoError("bad_change", "op must be 'set' or 'remove'.", field=key)
    if f["kind"] == "leader":
        if not isinstance(value, str) or value not in LEADER_CMDS:
            raise KosmoError("bad_value", "Leadership must be one of " + ", ".join(LEADER_CMDS), field=key)
    else:
        if isinstance(value, bool) or not isinstance(value, int):
            raise KosmoError("bad_value", f"{f['label']} must be a whole number.", field=key)
        if not f["min"] <= value <= f["max"]:
            raise KosmoError("bad_value", f"{f['label']} must be between {f['min']} and {f['max']}.", field=key)
        if value == 0 and not f["zero"]:
            raise KosmoError("bad_value", f"{f['label']} cannot be 0; remove the command instead.", field=key)
    return key, op, value, None


def _check_trait_values(changes: list[tuple[str, str, Any, int | None]], refs: tr.RefIndex
                        ) -> list[tuple[str, str, Any, int | None]]:
    out = []
    for key, op, value, line in changes:
        if key in tr.TRAITS and op != "remove":
            try:
                value = tr.check_value(tr.TRAITS[key], value, refs)
            except tr.TraitValueError as e:
                raise KosmoError("bad_value", str(e), field=key) from None
        out.append((key, op, value, line))
    return out


def _line_bounds(text: str, st: Statement) -> tuple[int, int, int]:
    """(line start, line end without newline, end including the newline) of a single-line statement."""
    ls = text.rfind("\n", 0, st.start) + 1
    le = text.find("\n", st.end)
    le = len(text) if le == -1 else le
    lr = le - 1 if le > 0 and text[le - 1] == "\r" else le
    return ls, lr, min(le + 1, len(text))


def _render(key: str, value: Any) -> str:
    f = SCHEMA[key]
    if f["kind"] == "leader":
        return f"#{value}"
    if f["kind"] == "flag":
        return f"#{key}"
    if f["kind"] == "magic":
        return f"#magicskill {f['path']} {value}"
    return f"#{f['command']} {value}"


def _args_span(st: Statement) -> tuple[int, int]:
    """Absolute (start, end) of the argument text of a single-line statement (a trailing comment is untouched)."""
    first = st.raw.find(st.args[0].raw, len(st.raw_command) + 1)
    last = st.raw.rfind(st.args[-1].raw)
    return st.start + first, st.start + last + len(st.args[-1].raw)


def _drop_line(text: str, st: Statement) -> tuple[int, int, str]:
    ls, lr, le = _line_bounds(text, st)
    if text[ls:st.start].strip() or text[st.end:lr].strip():
        return st.start, st.end, ""  # keep the comment / other text on that line
    return ls, le, ""


def _plan_trait(text: str, block: Block, res: dict[str, Any], t: tr.Trait, op: str, value: Any, line: int | None,
                spans: list[tuple[int, int, str]], appended: list[str], plan: list[dict[str, Any]],
                blocked: list[dict[str, Any]]) -> None:
    live, dead, last = _trait_lines(block, t)
    eff = _trait_effective(res, t.command, live)
    label = f"#{t.command}"
    item: dict[str, Any] = {"key": t.command, "label": label, "op": op, "value": value, "line": line,
                            "effective_before": eff}
    where = f"after #{last.command} on line {last.line}" if last else "after the existing commands"
    dead_note = (f" Older line(s) {', '.join(str(s.line) for s in dead)} stay as written; a reset already ended them."
                 if dead else "")
    if t.repeat is None and len(live) > 1:
        blocked.append({**item, "reason": f"{label} appears {len(live)} times after the last reset (lines "
                                          f"{', '.join(str(s.line) for s in live)}). Fix the duplicates in the source "
                                          "first.", "lines": [s.line for s in live]})
        return
    if t.repeat is not None and op in ("remove", "replace"):
        hit = [s for s in live if s.line == line]
        if not hit:
            why = (f"it is before #{last.command} on line {last.line} and already has no effect"
                   if last is not None and any(s.line == line for s in dead) else f"there is no live {label} on that line")
            blocked.append({**item, "reason": f"Line {line}: {why}.", "lines": [line]})
            return
        st = hit[0]
        if op == "remove":
            spans.append(_drop_line(text, st))
            plan.append({**item, "action": "remove", "line": st.line, "before": st.raw.strip(),
                         "explanation": f"Deletes only line {st.line}; other {label} lines stay."})
            return
        if tr.statement_args(t, st) is None:
            blocked.append({**item, "reason": f"Line {st.line} ({st.raw.strip()}) does not have the documented "
                                              "arguments, so it is not rewritten.", "lines": [st.line]})
            return
        a, z = _args_span(st)
        rep = tr.render(t, value).split(" ", 1)[1]
        spans.append((a, z, rep))
        plan.append({**item, "action": "replace", "line": st.line, "before": st.raw.strip(),
                     "after": st.raw[:a - st.start] + rep + st.raw[z - st.start:],
                     "explanation": f"Changes the arguments on line {st.line}; nothing else on that line is touched."})
        return
    if op == "add":
        n = len(live) + sum(1 for x in appended if x.split(" ", 1)[0] == label)
        if t.repeat and n >= t.repeat:
            blocked.append({**item, "reason": f"The manual allows {label} at most {t.repeat} times on one monster "
                                              f"(p.{t.page}); {n} already live or being added."})
            return
        new = tr.render(t, value)
        appended.append(new)
        plan.append({**item, "action": "append", "after": new,
                     "explanation": f"Adds another {label} line just before #end ({where})." + dead_note})
        return
    st = live[0] if live else None
    if st is not None and tr.statement_args(t, st) is None:
        blocked.append({**item, "reason": f"Line {st.line} ({st.raw.strip()}) does not have the documented arguments, "
                                          "so it is not rewritten.", "lines": [st.line]})
        return
    if op == "set":
        new = tr.render(t, value)
        if st is not None and tr.statement_args(t, st) == value:
            plan.append({**item, "action": "unchanged", "line": st.line, "explanation": f"Already set by line {st.line}."})
            return
        if st is not None:
            a, z = _args_span(st)
            rep = new.split(" ", 1)[1]
            spans.append((a, z, rep))
            plan.append({**item, "action": "replace", "line": st.line, "before": st.raw.strip(),
                         "after": st.raw[:a - st.start] + rep + st.raw[z - st.start:],
                         "explanation": f"Changes the existing command on line {st.line}; nothing else on that line "
                                        "is touched."})
        else:
            appended.append(new)
            plan.append({**item, "action": "append", "after": new,
                         "explanation": f"Adds {label} just before #end ({where}), so no reset overwrites it." + dead_note})
        return
    # remove (single value)
    if st is None:
        if eff.get("value") not in (None, False) and eff.get("source") == "donor":
            why = "#clearmagic" if t.bounds == tr.MAGIC_RESETS else "#clearspec"
            blocked.append({**item, "reason": f"{label} is inherited from the donor, not authored here. No command "
                                              f"removes only this; it would need {why}, which also removes other "
                                              "inherited abilities. Not done automatically."})
        else:
            blocked.append({**item, "reason": "There is no live authored line for this trait to remove."})
        return
    spans.append(_drop_line(text, st))
    if last is not None and last.command != "copystats":
        fallback = f"nothing: #{last.command} on line {last.line} already cleared earlier values"
    else:
        fallback = "whatever the donor has (" + ("not modelled for this trait" if eff.get("source") == "not_modelled"
                                                  or eff.get("source") == "authored" else "see the review") + ")"
    plan.append({**item, "action": "remove", "line": st.line, "before": st.raw.strip(),
                 "explanation": f"Deletes the authored line {st.line}. The trait then falls back to {fallback}."})


def plan_edit(text: str, block: Block, res: dict[str, Any], changes: list[tuple[str, str, Any, int | None]]
              ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (candidate text, per-change plan, blocked reasons). Spans never overlap: one change per key."""
    spans: list[tuple[int, int, str]] = []
    appended: list[str] = []
    plan: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    style = newline_style(text)
    end_ls = text.rfind("\n", 0, block.end.start) + 1  # type: ignore[union-attr]
    nl = "\r\n" if style == "crlf" or (style == "mixed" and text[max(0, end_ls - 2):end_ls] == "\r\n") else "\n"
    order = KEY_ORDER + list(tr.TRAITS)
    for key, op, value, line in sorted(changes, key=lambda c: (order.index(c[0]), c[3] or 0)):
        if key in tr.TRAITS and key not in SCHEMA:
            _plan_trait(text, block, res, tr.TRAITS[key], op, value, line, spans, appended, plan, blocked)
            continue
        f = SCHEMA[key]
        after, dead, last = _live(block, key)
        eff = _effective(res, key)
        donor = _donor_value(res, key)
        item: dict[str, Any] = {"key": key, "label": f["label"], "op": op, "value": value, "effective_before": eff}
        if len(after) > 1:
            blocked.append({**item, "reason": f"#{after[0].command} appears {len(after)} times after the last reset "
                                              f"(lines {', '.join(str(s.line) for s in after)}). Fix the duplicates "
                                              "in the source first.", "lines": [s.line for s in after]})
            continue
        st = after[0] if after else None
        if st is not None and _authored_value(key, st) is None:
            blocked.append({**item, "reason": f"Line {st.line} ({st.raw.strip()}) does not have the expected "
                                              "arguments, so it is not rewritten.", "lines": [st.line]})
            continue
        if op == "set":
            new = _render(key, value)
            if st is not None and _authored_value(key, st) == value:
                plan.append({**item, "action": "unchanged", "line": st.line,
                             "explanation": f"Already set by line {st.line}."})
                continue
            if st is not None:
                if f["kind"] == "leader":
                    a, z = st.start + 1, st.start + 1 + len(st.raw_command)
                    rep = value
                else:
                    a = st.start + st.raw.rfind(st.args[-1].raw)
                    z, rep = a + len(st.args[-1].raw), str(value)
                spans.append((a, z, rep))
                plan.append({**item, "action": "replace", "line": st.line, "before": st.raw.strip(),
                             "after": st.raw[:a - st.start] + rep + st.raw[z - st.start:],
                             "explanation": f"Changes the existing command on line {st.line}; nothing else on "
                                            "that line is touched."})
            else:
                appended.append(new)
                where = f"after #{last.command} on line {last.line}" if last else "after the existing commands"
                plan.append({**item, "action": "append", "after": new,
                             "explanation": f"Adds a new override just before #end ({where}), so it is not "
                                            "overwritten by a reset." + (f" Older line(s) {', '.join(str(s.line) for s in dead)} "
                                                                        "stay as written; they were already reset."
                                                                        if dead else "")})
            continue
        # remove
        if st is None:
            if f["group"] == "stats" or f["kind"] == "leader":
                blocked.append({**item, "reason": f"{f['label']} is not authored in this block, so there is nothing "
                                                  "to remove. Base values always exist; set a new value instead."})
            elif eff.get("value") not in (None, False) and eff.get("source") == "donor":
                why = "#clearmagic" if f["kind"] == "magic" else "#clearspec"
                blocked.append({**item, "reason": f"{f['label']} is inherited from the donor"
                                                  f"{' (' + str(donor) + ')' if donor else ''}, not authored here. "
                                                  f"There is no command that removes only this; it would need {why}, "
                                                  "which also removes other inherited values. Not done "
                                                  "automatically; edit the source if that is really intended."})
            else:
                blocked.append({**item, "reason": "There is no authored command for this field to remove."})
            continue
        ls, lr, le = _line_bounds(text, st)
        before_text, after_text = text[ls:st.start], text[st.end:lr]
        if before_text.strip() or after_text.strip():
            spans.append((st.start, st.end, ""))  # keep the trailing comment on its own
        else:
            spans.append((ls, le, ""))
        if f["group"] == "stats" or f["kind"] == "leader":
            fallback = f"the donor value ({donor})" if donor is not None else "the game default (not modelled)"
        elif last is not None and last.command != "copystats":
            fallback = f"nothing: #{last.command} on line {last.line} has already cleared any inherited value"
        else:
            fallback = (f"the donor value ({donor}), which is inherited and stays" if donor is not None
                        else "nothing (no inherited value found)")
        plan.append({**item, "action": "remove", "line": st.line, "before": st.raw.strip(),
                     "explanation": f"Deletes the authored command on line {st.line}. The field then falls back "
                                    f"to {fallback}."})
    if appended:
        spans.append((end_ls, end_ls, "".join(a + nl for a in appended)))
    out = text
    for a, z, rep in sorted(spans, key=lambda s: (s[0], s[1]), reverse=True):
        out = out[:a] + rep + out[z:]
    return out, plan, blocked


def _preflight(text: str, cand: str, block: Block, mid: int, slug: str, dm_rel: str, catalog: Catalog | None,
               plan: list[dict[str, Any]]) -> tuple[Block, dict[str, Any]]:
    """Re-parse the candidate and confirm only the target block changed and each change took effect."""
    a, z = block.opener.start, block.end.end  # type: ignore[union-attr]
    tail = len(text) - z
    if cand[:a] != text[:a] or cand[len(cand) - tail:] != text[z:]:
        raise KosmoError("internal", "Edit touched text outside the selected block; nothing was written.")
    old_issues = len(parse(text).issues)
    pr2 = parse(cand)
    if len(pr2.issues) != old_issues:
        raise KosmoError("preflight_failed", "The edited file would gain syntax problems; nothing was written.")
    pr2, b2 = _find_block(cand, mid)
    rep = Report()
    for st in b2.statements:
        _check_statement("monster", st, rep, dm_rel, [], [])
    errors = [i for i in rep.of("error") if any(i["line"] == s.line for s in b2.statements
                                                 if s.raw.strip() in {p.get("after") for p in plan})]
    if errors:
        raise KosmoError("preflight_failed", "The edited commands fail the curated argument checks.",
                         problems=[i["message"] for i in errors][:10])
    res2 = _resolve_monster(_ctx(cand, slug, dm_rel, catalog, pr2), b2)
    for p in plan:
        if p["key"] in tr.TRAITS and p["key"] not in SCHEMA:
            t = tr.TRAITS[p["key"]]
            live, _dead, _last = _trait_lines(b2, t)
            if p["action"] in ("replace", "append") and not any(
                    tr.statement_args(t, s) == p["value"] and s.raw.strip() == p["after"].strip() for s in live):
                raise KosmoError("preflight_failed", f"{p['label']}: the edited file does not read back as "
                                                     f"{p['after']}; nothing was written.")
            if t.repeat is None and len(live) > 1:
                raise KosmoError("preflight_failed", f"{p['label']} would be duplicated; nothing was written.")
            p["effective_after"] = _trait_effective(res2, t.command, live)
            continue
        if p["action"] in ("replace", "append") and SCHEMA[p["key"]]["kind"] != "flag":
            live, _dead, _last = _live(b2, p["key"])
            if len(live) != 1 or _authored_value(p["key"], live[0]) != p["value"]:
                raise KosmoError("preflight_failed", f"{p['label']}: the edited file does not read back as "
                                                     f"{p['value']}; nothing was written.")
        p["effective_after"] = _effective(res2, p["key"])
    return b2, res2


# Check documented cross-field requirements on the candidate, including traits added in the same draft.
def _check_trait_dependencies(block: Block, resolved: dict[str, Any], changed: set[str]) -> None:
    r = resolved["resolved"]
    sacred = r["specials"].get("holy") or r["creature_traits"].get("holy") or {}
    priest = r["magic"]["paths"].get("H") or {}
    costs, _, _ = _trait_lines(block, tr.TRAITS["holycost"])
    if changed & {"holy", "holycost", "magic:9"} and (costs or priest.get("value", 0)):
        if not sacred.get("value") or sacred.get("status") == "unresolved":
            raise KosmoError("trait_prerequisite", "Holy magic and #holycost require #holy on this unit. "
                             "Add Sacred in the same draft, or remove the dependent ability.", field="holy")
    if changed & {"nofmounts", "nofriders"}:
        counts = {}
        donor = (resolved.get("donor") or {}).get("catalog_row") or {}
        for key in ("nofmounts", "nofriders"):
            live, _, reset = _trait_lines(block, tr.TRAITS[key])
            args = tr.statement_args(tr.TRAITS[key], live[-1]) if live else None
            if live and args is None:
                raise KosmoError("trait_prerequisite", f"#{key} has malformed arguments; fix that line first.", field=key)
            value = args[0] if args is not None else (1 if reset and reset.command != "copystats" else donor.get(key, 1))
            try:
                counts[key] = int(value or 1)
            except (TypeError, ValueError):
                counts[key] = 1
        if counts["nofmounts"] > 1 and counts["nofriders"] > 1:
            raise KosmoError("trait_prerequisite", "A unit cannot have multiple mounts and multiple riders "
                             "at the same time (manual p.30).", field="nofmounts")


def apply_edit(workspace: Path, slug: str, mid: int, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) - {"expected_sha256", "changes", "preview"}:
        raise KosmoError("bad_request", "Body must be {expected_sha256, changes, preview}.")
    sha = body.get("expected_sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
        raise KosmoError("bad_request", "expected_sha256 must be the 64-hex SHA-256 from the editor state.")
    preview = body.get("preview", False)
    if not isinstance(preview, bool):
        raise KosmoError("bad_request", "preview must be true or false.")
    raw = body.get("changes")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CHANGES:
        raise KosmoError("bad_request", f"changes must be a list of 1-{MAX_CHANGES} changes.")
    changes = [_check_change(c) for c in raw]
    keys = [(c[0], c[3]) for c in changes if c[1] != "add"]
    if len(set(keys)) != len(keys):
        raise KosmoError("bad_request", "Each field (or repeatable trait line) may appear only once per save.")
    project = open_project(workspace, slug)
    path = resolve_dm_target(project, None)
    data, text, _enc = read_dm(path)
    if sha256_bytes(data).lower() != sha.lower():
        raise KosmoError("sha_mismatch", "The .dm changed since the editor was opened. Reload to see the new "
                                         "version; your unsaved values are kept in the form.")
    dm_rel = project.rel(path)
    pr, b = _find_block(text, mid)
    res = _resolve_monster(_ctx(text, slug, dm_rel, catalog, pr), b)
    changes = _check_trait_values(changes, _refs(pr, catalog))
    cand, plan, blocked = plan_edit(text, b, res, changes)
    if blocked:
        raise KosmoError("edit_blocked", "Some changes cannot be made safely; nothing was written.", blocked=blocked)
    b2, _res2 = _preflight(text, cand, b, mid, slug, dm_rel, catalog, plan)
    _check_trait_dependencies(b2, _res2, {p["key"] for p in plan if p["action"] != "unchanged"})
    a, z = b.opener.start, b.end.end  # type: ignore[union-attr]
    old_block, new_block = text[a:z], cand[a:len(cand) - (len(text) - z)]
    diff = "\n".join(difflib.unified_diff(text.splitlines(), cand.splitlines(), fromfile=f"a/{dm_rel}",
                                          tofile=f"b/{dm_rel}", lineterm="", n=1))
    out: dict[str, Any] = {"project": slug, "id": mid, "preview": preview, "plan": plan, "diff": diff,
                           "changed": cand != text, "before_sha256": sha256_bytes(data)}
    if preview or cand == text:
        return {**out, "written": False}
    if text.count(old_block) != 1:
        raise KosmoError("not_editable", "The block text is not unique in the file, so it cannot be patched safely.")
    res_patch = apply_mod_patch(workspace, slug, sha, old=old_block, new=new_block)
    return {**out, "written": True, "after_sha256": res_patch["after_sha256"], "backup": res_patch["backup"]}
