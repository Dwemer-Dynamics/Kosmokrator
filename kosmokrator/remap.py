"""Reviewed ID remapping: move project-owned numbered definitions to new IDs with every typed reference.

The project's own definitions are the only remappable identities: #newmonster/#newsite/#newweapon/#newarmor <id> in
the project .dm, and #selectnation 150+ (which creates a new nation, p.41) when neither the catalog nor a declared
dependency defines that nation. Selectors of vanilla or external objects are never treated as owned.

A plan is built from one captured project revision (revisions.py) and one external occupancy scan (catalog, declared
dependencies, other workspace projects with their reservations, installed mods). Every number in every owned .dm and
.map file is classified by its typed command argument (commands.py / manual_commands.py / mapformat.py):

* a typed reference of the remapped kind is rewritten (only that argument token; every other byte is kept);
* a typed argument of another kind or a typed non-reference value is kept (namespaces never mix);
* spell #damage is a monster only when the effect is a documented summon (an authored #effect, or the catalog
  template of #copyspell / #selectspell); otherwise a matching value blocks the plan for manual review;
* an untyped argument, an unknown command, a quoted number in a reference position, a number inside an untyped
  string, #startsite with a number, or a map monster/site reference (not proven by the map schema) blocks the plan.

Names are not changed, so name-based references stay valid. Text arguments (names, descriptions) are kept byte for
byte. Preview writes nothing and reserves nothing. Apply needs the exact mapping, the previewed current revision,
occupancy fingerprint and plan hash plus confirm; it rebuilds the plan under the project lock (rescanning external
occupancy immediately before writing), stores a complete pre-remap checkpoint, rewrites each file with a backup and
a hash check, appends reservations for the new IDs (old reservations are kept) and reverts the files if the metadata
cannot be saved. Files outside the project (dependencies, other projects, installed mods) are never changed.
"""

from __future__ import annotations

import copy
import datetime as _dt
import difflib
import json
import random
import re
from pathlib import Path
from typing import Any

from . import commands as cmdreg
from . import project as proj
from . import revisions as rev
from .dmparse import Statement, block_id, block_name, decode_dm, newline_style, parse
from .errors import KosmoError
from .mapformat import COMMANDS as MAP_COMMANDS
from .paths import atomic_write_bytes, contained
from .project import ID_KINDS, META_FILE, Project, open_project, project_lock, sha256_bytes

SCHEMA = "kosmokrator.remap/1"
PLAN_SCHEMA = "kosmokrator.remap-plan/1"
KINDS = ("monster", "site", "nation", "weapon", "armor")
CUSTOM_NATION_MIN = 150
MAX_MAPPING = 20
MAX_LISTED = 500
MAX_DIFF_LINES = 600
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# Typed argument -> ID kind. Item and spell references are by name and are not remapped.
REF_KIND = {"mon": "monster", "monid": "monster", "monneg": "monster", "site": "site", "sitename": "site",
            "weapon": "weapon", "armor": "armor", "nation": "nation", "nationref": "nation"}
# Plain int arguments the manual index names as numbered identities (event site commands, p.13).
INT_ID_ARGS = {"site_number": "site"}
NEW_OPENERS = {"newmonster": "monster", "newsite": "site", "newweapon": "weapon", "newarmor": "armor"}
SELECT_OPENERS = {"selectmonster": "monster", "selectsite": "site", "selectweapon": "weapon",
                  "selectarmor": "armor", "selectnation": "nation"}
# Map commands whose numbers are never identities (#pb: x, y, length, province; file format manual).
MAP_NON_REF = {"pb"}
OWN_DEF, OWN_REF = "this project (definition)", "this project (reference)"
MAP_REF_KIND = {"commander": "monster", "units": "monster", "bodyguards": "monster", "god": "monster",
                "feature": "site", "knownfeature": "site"}

LIMITATIONS = [
    "Only this project's files change. Dependencies, other workspace projects and installed mods that refer to an "
    "old ID by number keep that number; review them yourself.",
    "References are found through typed command arguments. Untyped, unknown or computed references block the plan "
    "instead of being guessed; spell #damage counts as a monster only for a documented summon effect.",
    "Name-based references stay valid because names do not change. Comments and text are never edited.",
    "Free-ID checks cover the catalog, declared dependencies, other workspace projects (definitions and "
    "reservations) and the installed mods scan. Mods that were not scanned can still collide.",
    "Exports and prepared Workshop folders are not rebuilt: export, prepare and check compatibility again.",
]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ---------- typed classification of every argument ----------

def _schema(context: str, cmd: str) -> list[dict[str, Any]] | None:
    """Argument specs for a command in a block context, or None when the signature is not typed."""
    if context == "top":
        spec = cmdreg.get("top", cmd)
        return [a.to_dict() for a in spec.args] if spec else None
    from .manual_commands import CONTEXTS, commands
    if context not in CONTEXTS:
        return None
    entry = commands(context).get(cmd)
    if not entry or not entry.get("editable") or entry.get("args") is None:
        return None
    return entry["args"]


def _arg_spans(text: str, st: Statement) -> list[tuple[int, int]] | None:
    """Character spans of each argument token, re-lexed exactly as dmparse does; None when they disagree."""
    i, end, spans = st.start + 1 + len(st.raw_command), st.end, []
    while i < end:
        ch = text[i]
        if ch in " \t\r\f\v":
            i += 1
            continue
        if ch == '"':
            close = text.find('"', i + 1)
            stop = end if close == -1 or close >= end else close + 1
            spans.append((i, stop))
            i = stop
            continue
        j = i
        while j < end and text[j] not in ' \t\r\n\f\v"' and not text.startswith("--", j):
            j += 1
        spans.append((i, j))
        i = j
    if len(spans) != len(st.args) or any(text[a:b] != arg.raw for (a, b), arg in zip(spans, st.args)):
        return None
    return spans


def _summon_state(block: Any, catalog: Any) -> str:
    """'summon', 'other' or 'unknown' for a spell block's #damage (documented summon effects only)."""
    from .content import SUMMON_EFFECTS, _spell_template
    effects = [s for s in block.statements if s.command == "effect" and s.args and s.args[0].kind == "int"]
    if effects:
        return "summon" if effects[-1].args[0].value in SUMMON_EFFECTS else "other"
    copies = [s for s in block.statements if s.command == "copyspell" and s.args]
    if copies and any(s.command == "clear" and s.start > copies[-1].start for s in block.statements):
        return "unknown"
    src = copies[-1].args[0] if copies else (block.opener.args[0] if block.opener.command == "selectspell"
                                              and block.opener.args else None)
    if src is None or catalog is None:
        return "unknown"
    try:
        sid = src.value if src.kind == "int" else None
        if sid is None and src.kind == "str":
            hits = catalog.names("spells").get(str(src.value).strip().lower(), [])
            sid = hits[0] if len(hits) == 1 else None
        if sid is None:
            return "unknown"
        t = _spell_template(catalog, sid)
    except (KosmoError, OSError, ValueError):
        return "unknown"
    if t["summon"] is not None:
        return "summon"
    return "other" if t["effects"] else "unknown"


def _record(out: list[dict[str, Any]], rel: str, st: Statement, ctx: str, i: int, span: tuple[int, int] | None,
            cls: str, kind: str | None = None, relation: str = "reference", **extra: Any) -> None:
    a = st.args[i]
    out.append({"file": rel, "line": st.line, "command": f"#{st.raw_command}", "context": ctx, "index": i,
                "token": a.kind, "value": a.value, "raw": a.raw, "span": span, "cls": cls, "kind": kind,
                "relation": relation, "statement": st.raw.replace("\r", "")[:200], **extra})


def _scan_dm(rel: str, text: str, catalog: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Any]:
    """(argument records, file problems, parse) for one owned .dm; mapping-independent."""
    pr = parse(text)
    recs: list[dict[str, Any]] = []
    problems = [{"file": rel, "line": i["line"], "message": i["message"]} for i in pr.issues
                if "unterminated string" in i["message"]]
    problems += [{"file": rel, "line": s["line"], "message": "stray text", "text": s["text"]} for s in pr.stray]
    units = [("top", None, st) for st in pr.toplevel]
    for b in pr.blocks:
        units.append((b.context, b, b.opener))
        units += [(b.context, b, st) for st in b.statements]
    summon: dict[int, str] = {}
    for ctx, b, st in units:
        if not st.args:
            continue
        spans = _arg_spans(text, st)
        if spans is None:
            for i in range(len(st.args)):
                _record(recs, rel, st, ctx, i, None, "unlexed")
            continue
        cmd = st.command
        opener = b is not None and st is b.opener
        if opener and cmd in NEW_OPENERS and st.args[0].kind == "int":
            _record(recs, rel, st, ctx, 0, spans[0], "ref", NEW_OPENERS[cmd], "definition", new=True)
            continue
        if opener and cmd in SELECT_OPENERS:
            a = st.args[0]
            kind = SELECT_OPENERS[cmd]
            if a.kind == "int":
                _record(recs, rel, st, ctx, 0, spans[0], "ref", kind, "selector")
            elif a.kind == "str":
                _record(recs, rel, st, ctx, 0, spans[0], "name_ref", kind, "selector")
            for i in range(1, len(st.args)):
                _record(recs, rel, st, ctx, i, spans[i], "untyped")
            continue
        specs = _schema(ctx, cmd)
        for i, a in enumerate(st.args):
            spec = specs[i] if specs is not None and i < len(specs) else None
            typ = spec["type"] if spec else None
            if spec is None:
                _record(recs, rel, st, ctx, i, spans[i], "untyped")
                continue
            kind = REF_KIND.get(typ) or (INT_ID_ARGS.get(spec.get("name")) if typ == "int" else None)
            if a.kind == "int":
                if ctx == "spell" and cmd == "damage" and i == 0:
                    if id(b) not in summon:
                        summon[id(b)] = _summon_state(b, catalog)
                    _record(recs, rel, st, ctx, i, spans[i], "damage", "monster", "summon", summon=summon[id(b)])
                elif kind is None:
                    _record(recs, rel, st, ctx, i, spans[i], "nonref")
                elif typ == "sitename":
                    _record(recs, rel, st, ctx, i, spans[i], "sitename_number", kind)
                elif typ in ("monneg", "nationref") and a.value < 0:
                    _record(recs, rel, st, ctx, i, spans[i], "nonref")  # montag / special nation value
                else:
                    _record(recs, rel, st, ctx, i, spans[i], "ref", kind)
            elif a.kind == "str" and kind is not None:
                _record(recs, rel, st, ctx, i, spans[i], "name_ref", kind)
            elif a.kind in ("word", "float") and kind is not None:
                _record(recs, rel, st, ctx, i, spans[i], "untyped")
            # Other typed text (names, descriptions, image paths) is literal and never an ID.
    return recs, problems, pr


def _scan_map(rel: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pr = parse(text)
    recs: list[dict[str, Any]] = []
    problems = [{"file": rel, "line": i["line"], "message": i["message"]} for i in pr.issues
                if "unterminated string" in i["message"]]
    for st in pr.statements:
        if not st.args or st.command in MAP_NON_REF:
            continue
        spans = _arg_spans(text, st)
        if spans is None:
            for i in range(len(st.args)):
                _record(recs, rel, st, "map", i, None, "unlexed")
            continue
        spec = MAP_COMMANDS.get(st.command)
        for i, a in enumerate(st.args):
            s = spec["args"][i] if spec and i < len(spec["args"]) else None
            if s is None:
                _record(recs, rel, st, "map", i, spans[i], "untyped")
            elif s["name"] == "nation" and a.kind == "int":
                _record(recs, rel, st, "map", i, spans[i], "ref", "nation")
            elif s["type"] == "ref":
                kind = MAP_REF_KIND.get(st.command)
                _record(recs, rel, st, "map", i, spans[i], "map_unproven" if a.kind == "int" else "name_ref", kind)
    return recs, problems


# ---------- project scan and occupancy ----------

def _read_owned(project: Project, cap: dict[str, Any], catalog: Any) -> dict[str, Any]:
    """Parse every owned .dm and .map of the captured revision; bytes must still match the capture."""
    main = f"mod/{project.slug}/{project.slug}.dm"
    if main not in cap["files"]:
        raise KosmoError("dm_missing", f"The project has no {main}.")
    files: dict[str, dict[str, Any]] = {}
    recs: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    parses: dict[str, Any] = {}
    for rel, f in sorted(cap["files"].items()):
        is_map = rel.lower().endswith(".map")
        if f["role"] != "dm" and not is_map:
            continue
        path = contained(project.root, rel, what=rel)
        data = path.read_bytes()
        if sha256_bytes(data) != f["sha256"]:
            raise KosmoError("changed_during_capture", f"{rel} changed while it was read; preview again.", path=rel)
        text, enc = decode_dm(data)
        files[rel] = {"path": rel, "role": f["role"] if not is_map else "map", "data": data, "text": text,
                      "encoding": enc, "newlines": newline_style(text), "sha256": f["sha256"]}
        if is_map:
            r, p = _scan_map(rel, text)
        else:
            r, p, parses[rel] = _scan_dm(rel, text, catalog)
        recs += r
        problems += p
    return {"main": main, "files": files, "records": recs, "problems": problems, "parses": parses}


def _definitions(owned: dict[str, Any], deps: list[tuple[str, list[dict[str, Any]]]], catalog: Any
                 ) -> list[dict[str, Any]]:
    """Owned numbered definitions of the main .dm with eligibility; plus selectors of external identities."""
    main = owned["main"]
    names: dict[tuple[str, int], str | None] = {}
    for b in owned["parses"][main].blocks:
        ident = block_id(b)
        kind = NEW_OPENERS.get(b.opener.command) or SELECT_OPENERS.get(b.opener.command)
        if kind and isinstance(ident, int):
            names.setdefault((kind, ident), block_name(b))
    found: dict[tuple[str, int], dict[str, Any]] = {}
    other_new: dict[tuple[str, int], list[str]] = {}
    for r in owned["records"]:
        if r["cls"] != "ref" or r["relation"] not in ("definition", "selector") or r["token"] != "int":
            continue
        key = (r["kind"], r["value"])
        creating = r["relation"] == "definition" or (r["kind"] == "nation" and r["value"] >= CUSTOM_NATION_MIN)
        if not creating:
            continue
        if r["file"] != main:
            if r["relation"] == "definition":
                other_new.setdefault(key, []).append(f"{r['file']}:{r['line']}")
            continue
        d = found.setdefault(key, {"kind": key[0], "id": key[1], "name": names.get(key), "file": main,
                                   "line": r["line"], "command": r["command"], "blocks": 0, "new_blocks": 0})
        d["blocks"] += 1
        d["new_blocks"] += r["relation"] == "definition"
    dep_ids: dict[tuple[str, int], list[str]] = {}
    for label, defs in deps:
        for d in defs:
            if d["id"] is not None:
                dep_ids.setdefault((d["kind"], d["id"]), []).append(label)
    out = []
    for key, d in sorted(found.items()):
        kind, ident = key
        reasons = []
        cat_ids = _catalog_ids(catalog, kind)
        if d["new_blocks"] > 1:
            reasons.append(f"{d['new_blocks']} blocks create {kind} {ident}; resolve the duplicate first.")
        if key in other_new:
            reasons.append(f"Another owned .dm also creates it ({', '.join(other_new[key][:3])}).")
        if key in dep_ids:
            reasons.append(f"Declared dependency {dep_ids[key][0]} also defines it, so references cannot be "
                           "attributed to this project.")
        if kind == "nation" and ident in cat_ids:
            reasons.append("The catalog defines this nation: it is a shared override, not a project nation.")
        notes = []
        if kind != "nation" and ident in cat_ids:
            notes.append(f"The catalog also has {kind} {ident}; this project's #new block replaces that number.")
        lo, hi = ID_KINDS[kind]["range"]
        if not lo <= ident <= hi:
            notes.append(f"Outside the documented modding range {lo}-{hi}.")
        out.append({**d, "eligible": not reasons, "reasons": reasons, "notes": notes})
    return out


def _catalog_ids(catalog: Any, kind: str) -> set[int]:
    if catalog is None:
        return set()
    try:
        return catalog.ids(ID_KINDS[kind]["catalog"])
    except (KosmoError, OSError):
        return set()


def _occupancy(project: Project, owned: dict[str, Any], catalog: Any, config: dict[str, Any] | None
               ) -> dict[str, Any]:
    """Who uses each ID of each kind outside the remap itself, with a fingerprint of everything read."""
    used: dict[str, dict[int, list[str]]] = {k: {} for k in KINDS}

    def note(kind: str, ident: int, label: str) -> None:
        if kind in used:
            labels = used[kind].setdefault(ident, [])
            if label not in labels and len(labels) < 8:
                labels.append(label)

    caveats, blocking = [], []
    cat_fp: dict[str, Any] = {"available": catalog is not None,
                              "revision": (catalog.meta.get("revision") if catalog is not None else None)}
    for kind in KINDS:
        ids = _catalog_ids(catalog, kind)
        cat_fp[kind] = sha256_bytes(_canon(sorted(ids)))
        for i in ids:
            note(kind, i, "catalog")
    if catalog is None:
        caveats.append("No catalog: vanilla IDs were not checked (targets stay inside the documented range).")
    deps_fp, dep_defs = [], []
    for dep in project.meta.get("dependencies") or []:
        try:
            p = contained(project.workspace, dep, what="dependency")
            data = p.read_bytes()
        except (OSError, KosmoError) as exc:
            blocking.append({"code": "dependency_unreadable", "reason": f"Declared dependency {dep} cannot be read "
                             f"({getattr(exc, 'message', None) or exc}); IDs it defines are unknown."})
            deps_fp.append([dep, None])
            continue
        digest, defs = proj.scan_definitions(data)
        deps_fp.append([dep, digest])
        dep_defs.append((dep, defs))
        for d in defs:
            if d["id"] is not None:
                note(d["kind"], d["id"], f"dependency:{dep}")
    for r in owned["records"]:
        if r["cls"] == "ref" and r["token"] == "int" and r["kind"]:
            note(r["kind"], r["value"], OWN_DEF if r["relation"] in ("definition", "selector") else OWN_REF)
    ext = proj.scan_external(project, config)
    src_fp = []
    dependents = []
    own_dm = f"{project.slug}/mod/{project.slug}/{project.slug}.dm"
    for src in ext["sources"]:
        for d in src["definitions"]:
            if d["id"] is not None:
                note(d["kind"], d["id"], src["label"])
        for kind, ids in src["reservations"].items():
            for i in ids:
                note(kind, i, f"{src['label']} (reserved)")
        src_fp.append([src["label"], src["sha256"], src.get("bytes"),
                       {k: sorted(v) for k, v in src["reservations"].items() if v}])
        if own_dm in [d.replace("\\", "/") for d in src["dependencies"]]:
            dependents.append(src["label"])
    inst = ext["installed_mods"]
    if not inst["available"]:
        caveats.append(f"Installed mods were not checked: {inst['reason']}")
    if not ext["complete"]:
        blocking.append({"code": "scan_incomplete", "reason": "Some workspace projects or installed mods could not "
                         "be read, or a scan limit was reached; IDs defined there are unknown.",
                         "evidence": {"unreadable": ext["unreadable"], "scan_limit_reached": ext["scan_limit_reached"]}})
    reserved = {k: set() for k in KINDS}
    for kind, items in (project.meta.get("reservations") or {}).items():
        if kind in reserved and isinstance(items, list):
            for r in items:
                if isinstance(r, dict) and isinstance(r.get("id"), int):
                    reserved[kind].add(r["id"])
    identity = {"catalog": cat_fp, "dependencies": deps_fp, "sources": src_fp, "installed": inst,
                "unreadable": ext["unreadable"], "scan_limit_reached": ext["scan_limit_reached"],
                "complete": ext["complete"]}
    coverage = {"catalog": catalog is not None, "dependencies": [d[0] for d in deps_fp],
                "workspace_projects": ext["workspace_projects"], "installed_mods": inst,
                "unreadable": ext["unreadable"], "unreadable_count": ext["unreadable_count"],
                "scan_limit_reached": ext["scan_limit_reached"], "complete": ext["complete"], "links_followed": False}
    return {"used": used, "reserved": reserved, "fingerprint": sha256_bytes(_canon(identity)), "coverage": coverage,
            "caveats": caveats, "blocking": blocking, "dependents": dependents, "dep_defs": dep_defs}


def _suggest(kind: str, occ: dict[str, Any], count: int = 5, rng: random.Random | None = None) -> list[dict[str, Any]]:
    lo, hi = ID_KINDS[kind]["range"]
    used = occ["used"][kind]
    out = [{"id": i, "source": "reserved for this project"} for i in sorted(occ["reserved"][kind])
           if lo <= i <= hi and i not in used][:3]
    taken = {x["id"] for x in out} | set(used) | occ["reserved"][kind]
    free = [i for i in range(lo, hi + 1) if i not in taken]
    if kind == "nation":
        picks = sorted((rng or random.SystemRandom()).sample(free, min(count, len(free))))
    else:
        picks = free[:count]
    return out + [{"id": i, "source": "free"} for i in picks]


# ---------- state ----------

def remap_state(workspace: Path, slug: str, catalog: Any = None, config: dict[str, Any] | None = None
                ) -> dict[str, Any]:
    """Eligible project-owned definitions, who else uses each ID, suggested free targets. Read-only."""
    project = open_project(workspace, slug)
    cap = rev._capture(project)
    owned = _read_owned(project, cap, catalog)
    occ = _occupancy(project, owned, catalog, config)
    defs = _definitions(owned, occ["dep_defs"], catalog)
    refs: dict[tuple[str, int], int] = {}
    for r in owned["records"]:
        if r["cls"] == "ref" and r["token"] == "int" and r["relation"] == "reference":
            refs[(r["kind"], r["value"])] = refs.get((r["kind"], r["value"]), 0) + 1
    items = []
    for d in defs:
        others = [x for x in occ["used"][d["kind"]].get(d["id"], []) if x not in (OWN_DEF, OWN_REF)]
        items.append({**d, "references": refs.get((d["kind"], d["id"]), 0), "also_used_by": others,
                      "conflict": bool(others)})
    selectors = []
    for r in owned["records"]:
        if r["cls"] == "ref" and r["relation"] == "selector" and r["token"] == "int" and r["file"] == owned["main"] \
                and not (r["kind"] == "nation" and r["value"] >= CUSTOM_NATION_MIN) \
                and not any(d["kind"] == r["kind"] and d["id"] == r["value"] for d in defs):
            selectors.append({"kind": r["kind"], "id": r["value"], "line": r["line"], "command": r["command"],
                              "reason": "Selects an existing (vanilla, dependency or external) identity; only "
                                        "definitions this project creates can be remapped."})
    return {
        "schema": SCHEMA, "project": slug, "current_revision": cap["revision"],
        "occupancy_fingerprint": occ["fingerprint"], "kinds": list(KINDS),
        "ranges": {k: list(ID_KINDS[k]["range"]) for k in KINDS},
        "definitions": items[:MAX_LISTED], "definitions_total": len(items),
        "not_eligible_selectors": selectors[:50],
        "suggestions": {k: _suggest(k, occ) for k in KINDS},
        "coverage": occ["coverage"], "caveats": occ["caveats"], "scan_blocking": occ["blocking"],
        "dependent_projects": occ["dependents"],
        "files": [{"path": f["path"], "role": f["role"], "sha256": f["sha256"], "encoding": f["encoding"],
                   "newlines": f["newlines"]} for f in owned["files"].values()],
        "usage": "Preview with author_save kind 'remap' {mapping: [{kind, old, new}], expected_revision}; apply the "
                 "same mapping with preview: false, expected_revision, expected_occupancy, plan_hash and confirm.",
        "limitations": LIMITATIONS,
    }


# ---------- plan ----------

def _mapping(body: dict[str, Any]) -> list[dict[str, Any]]:
    m = body.get("mapping")
    if not isinstance(m, list) or not 1 <= len(m) <= MAX_MAPPING:
        raise KosmoError("bad_request", f"mapping must list 1-{MAX_MAPPING} entries {{kind, old, new}}.")
    out = []
    for e in m:
        if not isinstance(e, dict) or set(e) != {"kind", "old", "new"} or e["kind"] not in KINDS or \
                any(type(e[k]) is not int for k in ("old", "new")):
            raise KosmoError("bad_request", f"Each mapping entry is {{kind: {'|'.join(KINDS)}, old: int, new: int}}.")
        out.append({"kind": e["kind"], "old": e["old"], "new": e["new"]})
    return sorted(out, key=lambda e: (e["kind"], e["old"], e["new"]))


def _finding(code: str, reason: str, blocking: bool = True, rec: dict[str, Any] | None = None,
             **extra: Any) -> dict[str, Any]:
    loc = {k: rec[k] for k in ("file", "line", "command", "context", "index", "raw", "statement")} if rec else {}
    key = sha256_bytes(_canon([code, loc.get("file"), loc.get("line"), loc.get("index"), extra.get("kind"),
                               extra.get("id")]))[:16]
    return {"id": key, "code": code, "severity": "error" if blocking else "warning", "blocking": blocking,
            "reason": reason, **loc, **extra}


def _build_plan(project: Project, cap: dict[str, Any], mapping: list[dict[str, Any]], catalog: Any,
                config: dict[str, Any] | None) -> dict[str, Any]:
    owned = _read_owned(project, cap, catalog)
    occ = _occupancy(project, owned, catalog, config)
    defs = {(d["kind"], d["id"]): d for d in _definitions(owned, occ["dep_defs"], catalog)}
    M: dict[str, dict[int, int]] = {k: {} for k in KINDS}
    findings: list[dict[str, Any]] = [_finding(b["code"], b["reason"], evidence=b.get("evidence")) for b in occ["blocking"]]
    entries = []
    news: dict[str, list[int]] = {k: [] for k in KINDS}
    for e in mapping:
        kind, old, new = e["kind"], e["old"], e["new"]
        if old in M[kind]:
            findings.append(_finding("duplicate_mapping", f"{kind} {old} is listed twice.", kind=kind, id=old))
        M[kind][old] = new
        news[kind].append(new)
    for e in mapping:
        kind, old, new = e["kind"], e["old"], e["new"]
        lo, hi = ID_KINDS[kind]["range"]
        d = defs.get((kind, old))
        occupied = [x for x in occ["used"][kind].get(new, [])]
        checks = {"in_range": lo <= new <= hi, "range": [lo, hi], "occupied_by": occupied,
                  "reserved_for_project": new in occ["reserved"][kind]}
        if d is None:
            findings.append(_finding("not_owned", f"{kind} {old} is not a definition this project creates (only "
                                     "#new blocks and #selectnation 150+ nations of the project .dm are owned).",
                                     kind=kind, id=old))
        elif not d["eligible"]:
            findings.append(_finding("not_eligible", " ".join(d["reasons"]), kind=kind, id=old))
        if new == old:
            findings.append(_finding("unchanged", f"{kind} {old} maps to itself.", kind=kind, id=old))
        elif not checks["in_range"]:
            findings.append(_finding("target_out_of_range", f"{kind} {new} is outside the documented range {lo}-{hi} "
                                     f"({ID_KINDS[kind]['source']})", kind=kind, id=new))
        if new != old and occupied:
            findings.append(_finding("target_occupied", f"{kind} {new} is already used by {', '.join(occupied[:4])}.",
                                     kind=kind, id=new))
        if news[kind].count(new) > 1:
            findings.append(_finding("duplicate_target", f"More than one {kind} maps to {new}.", kind=kind, id=new))
        if new != old and new in M[kind]:
            findings.append(_finding("chained_mapping", f"{kind} {new} is itself remapped; swaps, cycles and chains "
                                     "are refused. Remap in separate steps through a free ID.", kind=kind, id=new))
        others = [x for x in occ["used"][kind].get(old, []) if x not in (OWN_DEF, OWN_REF)]
        entries.append({"kind": kind, "old": old, "new": new, "name": d["name"] if d else None,
                        "definition": {k: d[k] for k in ("file", "line", "command")} if d else None,
                        "old_also_used_by": others, "target": checks, "references": 0, "selectors": 0,
                        "definitions": 0, "summons": 0, "name_references": 0})
    by_key = {(e["kind"], e["old"]): e for e in entries}
    olds = {(k, o) for k in KINDS for o in M[k]}
    all_olds = sorted({o for k in KINDS for o in M[k]})
    num_re = re.compile(r"(?<![0-9])(" + "|".join(str(o) for o in all_olds) + r")(?![0-9])") if all_olds else None
    edits: list[dict[str, Any]] = []
    preserved = {"other_namespace": 0, "non_reference": 0, "text": 0, "spell_damage_not_summon": 0}
    for r in owned["records"]:
        v, tok, kind = r["value"], r["token"], r["kind"]
        hit = tok == "int" and kind is not None and (kind, v) in olds
        if r["cls"] == "ref" and tok == "int":
            if hit:
                e = by_key[(kind, v)]
                edits.append({**{k: r[k] for k in ("file", "line", "command", "context", "index", "span", "relation",
                                                   "statement")},
                              "kind": kind, "old": v, "new": M[kind][v], "old_raw": r["raw"],
                              "new_raw": ("+" if r["raw"].startswith("+") else "") + str(M[kind][v])})
                e[{"definition": "definitions", "selector": "selectors"}.get(r["relation"], "references")] += 1
            elif any(v in M[k] for k in KINDS if k != kind):
                preserved["other_namespace"] += 1
        elif r["cls"] == "damage" and tok == "int" and ("monster", v) in olds:
            if r["summon"] == "summon":
                edits.append({**{k: r[k] for k in ("file", "line", "command", "context", "index", "span",
                                                   "statement")},
                              "relation": "summon", "kind": "monster", "old": v, "new": M["monster"][v],
                              "old_raw": r["raw"], "new_raw": str(M["monster"][v])})
                by_key[("monster", v)]["summons"] += 1
            elif r["summon"] == "other":
                preserved["spell_damage_not_summon"] += 1
            else:
                findings.append(_finding("spell_damage_unproven", f"#damage {v} in this spell may be monster {v}, but "
                                         "its effect is not a documented summon the plan can prove (no #effect, no "
                                         "catalog #copyspell/#selectspell template, or a #clear after the copy). "
                                         "Review it and edit it yourself, or remove the ambiguity.", rec=r))
        elif r["cls"] == "sitename_number" and tok == "int" and ("site", v) in olds:
            findings.append(_finding("numeric_site_name", f"#startsite-style commands take a site name (p.43); the "
                                     f"number {v} here is not a documented site reference. Use the site's name.",
                                     rec=r))
        elif r["cls"] == "map_unproven" and tok == "int" and (kind, v) in olds:
            findings.append(_finding("map_reference_unproven", f"Map command {r['command']} may refer to {kind} {v}; "
                                     "the map schema does not prove how numbers are read here. Edit the map "
                                     "bundle yourself.", rec=r))
        elif r["cls"] in ("untyped", "unlexed"):
            hits = [k for k in KINDS if tok == "int" and v in M[k]]
            if tok != "int" and num_re and num_re.search(str(r["raw"])):
                hits = ["text"]
            if hits:
                findings.append(_finding("untyped_reference", f"{r['command']} has no typed signature for argument "
                                         f"{r['index'] + 1}, so {r['raw']} may be an ID ({', '.join(hits)}). It is "
                                         "kept as written; review and edit it yourself.", rec=r))
        elif r["cls"] == "name_ref" and tok == "str":
            s = str(v).strip()
            if s.isdigit() and (kind, int(s)) in olds:
                findings.append(_finding("quoted_number", f"{r['command']} quotes the number {s}, which reads as a "
                                         "name, not an ID. Review it yourself.", rec=r))
            else:
                for (k, o), e in by_key.items():
                    if k == kind and e["name"] and s.lower() == e["name"].lower():
                        e["name_references"] += 1
        elif hit or (tok == "int" and any(v in M[k] for k in KINDS)):
            preserved["non_reference"] += 1
    for p in owned["problems"]:
        if num_re and num_re.search(p.get("text") or "") or "unterminated" in p["message"]:
            findings.append(_finding("unparsed_text", f"{p['file']} line {p['line']}: {p['message']}; text the parser "
                                     "cannot type may contain old IDs. Fix the syntax first.",
                                     rec=None, file=p["file"], line=p["line"]))
    for label in occ["dependents"]:
        findings.append(_finding("dependent_project", f"{label} declares this project's .dm as a dependency; its "
                                 "numeric references to old IDs are not changed.", blocking=False, source=label))
    for e in entries:
        if e["old_also_used_by"]:
            findings.append(_finding("external_old_id", f"{e['kind']} {e['old']} stays in use by "
                                     f"{', '.join(e['old_also_used_by'][:4])}; those files are not changed.",
                                     blocking=False, kind=e["kind"], id=e["old"]))
    # Apply the edits per file; only the argument tokens change.
    files_out = []
    by_file: dict[str, list[dict[str, Any]]] = {}
    for ed in edits:
        by_file.setdefault(ed["file"], []).append(ed)
    for rel, eds in sorted(by_file.items()):
        f = owned["files"][rel]
        text = f["text"]
        eds.sort(key=lambda x: x["span"][0])
        parts, pos = [], 0
        for ed in eds:
            a, b = ed["span"]
            if text[a:b] != ed["old_raw"] or a < pos:
                raise KosmoError("internal", f"Edit span mismatch in {rel}; nothing was written.")
            parts += [text[pos:a], ed["new_raw"]]
            pos = b
        parts.append(text[pos:])
        new_text = "".join(parts)
        try:
            new_data = new_text.encode(f["encoding"])
        except UnicodeEncodeError as exc:
            raise KosmoError("encoding", f"{rel} cannot be re-encoded as {f['encoding']}.") from exc
        _self_check(rel, text, new_text, f["data"], new_data, f["encoding"], eds)
        diff = list(difflib.unified_diff(text.splitlines(), new_text.splitlines(), fromfile=f"a/{rel}",
                                         tofile=f"b/{rel}", lineterm="", n=1))
        files_out.append({"path": rel, "role": f["role"], "encoding": f["encoding"], "newlines": f["newlines"],
                          "before_sha256": f["sha256"], "after_sha256": sha256_bytes(new_data),
                          "edits": len(eds), "diff": "\n".join(diff[:MAX_DIFF_LINES]),
                          "diff_truncated": len(diff) > MAX_DIFF_LINES, "_data": new_data})
    blocking = [f for f in findings if f["blocking"]]
    body = {"schema": PLAN_SCHEMA, "project": project.slug, "mapping": mapping, "current_revision": cap["revision"],
            "occupancy": occ["fingerprint"],
            "files": [[f["path"], f["before_sha256"], f["after_sha256"]] for f in files_out],
            "edits": [[e["file"], e["span"][0], e["span"][1], e["old_raw"], e["new_raw"]] for e in edits],
            "blocking": sorted(f["id"] for f in blocking)}
    return {"hash": sha256_bytes(_canon(body)), "mapping": mapping, "entries": entries, "edits": edits,
            "files": files_out, "findings": findings, "blocking": blocking, "occ": occ, "preserved": preserved,
            "can_apply": not blocking and bool(edits)}


def _self_check(rel: str, text: str, new_text: str, data: bytes, new_data: bytes, enc: str,
                eds: list[dict[str, Any]]) -> None:
    """The new text parses to the same statements; only the edited argument tokens differ."""
    if new_data.decode(enc) != new_text or newline_style(new_text) != newline_style(text):
        raise KosmoError("internal", f"Lossless self-check failed for {rel}; nothing was written.")
    a, b = parse(text).statements, parse(new_text).statements
    changed = {e["span"][0]: e["new_raw"] for e in eds}
    used = 0
    if len(a) != len(b):
        raise KosmoError("internal", f"Statement self-check failed for {rel}; nothing was written.")
    for x, y in zip(a, b):
        if x.command != y.command or x.line != y.line or len(x.args) != len(y.args):
            raise KosmoError("internal", f"Statement self-check failed for {rel}; nothing was written.")
        spans = _arg_spans(text, x) or []
        for i, (p, q) in enumerate(zip(x.args, y.args)):
            start = spans[i][0] if i < len(spans) else None
            want = changed.get(start, p.raw) if start is not None else p.raw
            used += start in changed
            if q.raw != want:
                raise KosmoError("internal", f"Argument self-check failed for {rel}; nothing was written.")
    if used != len(changed):
        raise KosmoError("internal", f"Edit self-check failed for {rel}; nothing was written.")
    if data.count(b"\r\n") != new_data.count(b"\r\n") or len(data.splitlines()) != len(new_data.splitlines()):
        raise KosmoError("internal", f"Line self-check failed for {rel}; nothing was written.")


def _view(project: Project, cap: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    occ = plan["occ"]
    edits = [{k: e[k] for k in ("file", "line", "command", "context", "index", "relation", "kind", "old", "new",
                                "old_raw", "new_raw", "statement")} for e in plan["edits"]]
    reasons = [f["reason"] for f in plan["blocking"]]
    if not plan["edits"] and not reasons:
        reasons.append("Nothing to change.")
    return {
        "schema": PLAN_SCHEMA, "project": project.slug, "mapping": plan["mapping"], "entries": plan["entries"],
        "current_revision": cap["revision"], "expected_revision": cap["revision"],
        "occupancy_fingerprint": occ["fingerprint"], "plan_hash": plan["hash"],
        "can_apply": plan["can_apply"], "blocked_reasons": reasons[:50],
        "edits": edits[:MAX_LISTED], "edits_total": len(edits),
        "files": [{k: v for k, v in f.items() if not k.startswith("_")} for f in plan["files"]],
        "manual_findings": plan["findings"][:MAX_LISTED], "manual_findings_total": len(plan["findings"]),
        "preserved": plan["preserved"],
        "coverage": occ["coverage"], "caveats": occ["caveats"],
        "reservations": [{"kind": e["kind"], "id": e["new"], "already_reserved": e["target"]["reserved_for_project"]}
                         for e in plan["entries"]],
        "apply": {"requires": ["mapping", "expected_revision", "expected_occupancy", "plan_hash", "confirm"],
                  "recovery": "A complete pre-remap checkpoint is stored first; restore it from Changes to undo. Old "
                              "reservations are kept and the new IDs are reserved."},
        "limitations": LIMITATIONS,
    }


def preview_remap(workspace: Path, slug: str, body: dict[str, Any], catalog: Any = None,
                  config: dict[str, Any] | None = None) -> dict[str, Any]:
    project = open_project(workspace, slug)
    mapping = _mapping(body)
    cap = rev._capture(project)
    expected = body.get("expected_revision")
    if expected is not None and expected != cap["revision"]:
        raise KosmoError("stale_revision", "The project changed since you looked at it; reload first.",
                         expected=expected, actual=cap["revision"])
    plan = _build_plan(project, cap, mapping, catalog, config)
    return {**_view(project, cap, plan), "preview": True, "written": False}


# ---------- apply ----------

def _revert(project: Project, written: list[tuple[str, bytes, str]]) -> list[dict[str, Any]]:
    """Put back each written file whose content is still ours; anything else is reported, never overwritten."""
    problems = []
    for rel, before, after_sha in reversed(written):
        try:
            path = contained(project.root, rel, what=rel)
            now = sha256_bytes(path.read_bytes())
            if now == sha256_bytes(before):
                continue
            if now != after_sha:
                problems.append({"path": rel, "reason": "changed by someone else; left as is"})
                continue
            atomic_write_bytes(path, before)
        except (OSError, KosmoError) as exc:
            problems.append({"path": rel, "reason": getattr(exc, "message", None) or str(exc)})
    return problems


def apply_remap(workspace: Path, slug: str, body: dict[str, Any], catalog: Any = None,
                config: dict[str, Any] | None = None, via: str = "api") -> dict[str, Any]:
    project = open_project(workspace, slug)
    mapping = _mapping(body)
    if body.get("confirm") is not True:
        raise KosmoError("confirm_required", "Applying a remap needs confirm: true after reviewing the preview.")
    expected, occ_fp, plan_hash = body.get("expected_revision"), body.get("expected_occupancy"), body.get("plan_hash")
    if not all(isinstance(x, str) and SHA_RE.match(x) for x in (expected, occ_fp, plan_hash)):
        raise KosmoError("bad_request", "Apply needs expected_revision, expected_occupancy and plan_hash from the "
                                        "remap preview.")
    with project_lock(project):
        proj.reload_meta(project)
        store = rev._store(project, create=False)
        pending = rev._interrupted(store)
        if pending:
            raise KosmoError("restore_interrupted", "An earlier restore did not finish; recover it first.",
                             journal=pending[0]["id"])
        cap = rev._capture(project)
        if cap["revision"] != expected:
            raise KosmoError("stale_revision", "The project changed after the preview; preview the remap again. "
                             "Nothing was written.", expected=expected, actual=cap["revision"])
        # Rebuilt now: the external occupancy scan runs again immediately before any write.
        plan = _build_plan(project, cap, mapping, catalog, config)
        if plan["occ"]["fingerprint"] != occ_fp:
            raise KosmoError("occupancy_changed", "Installed mods, other projects, dependencies or the catalog changed "
                             "since the preview; preview again. Nothing was written.",
                             expected=occ_fp, actual=plan["occ"]["fingerprint"])
        if plan["hash"] != plan_hash:
            raise KosmoError("plan_changed", "The remap plan differs from the preview; preview again. Nothing was "
                             "written.", expected=plan_hash, actual=plan["hash"])
        if not plan["can_apply"]:
            raise KosmoError("remap_blocked", "The plan has unresolved manual findings; nothing was written.",
                             findings=[{k: f.get(k) for k in ("code", "file", "line", "reason")}
                                       for f in plan["blocking"][:20]])
        store = rev._store(project, create=True)
        full = rev._capture(project, store)
        if full["revision"] != expected:
            raise KosmoError("stale_revision", "The project changed during the remap; nothing was written.",
                             expected=expected, actual=full["revision"])
        meta_before = project.meta_path.read_bytes()
        if sha256_bytes(meta_before) != full["shas"].get(META_FILE):
            raise KosmoError("stale_revision", "Project metadata changed during the remap; nothing was written.",
                             expected=full["shas"].get(META_FILE), actual=sha256_bytes(meta_before))
        summary = ", ".join(f"{e['kind']} {e['old']}->{e['new']}" for e in mapping)
        pre = rev._write_checkpoint(project, store, full, "pre-remap", via=via,
                                    label=f"Before remapping {summary}"[:120],
                                    extra={"remap": {"mapping": mapping, "plan_hash": plan["hash"]}})
        written: list[tuple[str, bytes, str]] = []
        backups = []
        meta_saved = copy.deepcopy(project.meta)
        meta_new: bytes | None = None
        try:
            for f in plan["files"]:
                path = contained(project.root, f["path"], what=f["path"])
                data = path.read_bytes()
                if sha256_bytes(data) != f["before_sha256"]:
                    raise KosmoError("changed_during_remap", f"{f['path']} changed during the remap.", path=f["path"])
                backups.append(proj.write_dm_locked(project, path, data, f["_data"]))
                written.append((f["path"], data, f["after_sha256"]))
            stamp = _now()
            res = project.meta.setdefault("reservations", {})
            for e in mapping:
                items = res.setdefault(e["kind"], [])
                if not any(isinstance(r, dict) and r.get("id") == e["new"] for r in items):
                    items.append({"id": e["new"], "label": f"remap {e['kind']} {e['old']} -> {e['new']}",
                                  "reserved_utc": stamp})
            meta_new = proj._meta_bytes(project)
            # Compare-and-swap: the project lock only holds off co-operating writers, so an outside editor can still
            # change the file between this check and the atomic rename; that narrow gap is not closed here.
            if project.meta_path.read_bytes() != meta_before:
                raise KosmoError("changed_during_remap", f"{META_FILE} changed during the remap.", path=META_FILE)
            proj._save_meta(project)
        except BaseException as exc:
            project.meta = meta_saved
            problems = _revert(project, written)
            try:
                meta_now = project.meta_path.read_bytes()
                if meta_now != meta_before:
                    if meta_new is not None and meta_now == meta_new:
                        atomic_write_bytes(project.meta_path, meta_before)
                    else:
                        problems.append({"path": META_FILE, "reason": "changed by someone else; left as is"})
            except OSError as meta_exc:
                problems.append({"path": META_FILE, "reason": str(meta_exc)})
            if problems:
                raise KosmoError("remap_rollback_failed", "The remap failed and some files could not be put back; "
                                 f"restore pre-remap checkpoint {pre['id']} from Changes.", pre_remap=pre["id"],
                                 problems=problems[:20]) from exc
            cause = getattr(exc, "message", None) or str(exc) or type(exc).__name__
            raise KosmoError("remap_failed", f"The remap failed ({cause}); every written file was put back. "
                             f"Pre-remap checkpoint {pre['id']} is kept.", pre_remap=pre["id"]) from exc
        final = rev._capture(project)
    verified = all(final["shas"].get(f["path"]) == f["after_sha256"] for f in plan["files"])
    return {**_view(project, cap, plan), "preview": False, "written": True, "verified": verified,
            "revision": final["revision"], "pre_remap": rev._summary(pre), "backups": backups,
            "after": _after(workspace, slug, catalog, config),
            "note": "Remapped. Export again, prepare a new Workshop folder and check compatibility again; nothing was "
                    "installed, exported or published."}


def _after(workspace: Path, slug: str, catalog: Any, config: dict[str, Any] | None) -> dict[str, Any]:
    """Validation and health of the new revision, and the bundles built from earlier revisions."""
    from .export import list_exports
    from .health import build_health
    from .validate import validate_project
    out: dict[str, Any] = {}
    try:
        v = validate_project(workspace, slug, catalog)
        out["validation"] = {"ok": v["ok"], "counts": v["counts"], "errors": v["errors"][:20]}
    except KosmoError as exc:
        out["validation"] = {"ok": False, "error": exc.to_dict()}
    try:
        h = build_health(workspace, slug, catalog)
        out["health"] = {"status": h["status"], "counts": h["counts"], "revision": h["revision"],
                         "findings": [{k: f.get(k) for k in ("id", "code", "severity", "message")}
                                      for f in h["findings"][:15]]}
    except (KosmoError, OSError) as exc:
        out["health"] = {"status": "unavailable", "error": getattr(exc, "message", None) or str(exc)}
    stale = []
    try:
        stale += [{"type": "export", "id": x.get("export_id")} for x in list_exports(workspace, slug)]
    except (KosmoError, OSError):
        pass
    try:
        from .workshop import workshop_state
        stale += [{"type": "workshop", "id": x.get("workshop_id")}
                  for x in workshop_state(workspace, slug, config or {})["prepared"]]
    except (KosmoError, OSError, KeyError, TypeError):
        pass
    out["regenerate"] = {"stale_bundles": stale[:50],
                         "steps": ["export the new revision", "prepare a new Workshop folder from it",
                                   "check compatibility (preflight) again", "install only after a passing check"],
                         "automatic": False}
    return out


ACTION_FIELDS = {"mapping", "preview", "expected_revision", "expected_occupancy", "plan_hash", "confirm"}


def save_remap(workspace: Path, slug: str, body: Any, catalog: Any = None, config: dict[str, Any] | None = None,
               via: str = "api") -> dict[str, Any]:
    """Preview (default) or apply one reviewed mapping."""
    if not isinstance(body, dict):
        raise KosmoError("bad_request", "Body must be a JSON object.")
    extra = set(body) - ACTION_FIELDS
    if extra:
        raise KosmoError("bad_request", f"Unexpected fields: {sorted(extra)}.")
    if body.get("preview", True) is not False:
        return preview_remap(workspace, slug, body, catalog, config)
    return apply_remap(workspace, slug, body, catalog, config, via)
