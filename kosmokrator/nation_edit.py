"""Bounded in-place editor for one project nation block (#selectnation N), used by the local web browser.

Editable: identity (#name, #epithet, #era, #descr, #summary, #brief), fort recruitment (#addrecunit, #addreccom),
custom gods (#addgod), home realms (#homerealm), start sites (#startsite) and the start army (#startcom,
#startscout, #startunittype1/2 with #startunitnbrs1/2). Each change is a small text span inside the selected block:
an argument rewritten in place, one authored line deleted, or one new line inserted next to its group. Everything
else in the .dm (province defence, walls, flags, colours, AI and unknown commands, comments, order, newlines,
encoding) stays byte-for-byte as written. The candidate is re-parsed and read back, and the write goes through
project.apply_mod_patch (project lock, expected SHA-256, backup, lossless self-check). No ids are allocated.

Never generated: #clearnation, #clearrec, #clearsites, #cleargods or any other reset. Removing an entry is offered
only when deleting its authored line is known to remove it. Entries a vanilla nation may also inherit (no reset in
the block), duplicate live lines, malformed lines and lines an earlier reset already made ineffective are refused or
shown read-only. #homecom/#homemon lines on start sites (capital-only recruitment) are never touched here.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from .browse import ERA_NAMES, _cat_rows, _Ctx, build_project_model
from .catalog import Catalog
from .dmparse import Block, Statement, block_id, block_name, newline_style, parse
from .errors import KosmoError
from .project import apply_mod_patch, open_project, read_dm, resolve_dm_target, sha256_bytes
from .validate import Report, _check_statement

MAX_CHANGES = 64
MAX_START_SITES = 4
MAX_COUNT = 200  # Kosmokrator sanity bound for #startunitnbrs (the manual states only the default, 20)
REALM_NAMES = {1: "North", 2: "Celtic", 3: "Mediterranean", 4: "Far East", 5: "Middle East", 6: "Middle America",
               7: "Africa", 8: "India", 9: "Deeps", 10: "Default"}
# key -> (label, kind, max length). Identity lines are edited in place; new ones go right after #selectnation
# (or after the identity line that precedes them), before any reset, because the manual wants #name first.
IDENTITY: dict[str, tuple[str, str, int]] = {
    "name": ("Name", "str", 60), "epithet": ("Epithet", "str", 60), "era": ("Era", "int", 0),
    "descr": ("Lore / description", "str", 1999), "summary": ("Summary", "str", 1999), "brief": ("Brief", "str", 1999)}
ID_ORDER = list(IDENTITY)
# Lists of single-argument lines and the resets that end the effect of earlier lines (commands.py texts:
# #clearrec clears recruitment, #clearsites start sites, #clearnation/#cleargods the explicit god list,
# #clearnation the home realms and start sites). #clearnation does not clear recruitment.
LISTS: dict[str, dict[str, Any]] = {
    "troops": {"command": "addrecunit", "resets": ("clearrec",), "label": "Fort troops"},
    "commanders": {"command": "addreccom", "resets": ("clearrec",), "label": "Fort commanders"},
    "gods": {"command": "addgod", "resets": ("clearnation", "cleargods"), "label": "Custom gods"},
    "realms": {"command": "homerealm", "resets": ("clearnation",), "label": "Home realms"},
    "sites": {"command": "startsite", "resets": ("clearnation", "clearsites"), "label": "Start sites"},
}
LIST_ORDER = list(LISTS)
SQUADS = {"squad1": ("startunittype1", "startunitnbrs1"), "squad2": ("startunittype2", "startunitnbrs2")}
START_CMDS = ("startcom", "startscout", "startunittype1", "startunitnbrs1", "startunittype2", "startunitnbrs2")
START_FIELDS = ("startcom", "startscout", "squad1", "squad2")
FIELDS = ID_ORDER + LIST_ORDER + list(START_FIELDS)


def _group(cmd: str) -> str | None:
    """The editable field a command belongs to (start-army commands share one group)."""
    if cmd in IDENTITY:
        return cmd
    for k, v in LISTS.items():
        if v["command"] == cmd:
            return k
    return "start" if cmd in START_CMDS else None


# ---------- reading the block ----------
def _find_block(text: str, nid: int) -> tuple[Any, Block]:
    pr = parse(text)
    hits = [b for b in pr.blocks if b.context == "nation" and b.opener.command == "selectnation" and block_id(b) == nid]
    if not hits:
        raise KosmoError("object_missing", f"No #selectnation {nid} block in this project.")
    if len(hits) > 1:
        raise KosmoError("ambiguous_block", f"Nation {nid} is selected by {len(hits)} blocks; edit the source instead.",
                         lines=[b.opener.line for b in hits])
    b = hits[0]
    name = block_name(b)
    by_name = [x.opener.line for x in pr.blocks if x is not b and x.context == "nation"
               and isinstance(block_id(x), str) and name and str(block_id(x)).lower() == name.lower()]
    if by_name:
        raise KosmoError("ambiguous_block", "Another nation block selects this nation by name; edit the source instead.",
                         lines=by_name)
    if b.end is None:
        raise KosmoError("not_editable", "This nation block is not closed with #end.", lines=[b.opener.line])
    if text[text.rfind("\n", 0, b.end.start) + 1:b.end.start].strip():
        raise KosmoError("not_editable", "#end does not start its own line.", lines=[b.end.line])
    if text[text.rfind("\n", 0, b.opener.start) + 1:b.opener.start].strip():
        raise KosmoError("not_editable", "#selectnation does not start its own line.", lines=[b.opener.line])
    bad = [i for i in pr.issues if b.opener.line <= i["line"] <= b.end.line]
    if bad:
        raise KosmoError("not_editable", "The nation block has syntax problems; fix them in the source first.",
                         lines=[i["line"] for i in bad])
    return pr, b


def _ctx(text: str, slug: str, rel: str, catalog: Catalog | None, pr: Any) -> _Ctx:
    c = _Ctx(slug, rel, text.splitlines(), catalog, None)
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
    return c


def _single(st: Statement) -> Any:
    return st.args[0].value if len(st.args) == 1 else None


def _list_lines(b: Block, field: str) -> tuple[list[Statement], list[Statement], Statement | None]:
    cfg = LISTS[field]
    last = None
    for st in b.statements:
        if st.command in cfg["resets"]:
            last = st
    sts = [s for s in b.statements if s.command == cfg["command"]]
    return ([s for s in sts if last is None or s.start > last.start],
            [s for s in sts if last is not None and s.start < last.start], last)


def _start_lines(b: Block) -> tuple[dict[str, list[Statement]], list[Statement], Statement | None]:
    """Live start-army lines. Per the manual #startcom also removes the start army set before it."""
    coms = [s for s in b.statements if s.command == "startcom"]
    last = coms[-1] if coms else None
    live = {c: [s for s in b.statements if s.command == c and (last is None or s.start > last.start)]
            for c in START_CMDS[1:]}
    live["startcom"] = coms
    dead = [s for s in b.statements if s.command in START_CMDS[1:] and last is not None and s.start < last.start]
    return live, dead, last


def _vanilla(nid: int, catalog: Catalog | None) -> bool:
    """A nation that may inherit vanilla settings: below 150 (manual: 150+ creates new nations) or in the catalog."""
    return nid < 150 or bool(_cat_rows(catalog, "nations").get(str(nid)))


def _ref(c: _Ctx, field: str, v: Any) -> dict[str, Any]:
    if field == "realms":
        return {"label": f"{v} {REALM_NAMES.get(v, '(unknown realm)')}" if isinstance(v, int) else str(v)}
    r = c.ref_site(v) if field == "sites" else c.ref_monster(v)
    return {**r, "label": f"{r.get('name') or r.get('ref')}" + (f" (#{r['id']})" if r.get("id") is not None else "")}


def _read_state(text: str, b: Block, c: _Ctx, vanilla: bool) -> dict[str, Any]:
    """Identity, lists and start army as written: live lines, read-only dead lines and per-entry removability."""
    ident: dict[str, Any] = {}
    for k, (label, kind, lim) in IDENTITY.items():
        sts = [s for s in b.statements if s.command == k]
        e: dict[str, Any] = {"label": label, "kind": kind, "max": lim or None, "value": None, "line": None,
                             "lines": [s.line for s in sts]}
        if len(sts) > 1:
            e["blocked"] = f"#{k} appears {len(sts)} times (lines {', '.join(str(s.line) for s in sts)}); fix the source first."
        elif sts:
            v = _single(sts[0])
            if v is None or sts[0].args[0].kind != kind:
                e["blocked"] = f"Line {sts[0].line} ({sts[0].raw.strip()[:60]}) does not have the expected argument."
            else:
                e.update(value=v, line=sts[0].line, multiline=isinstance(v, str) and "\n" in v)
        ident[k] = e
    lists: dict[str, Any] = {}
    for field, cfg in LISTS.items():
        live, dead, last = _list_lines(b, field)
        inherited = vanilla and last is None
        keys = [s.args[0].raw if len(s.args) == 1 else None for s in live]
        items = []
        for s, key in zip(live, keys):
            v = _single(s)
            it: dict[str, Any] = {"key": key, "line": s.line, "raw": s.raw.strip(), "value": v, **_ref(c, field, v)}
            project = it.get("origin") == "project"
            if key is None or (field == "realms" and not isinstance(v, int)):
                it["reason"] = "Malformed line (expected one argument); edit the source."
            elif keys.count(key) > 1:
                it["reason"] = (f"Listed {keys.count(key)} times after the last reset; deleting one line would not remove "
                                "it. Fix the duplicates in the source first.")
            elif inherited and not project:
                reset = "/".join("#" + r for r in cfg["resets"])
                it["reason"] = (f"This vanilla nation may also inherit this entry (no {reset} in the block), so deleting "
                                "the line is not known to remove it. Kosmokrator never adds resets.")
            it["removable"] = "reason" not in it
            items.append(it)
        lists[field] = {
            "label": cfg["label"], "command": f"#{cfg['command']}", "resets": [f"#{r}" for r in cfg["resets"]],
            "last_reset": {"command": f"#{last.command}", "line": last.line} if last else None,
            "inherited": inherited, "live": items,
            "dead": [{"line": s.line, "raw": s.raw.strip(),
                      "note": f"already cleared by #{last.command} on line {last.line}"} for s in dead]}  # type: ignore[union-attr]
    live, dead, last = _start_lines(b)

    def one(cmd: str) -> dict[str, Any]:
        sts = live[cmd]
        e: dict[str, Any] = {"command": f"#{cmd}", "lines": [s.line for s in sts], "value": None, "key": None}
        if len(sts) > 1:
            e["blocked"] = f"#{cmd} appears {len(sts)} times (lines {', '.join(str(s.line) for s in sts)}); fix the source first."
        elif sts:
            v = _single(sts[0])
            if v is None:
                e["blocked"] = f"Line {sts[0].line} does not have exactly one argument."
            else:
                e.update(value=v, key=sts[0].args[0].raw, line=sts[0].line, raw=sts[0].raw.strip())
                if cmd.startswith("startunitnbrs"):
                    if not isinstance(v, int):
                        e["blocked"] = f"Line {sts[0].line} has no whole-number count."
                else:
                    e["ref"] = _ref(c, "troops", v)
        return e
    start = {"startcom": one("startcom"), "startscout": one("startscout"),
             **{k: {"type": one(t), "count": one(n)} for k, (t, n) in SQUADS.items()},
             "inherited": vanilla and last is None,
             "dead": [{"line": s.line, "raw": s.raw.strip(), "note": f"cleared by #startcom on line {last.line}"}  # type: ignore[union-attr]
                      for s in dead]}
    return {"identity": ident, "lists": lists, "start": start}


def _load(workspace: Path, slug: str, nid: int, catalog: Catalog | None) -> dict[str, Any]:
    project = open_project(workspace, slug)
    path = resolve_dm_target(project, None)
    data, text, enc = read_dm(path)
    rel = project.rel(path)
    pr, b = _find_block(text, nid)
    return {"project": project, "path": path, "data": data, "text": text, "enc": enc, "rel": rel, "pr": pr, "b": b,
            "c": _ctx(text, slug, rel, catalog, pr), "vanilla": _vanilla(nid, catalog)}


def _options(m: dict[str, Any]) -> dict[str, Any]:
    def god(x: dict[str, Any]) -> bool:
        g = x["resolved"]["god"]
        return g["startdom"]["value"] is not None and g["pathcost"]["value"] is not None
    mons = [x for x in m["monsters"] if x.get("new") and isinstance(x.get("id"), int)]
    return {"units": [{"id": x["id"], "name": x["name"], "role": x["role"], "god": god(x)} for x in mons],
            "sites": [{"id": s["id"], "name": s["name"], "start_site_of": s["start_site_of"]} for s in m["sites"]
                      if s.get("new") and isinstance(s.get("id"), int) and s.get("name") and '"' not in s["name"]],
            "realms": REALM_NAMES}


def _capital_roster(m: dict[str, Any], nid: int) -> list[dict[str, Any]]:
    """Derived, read-only: #homecom/#homemon/#com/#mon on this nation's project start sites."""
    uid = f"nation:{nid}"
    return [{"site": {"id": s["id"], "uid": s["uid"], "name": s["name"], "line": s["source"]["line"]},
             "units": s["units"], "shared_with": [x for x in s["start_site_of"] if x != uid]}
            for s in m["sites"] if uid in s["start_site_of"]]


def editor_state(workspace: Path, slug: str, nid: int, catalog: Catalog | None) -> dict[str, Any]:
    """Everything the nation form needs: current SHA-256, fields as written, options and derived context."""
    ld = _load(workspace, slug, nid, catalog)
    sha = sha256_bytes(ld["data"])
    m = build_project_model(workspace, slug, catalog)
    if m["provenance"]["sha256"] != sha:
        raise KosmoError("sha_mismatch", "The .dm changed while the editor was reading it. Reload.")
    b = ld["b"]
    row = _cat_rows(catalog, "nations").get(str(nid)) or {}
    return {"project": slug, "id": nid, "uid": f"nation:{nid}", "file": ld["rel"], "sha256": sha,
            "encoding": ld["enc"], "line": b.opener.line, "end_line": b.end.line,
            "basis": ("vanilla nation: settings without a reset in this block may also be inherited"
                      if ld["vanilla"] else "new nation (150+): nothing is inherited from a vanilla nation"),
            "vanilla": ld["vanilla"],
            "catalog": {"name": row.get("name"), "epithet": row.get("epithet"), "era": row.get("era")} if row else None,
            "resets": [{"command": f"#{s.command}", "line": s.line} for s in b.statements
                       if s.command in ("clearnation", "clearrec", "clearsites", "cleargods")],
            **_read_state(ld["text"], b, ld["c"], ld["vanilla"]),
            "options": _options(m), "capital_roster": _capital_roster(m, nid),
            "era_names": ERA_NAMES, "max_start_sites": MAX_START_SITES, "max_count": MAX_COUNT,
            "limits": ["Only the listed commands change; defence, walls, flags, colours, AI and unknown commands, "
                       "comments, order, newlines and encoding stay as written.",
                       "Kosmokrator never adds #clearnation, #clearrec, #clearsites or #cleargods. Entries a vanilla "
                       "nation may inherit cannot be removed here.",
                       "#homecom/#homemon on start sites (capital-only recruitment) are edited on the site, not here.",
                       "Static checks only; test in Dominions 6."]}


# ---------- checking a request ----------
def _text_value(key: str, v: Any) -> str:
    label, _kind, lim = IDENTITY[key]
    if not isinstance(v, str) or not v.strip():
        raise KosmoError("bad_value", f"{label} must be non-empty text.", field=key)
    v = v.strip()
    if '"' in v or "#" in v or any(ch in v for ch in "\r\n\t\x00") or len(v) > lim:
        raise KosmoError("bad_value", f"{label}: at most {lim} characters without double quotes, '#', tabs or line "
                                      "breaks.", field=key)
    return v


def _int_value(v: Any, lo: int, hi: int, field: str, what: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise KosmoError("bad_value", f"{what} must be a whole number {lo}-{hi}.", field=field)
    return v


def _check_change(ch: Any) -> tuple[str, str, Any]:
    if not isinstance(ch, dict) or set(ch) - {"field", "op", "value"}:
        raise KosmoError("bad_change", "Each change is an object with field, op and value only.")
    field, op, v = ch.get("field"), ch.get("op"), ch.get("value")
    if not isinstance(field, str) or field not in FIELDS:
        raise KosmoError("unsupported_field", f"{str(field)[:40]!r} is not an editable nation field.", field=str(field)[:40])
    if field in IDENTITY:
        if op != "set":
            raise KosmoError("bad_change", "Identity fields can only be set.", field=field)
        return field, op, (_int_value(v, 1, 3, field, "Era") if field == "era" else _text_value(field, v))
    if field in LISTS:
        if op == "add":
            return field, op, _int_value(v, 1, 10, field, "Realm") if field == "realms" else \
                _int_value(v, 1, 99999, field, "The id")
        if op == "remove":
            if not isinstance(v, str) or not 0 < len(v) <= 200:
                raise KosmoError("bad_value", "remove takes the entry's key as shown by the editor.", field=field)
            return field, op, v
        raise KosmoError("bad_change", "List fields take op 'add' or 'remove'.", field=field)
    if op == "remove":
        if v is not None:
            raise KosmoError("bad_change", "A remove change takes no value.", field=field)
        return field, op, None
    if op != "set":
        raise KosmoError("bad_change", "op must be 'set' or 'remove'.", field=field)
    if field in SQUADS:
        if not isinstance(v, dict) or set(v) != {"unit", "count"}:
            raise KosmoError("bad_value", "A squad is {unit, count}.", field=field)
        unit = v["unit"]
        if not ((isinstance(unit, int) and not isinstance(unit, bool) and 0 < unit <= 99999)
                or (isinstance(unit, str) and 0 < len(unit) <= 200)):
            raise KosmoError("bad_value", "Squad unit must be a project unit id (or the current entry).", field=field)
        return field, op, {"unit": unit, "count": _int_value(v["count"], 1, MAX_COUNT, field, "Squad size")}
    return field, op, _int_value(v, 1, 99999, field, "The unit id")


# ---------- planning text spans ----------
class _Spans:
    def __init__(self, text: str, b: Block) -> None:
        self.text = text
        self.items: list[tuple[int, int, tuple[int, ...], str]] = []
        end_ls = text.rfind("\n", 0, b.end.start) + 1  # type: ignore[union-attr]
        self.end_ls = end_ls
        style = newline_style(text)
        self.nl = "\r\n" if style == "crlf" or (style == "mixed" and text[max(0, end_ls - 2):end_ls] == "\r\n") else "\n"

    def line_bounds(self, st: Statement) -> tuple[int, int, int]:
        t = self.text
        ls = t.rfind("\n", 0, st.start) + 1
        le = t.find("\n", st.end)
        le = len(t) if le == -1 else le
        lr = le - 1 if le > 0 and t[le - 1] == "\r" else le
        return ls, lr, min(le + 1, len(t))

    def after(self, st: Statement) -> int:
        return self.line_bounds(st)[2]

    def before(self, st: Statement) -> int:
        return self.line_bounds(st)[0]

    def insert(self, pos: int, line: str, order: tuple[int, ...]) -> None:
        self.items.append((pos, pos, order, line + self.nl))

    def replace_arg(self, st: Statement, rep: str) -> str:
        a = st.start + st.raw.rfind(st.args[-1].raw)
        z = a + len(st.args[-1].raw)
        self.items.append((a, z, (0,), rep))
        return st.raw[:a - st.start] + rep + st.raw[z - st.start:]

    def delete(self, st: Statement) -> None:
        ls, lr, le = self.line_bounds(st)
        if self.text[ls:st.start].strip() or self.text[st.end:lr].strip():
            self.items.append((st.start, st.end, (0,), ""))  # keep a trailing comment on its own
        else:
            self.items.append((ls, le, (0,), ""))

    def apply(self) -> str:
        ranges = sorted((a, z) for a, z, _o, _r in self.items if z > a)
        for (a1, z1), (a2, _z2) in zip(ranges, ranges[1:]):
            if a2 < z1:
                raise KosmoError("internal", "Overlapping edits were planned; nothing was written.")
        out = self.text
        for a, z, _o, rep in sorted(self.items, key=lambda s: (s[0], s[1], s[2]), reverse=True):
            out = out[:a] + rep + out[z:]
        return out


def _plan(ld: dict[str, Any], state: dict[str, Any], m: dict[str, Any],
          changes: list[tuple[str, str, Any]]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """(candidate text, plan, blocked, expected read-back) for the requested changes."""
    text, b, c = ld["text"], ld["b"], ld["c"]
    sp = _Spans(text, b)
    plan: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    opts = _options(m)
    units = {u["id"]: u for u in opts["units"]}
    sites = {s["id"]: s for s in opts["sites"]}
    expect: dict[str, Any] = {}
    first_reset = next((s for s in b.statements if s.command in ("clearnation", "clearrec", "clearsites", "cleargods")),
                       None)

    def block(item: dict[str, Any], reason: str, lines: list[int] | None = None) -> None:
        blocked.append({**item, "reason": reason, **({"lines": lines} if lines else {})})

    # Identity
    for field, op, value in [c_ for c_ in changes if c_[0] in IDENTITY]:
        e = state["identity"][field]
        item = {"field": field, "label": e["label"], "op": op, "value": value}
        if e.get("blocked"):
            block(item, e["blocked"], e["lines"])
            continue
        rendered = str(value) if field == "era" else f'"{value}"'
        expect[field] = value
        if e["line"] is not None:
            if e["value"] == value:
                plan.append({**item, "action": "unchanged", "line": e["line"], "explanation": f"Already set on line {e['line']}."})
                continue
            st = next(s for s in b.statements if s.command == field)
            after = sp.replace_arg(st, rendered)
            plan.append({**item, "action": "replace", "line": st.line, "before": _short(st.raw.strip()),
                         "after": _short(after.strip()), "explanation": f"Rewrites the argument on line {st.line} only; "
                         "its position (before or after resets) is kept."})
            continue
        idx = ID_ORDER.index(field)
        prev = [s for s in b.statements if s.command in ID_ORDER[:idx]
                and (first_reset is None or s.start < first_reset.start)]
        anchor = max(prev, key=lambda s: s.start) if prev else b.opener
        sp.insert(sp.after(anchor), f"#{field} {rendered}", (1, idx))
        where = f"#{anchor.command} on line {anchor.line}"
        plan.append({**item, "action": "add", "after": _short(f"#{field} {rendered}"),
                     "explanation": f"Not written yet; added after {where}, before any reset, because the manual "
                                    "wants #name first and #era right after #name/#epithet."})
    # Lists
    for field in LIST_ORDER:
        mine = [c_ for c_ in changes if c_[0] == field]
        if not mine:
            continue
        cfg, ls = LISTS[field], state["lists"][field]
        live_sts, _dead, _last = _list_lines(b, field)
        by_key = {it["key"]: it for it in ls["live"]}
        result = [it["key"] for it in ls["live"]]
        anchor_pos = sp.after(live_sts[-1]) if live_sts else sp.end_ls
        n_add = 0
        for _f, op, value in mine:
            item = {"field": field, "label": cfg["label"], "op": op, "value": value}
            if op == "remove":
                it = by_key.get(value)
                if it is None:
                    block(item, f"{value} is not an authored, live #{cfg['command']} line of this nation, so there is "
                                "nothing to delete." + (" Entries before a reset are already ineffective." if ls["dead"] else ""))
                    continue
                if not it["removable"]:
                    block(item, it["reason"], [it["line"]])
                    continue
                st = next(s for s in live_sts if s.line == it["line"])
                sp.delete(st)
                result.remove(value)
                plan.append({**item, "action": "remove", "line": st.line, "before": st.raw.strip(),
                             "label_value": it.get("label"),
                             "explanation": f"Deletes line {st.line} only. Nothing else lists it after the last reset, "
                                            "so it is no longer in this list."
                                            + (" (A new nation: nothing is inherited.)" if not ld["vanilla"] else "")})
                continue
            # add
            if field == "realms":
                rendered, label = str(value), f"{value} {REALM_NAMES[value]}"
                present = any(it["value"] == value for it in ls["live"])
            elif field == "sites":
                s = sites.get(value)
                if s is None:
                    block(item, f"Site {value} is not a named #newsite in this project.")
                    continue
                rendered, label = f'"{s["name"]}"', f'{s["name"]} (#{value})'
                present = any(it.get("id") == value or str(it["value"]).lower() == s["name"].lower() for it in ls["live"])
            else:
                u = units.get(value)
                if u is None or (field == "gods" and not u["god"]):
                    block(item, f"{value} is not a project " + ("custom god (needs #startdom and #pathcost)."
                                                                if field == "gods" else "#newmonster."))
                    continue
                rendered, label = str(value), f'{u["name"]} (#{value})'
                present = any(it["value"] == value or it.get("id") == value for it in ls["live"])
            if present:
                plan.append({**item, "action": "unchanged", "label_value": label, "explanation": "Already listed."})
                continue
            n_add += 1
            line = f"#{cfg['command']} {rendered}"
            sp.insert(anchor_pos, line, (2, LIST_ORDER.index(field), n_add))
            result.append(rendered)
            plan.append({**item, "action": "add", "after": line, "label_value": label,
                         "explanation": ("Added after the last live " if live_sts else "Added just before #end, after ")
                                        + (f"#{cfg['command']} line." if live_sts else "every reset.")})
        if field == "sites" and len(result) > MAX_START_SITES:
            block({"field": field, "label": cfg["label"], "op": "add", "value": None},
                  f"That would list {len(result)} start sites; the manual allows at most {MAX_START_SITES}.")
        expect[field] = result
    # Start army
    st_state = state["start"]
    live, dead, last = _start_lines(b)
    starts = [c_ for c_ in changes if c_[0] in START_FIELDS]
    first_start = min((s for k in START_CMDS[1:] for s in live[k]), key=lambda s: s.start, default=None)
    last_start = max((s for k in START_CMDS for s in live[k]), key=lambda s: s.start, default=None)
    start_anchor = sp.after(last_start) if last_start is not None else sp.end_ls
    exp_start = {"startcom": st_state["startcom"]["key"], "startscout": st_state["startscout"]["key"],
                 **{k: (st_state[k]["type"]["key"], st_state[k]["count"]["value"]) for k in SQUADS}}
    for field, op, value in starts:
        label = {"startcom": "Starting commander", "startscout": "Scout", "squad1": "Start squad 1",
                 "squad2": "Start squad 2"}[field]
        item = {"field": field, "label": label, "op": op, "value": value}
        parts = [st_state[field]] if field in ("startcom", "startscout") else [st_state[field]["type"], st_state[field]["count"]]
        bad = [p for p in parts if p.get("blocked")]
        if bad:
            block(item, bad[0]["blocked"], bad[0]["lines"])
            continue
        cur_sts = [s for p in parts for s in (live[p["command"][1:]] or [])]
        if op == "remove":
            if not cur_sts:
                block(item, "Nothing authored to remove" + (" (a vanilla start army may still apply)." if st_state["inherited"] else "."))
                continue
            if st_state["inherited"] or (field == "startcom" and ld["vanilla"]):
                block(item, "This vanilla nation may inherit its start army (no authored #startcom clears it), so "
                            "deleting the line is not known to remove it.", [s.line for s in cur_sts])
                continue
            if field == "startcom" and dead:
                block(item, "Removing #startcom would make the start-army lines before it effective again (lines "
                            f"{', '.join(str(s.line) for s in dead)}). Edit the source instead.", [s.line for s in dead])
                continue
            for s in cur_sts:
                sp.delete(s)
            exp_start[field] = None if field in ("startcom", "startscout") else (None, None)
            plan.append({**item, "action": "remove", "line": cur_sts[0].line,
                         "before": " / ".join(s.raw.strip() for s in cur_sts),
                         "explanation": "Deletes the authored line(s). " + ("With no #startcom what the game does "
                                        "is not verified; set one before testing." if field == "startcom" else
                                        "No other live line sets it.")})
            continue
        unit = value["unit"] if field in SQUADS else value
        cur_key = parts[0]["key"]
        if not (isinstance(unit, int) and unit in units) and str(unit) != str(cur_key):
            block(item, f"{unit} is not a #newmonster of this project (the current entry may be kept as it is).")
            continue
        new_key = str(unit) if isinstance(unit, int) and str(unit) != str(cur_key) else cur_key
        if field in ("startcom", "startscout"):
            exp_start[field] = new_key
            if cur_key is not None and str(cur_key) == str(new_key):
                plan.append({**item, "action": "unchanged", "line": parts[0]["line"], "explanation": "Already set."})
                continue
            if cur_sts:
                after = sp.replace_arg(cur_sts[0], str(unit))
                plan.append({**item, "action": "replace", "line": cur_sts[0].line, "before": cur_sts[0].raw.strip(),
                             "after": after.strip(), "explanation": f"Rewrites the argument on line {cur_sts[0].line}."})
                continue
            line = f"#{field} {unit}"
            if field == "startcom":
                pos = sp.before(first_start) if first_start is not None else sp.end_ls
                sp.insert(pos, line, (3, 0))
                why = ("Added before the first start-army line, so it does not clear it (the manual: #startcom removes "
                       "the start army set before it)." if first_start is not None else "Added just before #end.")
            else:
                sp.insert(start_anchor, line, (3, 1))
                why = "Added after the last start-army line."
            plan.append({**item, "action": "add", "after": line, "explanation": why})
            continue
        # squads
        tcmd, ncmd = SQUADS[field]
        t_e, n_e = st_state[field]["type"], st_state[field]["count"]
        exp_start[field] = (new_key, value["count"])
        t_sts, n_sts = live[tcmd], live[ncmd]
        if t_sts and str(t_e["key"]) == str(new_key) and n_sts and n_e["value"] == value["count"]:
            plan.append({**item, "action": "unchanged", "line": t_sts[0].line, "explanation": "Already set."})
            continue
        before = " / ".join(s.raw.strip() for s in t_sts + n_sts)
        afters = []
        slot = 2 + 2 * (int(field[-1]) - 1)
        if t_sts:
            afters.append(sp.replace_arg(t_sts[0], str(unit)).strip() if str(t_e["key"]) != str(new_key) else t_sts[0].raw.strip())
        if n_sts:
            afters.append(sp.replace_arg(n_sts[0], str(value["count"])).strip() if n_e["value"] != value["count"] else n_sts[0].raw.strip())
        if t_sts and not n_sts:
            sp.insert(sp.after(t_sts[0]), f"#{ncmd} {value['count']}", (3, slot + 1))
            afters.append(f"#{ncmd} {value['count']}")
        elif n_sts and not t_sts:
            sp.insert(sp.before(n_sts[0]), f"#{tcmd} {unit}", (3, slot))
            afters.insert(0, f"#{tcmd} {unit}")
        elif not t_sts:
            sp.insert(start_anchor, f"#{tcmd} {unit}", (3, slot))
            sp.insert(start_anchor, f"#{ncmd} {value['count']}", (3, slot + 1))
            afters = [f"#{tcmd} {unit}", f"#{ncmd} {value['count']}"]
        plan.append({**item, "action": "replace" if before else "add", "before": before or None, "after": " / ".join(afters),
                     "explanation": "Rewrites the existing squad lines in place." if before else
                     "Added after the last start-army line."})
    if starts:
        expect["start"] = exp_start
    return sp.apply(), plan, blocked, expect


def _short(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


# ---------- read-back ----------
def _signature(b: Block) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for st in b.statements:
        out.setdefault(_group(st.command) or "other", []).append((st.command, st.raw))
    return out


def _preflight(ld: dict[str, Any], cand: str, nid: int, expect: dict[str, Any], changes: list[tuple[str, str, Any]],
               plan: list[dict[str, Any]]) -> None:
    text, b = ld["text"], ld["b"]
    a, z = b.opener.start, b.end.end  # type: ignore[union-attr]
    tail = len(text) - z
    if cand[:a] != text[:a] or cand[len(cand) - tail:] != text[z:]:
        raise KosmoError("internal", "Edit touched text outside the nation block; nothing was written.")
    if len(parse(cand).issues) != len(ld["pr"].issues):
        raise KosmoError("preflight_failed", "The edited file would gain syntax problems; nothing was written.")
    try:
        cand.encode(ld["enc"])
    except UnicodeEncodeError as exc:
        raise KosmoError("encoding", f"The new text cannot be written in the file's {ld['enc']} encoding.") from exc
    _pr2, b2 = _find_block(cand, nid)
    old_sig, new_sig = _signature(b), _signature(b2)
    touched = {f if f in IDENTITY or f in LISTS else "start" for f, _o, _v in changes}
    for g in set(old_sig) | set(new_sig):
        if g not in touched and old_sig.get(g, []) != new_sig.get(g, []):
            raise KosmoError("preflight_failed", f"Lines outside the requested fields changed ({g}); nothing was written.")
    old_raws = {s.raw for s in b.statements}
    rep = Report()
    for st in b2.statements:
        if st.raw not in old_raws:
            _check_statement("nation", st, rep, ld["rel"], [], [])
    if rep.of("error"):
        raise KosmoError("preflight_failed", "The edited commands fail the curated argument checks.",
                         problems=[i["message"] for i in rep.of("error")][:10])
    st2 = _read_state(cand, b2, ld["c"], ld["vanilla"])
    for k in IDENTITY:
        if k in expect and st2["identity"][k]["value"] != expect[k]:
            raise KosmoError("preflight_failed", f"{IDENTITY[k][0]} does not read back as requested; nothing was written.")
    for k in LISTS:
        if k in expect:
            got = sorted(str(it["key"]) for it in st2["lists"][k]["live"])
            if got != sorted(str(x) for x in expect[k]):
                raise KosmoError("preflight_failed", f"{LISTS[k]['label']} do not read back as requested; nothing was written.")
    if "start" in expect:
        s2 = st2["start"]
        got = {"startcom": s2["startcom"]["key"], "startscout": s2["startscout"]["key"],
               **{k: (s2[k]["type"]["key"], s2[k]["count"]["value"]) for k in SQUADS}}
        norm = lambda d: {k: (tuple(str(x) if x is not None else None for x in v) if isinstance(v, tuple)  # noqa: E731
                              else (str(v) if v is not None else None)) for k, v in d.items()}
        if norm(got) != norm(expect["start"]):
            raise KosmoError("preflight_failed", "The start army does not read back as requested; nothing was written.")


def apply_nation_edit(workspace: Path, slug: str, nid: int, catalog: Catalog | None, body: Any) -> dict[str, Any]:
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
    changes = [_check_change(ch) for ch in raw]
    singles = [f for f, _o, _v in changes if f not in LISTS]
    if len(set(singles)) != len(singles):
        raise KosmoError("bad_request", "Each identity or start-army field may appear only once per save.")
    pairs = [(f, repr(v)) for f, _o, v in changes if f in LISTS]
    if len(set(pairs)) != len(pairs):
        raise KosmoError("bad_request", "Each list entry may be added or removed only once per save.")
    ld = _load(workspace, slug, nid, catalog)
    if sha256_bytes(ld["data"]).lower() != sha.lower():
        raise KosmoError("sha_mismatch", "The .dm changed since the editor was opened. Reload to see the new version; "
                                         "your unsaved choices are kept in the form.")
    m = build_project_model(workspace, slug, catalog)
    if m["provenance"]["sha256"].lower() != sha.lower():
        raise KosmoError("sha_mismatch", "The .dm changed while reading it. Reload; your choices are kept.")
    state = _read_state(ld["text"], ld["b"], ld["c"], ld["vanilla"])
    cand, plan, blocked, expect = _plan(ld, state, m, changes)
    if blocked:
        raise KosmoError("edit_blocked", "Some changes cannot be made safely; nothing was written.", blocked=blocked)
    if cand != ld["text"]:
        _preflight(ld, cand, nid, expect, changes, plan)
    text, b, rel = ld["text"], ld["b"], ld["rel"]
    diff = "\n".join(difflib.unified_diff(text.splitlines(), cand.splitlines(), fromfile=f"a/{rel}", tofile=f"b/{rel}",
                                          lineterm="", n=1))
    out: dict[str, Any] = {"project": slug, "id": nid, "preview": preview, "plan": plan, "diff": diff,
                           "changed": cand != text, "before_sha256": sha256_bytes(ld["data"])}
    if preview or cand == text:
        return {**out, "written": False}
    a, z = b.opener.start, b.end.end  # type: ignore[union-attr]
    old_block, new_block = text[a:z], cand[a:len(cand) - (len(text) - z)]
    if text.count(old_block) != 1:
        raise KosmoError("not_editable", "The nation block text is not unique in the file, so it cannot be patched safely.")
    res = apply_mod_patch(workspace, slug, sha, old=old_block, new=new_block)
    return {**out, "written": True, "after_sha256": res["after_sha256"], "backup": res["backup"]}
