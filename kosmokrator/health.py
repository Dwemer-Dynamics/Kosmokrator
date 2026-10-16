"""Unified project health: one prioritized, deduplicated list of actionable findings.

Health adds no checks of its own. It reads the existing reports for one captured revision:
  validation     - static validation (validate.py) with every error, warning and unverified item;
  assets         - referenced files missing from the mod folder and per-unit sprite sources (browse readiness);
  references     - the explicit reference graph and dependency compatibility report (resolution.py);
  recruitment    - roster roles and recruitment ties from the browser model (never inferred from donors);
  catalog        - live catalog or project reference-snapshot state (reference.py).
Findings have stable ids derived from code, object identity, asset and normalized detail, never from line
numbers, so inserting or removing lines elsewhere keeps ids and order. Severities: error (blocks export or is
known invalid), warning, unverified (needs a catalog, a human or the game) and info.
Nothing here loads the game, scans installed mods or proves balance; scope and caveats are part of the result.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import __version__
from .catalog import Catalog
from .errors import KosmoError
from .project import Project, open_project, sha256_bytes

SCHEMA = "kosmokrator.health/1"
SEVERITIES = ("error", "warning", "unverified", "info")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
# Category order within one severity: integrity of the read first, then what most often blocks other work.
CATEGORIES = ("integrity", "identity", "references", "assets", "validation", "sprites", "recruitment", "catalog")
CATEGORY_RANK = {c: i for i, c in enumerate(CATEGORIES)}

ASSET_CODES = {"bad_asset_path", "bad_image_type", "asset_missing", "asset_case_mismatch", "asset_symlink",
               "asset_not_a_file", "bad_image", "flag_size", "icon_size", "sprite_size", "unreferenced_file",
               "symlink_in_mod", "unsafe_filename"}
REFERENCE_CODES = {"unresolved_reference", "ambiguous_reference", "unverified_reference"}
IDENTITY_CODES = {"duplicate_definition", "dependency_conflict", "id_in_use"}

# Next actions by code. Unlisted codes fall back to the per-severity default below.
NEXT_ACTIONS = {
    "asset_missing": "Add the file to the mod folder under exactly this path, or change the command to an existing file.",
    "asset_case_mismatch": "Rename the file or the reference so the letter case matches exactly.",
    "bad_asset_path": "Use a relative path inside the mod folder without '..', drive letters or backslashes.",
    "unreferenced_file": "Reference the file from the .dm, or remove it from the mod folder if it is not needed.",
    "unresolved_reference": "Check the target ID or name; declare the dependency that defines it, or correct the reference.",
    "uncertain_reference": "Confirm the target exists in a declared dependency or the catalog; prefer a verified numeric ID.",
    "ambiguous_reference": "Reference the target by its numeric ID instead of a shared name.",
    "unverified_reference": "Configure a catalog (or reference snapshot) so vanilla references can be checked.",
    "id_collision": "Reserve a free ID with allocate_ids (dependencies declared), then update every reference with a guarded edit.",
    "identity_overlap": "Confirm the shared target is intended; the declared order decides which authored commands come last.",
    "ambiguous_named_definition": "Give the new definition a reserved numeric ID or a unique name.",
    "order_sensitive_reference": "Place the copied definition before this block (or declare its provider earlier) and recheck.",
    "no_sprite_source": "Add #spr1/#spr2 artwork (see the asset rules) or an explicit #copyspr source.",
    "borrowed_sprite": "Replace the borrowed sprite with original artwork unless reuse was requested.",
    "unverified_sprite_source": "Check the donor ID against a catalog; the sprite source could not be confirmed.",
    "sprite_overwritten": "Move #spr1/#spr2 after #copystats so the custom art is used.",
    "unassigned_monster": "Tie it to a nation, site, summon, hero or pretender command, or confirm it is intentionally unlisted.",
    "catalog_unavailable": "Start with --catalog (or set KOSMOKRATOR_CATALOG), or create a project reference snapshot.",
    "catalog_error": "Fix the configured catalog path; vanilla references stay unverified meanwhile.",
    "reference_snapshot_invalid": "Recreate the reference snapshot from a live catalog.",
    "reference_snapshot_stale": "Refresh the reference snapshot if the newer catalog should be used.",
    "reference_snapshot_sprites": "Refresh the reference snapshot so newly referenced vanilla sprites are included.",
    "unreserved_id": "Record the ID with allocate_ids, or reserve a fresh one and update its references with a guarded edit.",
    "id_range": "Reserve an ID in the documented range with allocate_ids, then update references.",
    "duplicate_name": "Give each new definition a unique name, or reference it by number.",
    "name_shadows_catalog": "Rename the new definition or reference it by number; name references are ambiguous.",
    "copystats_order": "Move #copystats directly after the opening command.",
    "name_overwritten": "Move #name after #copystats.",
    "syntax": "Fix the source syntax at this line.",
    "unknown_command": "Check the command with lookup_command; it is kept verbatim but not checked.",
    "documented_uncurated": "Check the arguments against the manual; they are kept verbatim but not checked.",
    "uncurated_context": "Review this block by hand; its commands are kept verbatim but not checked.",
    "unknown_block": "Review this block by hand; it is kept verbatim but not interpreted.",
    "auto_id": "Use a reserved numeric ID if other definitions refer to this one.",
    "changed_during_check":"Re-run health; the project changed while it was being read.",
    "model_unavailable": "Fix the reported read error, then re-run health.",
}
DEFAULT_ACTIONS = {
    "error": "Fix this before export; see the validation report for the command and manual reference.",
    "warning": "Review and fix, or record why it is intended.",
    "unverified": "Confirm by hand or in game; static checks cannot verify it.",
    "info": "No action required unless it conflicts with the brief.",
}
TITLES = {
    "id_collision": "Duplicate or colliding ID", "identity_overlap": "Shared identity across mods",
    "asset_missing": "Referenced file missing", "unresolved_reference": "Broken reference",
    "uncertain_reference": "Uncertain reference", "ambiguous_reference": "Ambiguous reference",
    "unverified_reference": "Unverified reference", "no_sprite_source": "Unit has no sprite",
    "borrowed_sprite": "Unit uses a borrowed sprite", "unassigned_monster": "Unit not tied to any roster",
    "catalog_unavailable": "No catalog", "order_sensitive_reference": "Copy target defined later",
}

# Recruitment classes, from explicit nation/site/spell/god commands in the model (never from #copystats donors).
NORMAL_RECRUIT = {"addrecunit", "addreccom", "addforeignunit", "addforeigncom", "uwrec", "uwcom", "landrec",
                  "landcom", "coastunit1", "coastunit2", "coastunit3", "coastcom1", "coastcom2",
                  *(f"{t}rec" for t in ("forest", "mountain", "swamp", "waste", "cave", "coast")),
                  *(f"{t}com" for t in ("forest", "mountain", "swamp", "waste", "cave"))}
START_ARMY = {"startcom", "startscout", "startunittype1", "startunittype2"}
DEFENCE = {"defcom1", "defcom2", "defunit1", "defunit1b", "defunit1c", "defunit1d", "defunit2", "defunit2b",
           "wallcom", "wallunit", "guardcom", "guardunit"}
HERO = {f"hero{i}" for i in range(1, 11)} | {f"multihero{i}" for i in range(1, 8)}
RECRUITMENT_CLASSES = ("normal", "cap_only", "site", "start_army", "defence", "hero", "summon", "pretender",
                       "form", "merc", "event", "referenced", "unassigned")

LIMITATIONS = [
    "Static health only: it does not load Dominions, simulate combat or prove balance.",
    "Installed mods are not scanned here; conflicts with mods that are not declared dependencies are unknown.",
    "Dependencies are modelled in declared order followed by this project, not the game's detected activation order.",
    "Catalog and reference snapshot data are third-party extracts and may differ from the installed game.",
    "Recruitment classes come from explicit commands only; unassigned units are reported, not treated as errors.",
]
NOT_CHECKED = [
    {"check": "installed_mods", "reason": "The game's mods folder is not scanned by health (allocate_ids scans it separately)."},
    {"check": "unlisted_enabled_mods", "reason": "Mods enabled in game but not declared as dependencies are unknown."},
    {"check": "game_load", "reason": "No engine load test; a clean result covers supported static checks only."},
    {"check": "gameplay_balance", "reason": "Balance comparisons are separate review aids, not simulations."},
    {"check": "revision_history", "reason": "Earlier revisions, exports and installs are not compared."},
]


# ---------- captured identity ----------

def _catalog_identity(catalog: Catalog | None, state: str, error: dict[str, Any] | None) -> dict[str, Any]:
    meta = catalog.meta if catalog else {}
    snap = meta.get("reference_snapshot") or {}
    return {"state": state, "revision": meta.get("revision"), "dataset_version": meta.get("dataset_version"),
            "snapshot": snap.get("snapshot") if isinstance(snap, dict) else None,
            "error": (error or {}).get("code")}


def _asset_digest(project: Project) -> tuple[str, int, str | None]:
    from .export import _mod_snapshot
    try:
        files = _mod_snapshot(project)
    except KosmoError as exc:
        return "unreadable", 0, exc.code
    except OSError:
        return "unreadable", 0, "os_error"
    dm = project.dm_path.relative_to(project.mod_dir).as_posix()
    body = "".join(f"{k}\0{v}\n" for k, v in sorted(files.items()) if k != dm)
    return sha256_bytes(body.encode("utf-8")), len(files) - (dm in files), None


def capture_identity(workspace: Path, slug: str, catalog: Catalog | None, catalog_state: str,
                     catalog_error: dict[str, Any] | None = None) -> dict[str, Any]:
    """Source, metadata, mod-folder files, declared dependencies and catalog, read once from disk.

    revision is a SHA-256 over all of them; any change to an input changes it."""
    project = open_project(workspace, slug)
    source = sha256_bytes(project.dm_path.read_bytes()) if project.dm_path.is_file() else None
    meta = sha256_bytes(project.meta_path.read_bytes())
    assets, files, asset_error = _asset_digest(project)
    deps = []
    for dep in project.meta.get("dependencies") or []:
        path = workspace / dep
        try:
            deps.append({"label": dep, "sha256": sha256_bytes(path.read_bytes())})
        except OSError:
            deps.append({"label": dep, "sha256": None})
    ident = {"source_sha256": source, "meta_sha256": meta, "assets_sha256": assets, "asset_files": files,
             "dependencies": deps, "catalog": _catalog_identity(catalog, catalog_state, catalog_error)}
    if asset_error:
        ident["assets_error"] = asset_error
    revision = sha256_bytes(json.dumps(ident, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return {"revision": revision, **ident}


def resolve_health_catalog(workspace: Path, slug: str, live: Catalog | None, live_error: dict[str, Any] | None
                           ) -> tuple[Catalog | None, dict[str, Any] | None, str]:
    """(catalog the project reads, error, state): snapshot, live, none, error or snapshot_invalid."""
    from .reference import resolve_catalog
    cat, err = resolve_catalog(workspace, slug, live, live_error)
    if cat is not None:
        return cat, None, "snapshot" if (cat.meta.get("reference_snapshot")) else "live"
    if err and err.get("code") == "reference_invalid":
        return None, err, "snapshot_invalid"
    return None, err, "error" if err else "none"


# ---------- findings ----------

_LINE_RE = re.compile(r"\b(line|L)\s?\d+", re.IGNORECASE)


def _message_key(message: Any) -> str:
    """Message text without line numbers, so a finding keeps its id when lines move."""
    return _LINE_RE.sub(r"\1 ?", str(message).strip())


def _key_part(value: Any) -> str:
    return str(value).strip().strip('"')


class _Findings:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def add(self, key: tuple, *, code: str, severity: str, category: str, message: str,
            obj: dict[str, Any] | None = None, asset: str | None = None, occurrence: dict[str, Any] | None = None,
            evidence: dict[str, Any] | None = None, action_code: str | None = None) -> dict[str, Any]:
        fid = hashlib.sha256(json.dumps([_key_part(k) for k in key], ensure_ascii=False).encode()).hexdigest()[:16]
        f = self.items.get(fid)
        if f is None:
            f = self.items[fid] = {
                "id": fid, "code": code, "severity": severity, "category": category,
                "title": TITLES.get(code) or code.replace("_", " ").capitalize(), "message": message,
                "location": {"file": None, "line": None, "object": obj, "asset": asset},
                "occurrences": [], "evidence": {}, "sources": [],
                "next_action": NEXT_ACTIONS.get(action_code or code) or DEFAULT_ACTIONS[severity]}
        elif SEVERITY_RANK[severity] < SEVERITY_RANK[f["severity"]]:
            # The most severe contributor names the finding; nothing is ever downgraded.
            f.update(code=code, severity=severity, message=message,
                     title=TITLES.get(code) or code.replace("_", " ").capitalize(),
                     next_action=NEXT_ACTIONS.get(action_code or code) or DEFAULT_ACTIONS[severity])
        if obj and not f["location"]["object"]:
            f["location"]["object"] = obj
        if asset and not f["location"]["asset"]:
            f["location"]["asset"] = asset
        if occurrence:
            f["occurrences"].append(occurrence)
            if occurrence.get("source") not in f["sources"]:
                f["sources"].append(occurrence.get("source"))
        for k, v in (evidence or {}).items():
            f["evidence"].setdefault(k, v)
        return f

    def finish(self) -> list[dict[str, Any]]:
        out = []
        for f in self.items.values():
            occ = sorted(f["occurrences"], key=lambda o: (o.get("file") or "", o.get("line") or 0, o.get("source") or ""))
            f["occurrences"] = occ
            places = {(o.get("file"), o.get("line"), o.get("command")) for o in occ}
            f["count"] = max(1, len(places))
            first = next((o for o in occ if o.get("line")), occ[0] if occ else None)
            if first:
                f["location"].update(file=first.get("file"), line=first.get("line"))
            f["sources"] = sorted(s for s in f["sources"] if s)
            out.append(f)
        out.sort(key=_order_key)
        return out


def _order_key(f: dict[str, Any]) -> tuple:
    obj = f["location"]["object"] or {}
    oid = obj.get("id")
    return (SEVERITY_RANK[f["severity"]], CATEGORY_RANK.get(f["category"], len(CATEGORIES)), f["code"],
            str(obj.get("kind") or ""), oid if isinstance(oid, int) else 10 ** 9, str(obj.get("name") or "").lower(),
            f["location"]["asset"] or "", f["id"])


class _Objects:
    """Maps source lines and graph keys to stable object identities (kind + id or name, never a line)."""

    def __init__(self, model: dict[str, Any]) -> None:
        graph = model.get("relationships") or {}
        self.by_key: dict[str, dict[str, Any]] = {}
        unnamed: dict[str, int] = {}
        for o in graph.get("objects") or []:
            ctx, ident, name = o.get("context"), o.get("id"), o.get("name")
            if isinstance(ident, int):
                stable = f"{ctx}:{ident}"
            elif ident is not None or (name and name != ctx):
                stable = f"{ctx}:name:{str(ident if ident is not None else name).lower()}"
            else:
                n = unnamed[f"{o.get('origin')}:{ctx}"] = unnamed.get(f"{o.get('origin')}:{ctx}", 0) + 1
                stable = f"{ctx}:unnamed:{n}"
            if o.get("origin") != "project":
                stable = f"{o.get('origin')}|{stable}"
            self.by_key[o["key"]] = {"key": stable, "kind": ctx, "id": ident if isinstance(ident, int) else None,
                                     "name": name, "origin": o.get("origin")}
        self.ranges: list[tuple[int, int, dict[str, Any]]] = []
        for group in ("monsters", "sites", "nations", "other_definitions"):
            for obj in model.get(group) or []:
                src = obj.get("source") or {}
                ctx = obj.get("context", obj.get("kind"))
                ref = self.by_key.get(f"{ctx}:line:{src.get('line')}")
                if ref and src.get("line"):
                    self.ranges.append((src["line"], src.get("end_line") or src["line"], ref))
        self.ranges.sort(key=lambda r: r[0])
        self.mod = {"key": "mod", "kind": "mod", "id": None, "name": None, "origin": "project"}

    def at_line(self, line: Any) -> dict[str, Any]:
        if isinstance(line, int):
            for start, end, ref in self.ranges:
                if start <= line <= end:
                    return ref
        return self.mod

    def project(self, kind: str, ident: Any) -> dict[str, Any]:
        for ref in self.by_key.values():
            if ref["origin"] == "project" and ref["kind"] == kind and ref["id"] == ident:
                return ref
        return {"key": f"{kind}:{ident}", "kind": kind, "id": ident, "name": None, "origin": "project"}


def _occ(source: str, item: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out = {"source": source, "file": item.get("file"), "line": item.get("line"), "command": item.get("command"),
           "code": item.get("code"), "severity": item.get("severity"), "message": item.get("message")}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def _validation_findings(F: _Findings, objs: _Objects, validation: dict[str, Any], catalog_ok: bool) -> None:
    for sev_key in ("errors", "warnings", "unverified"):
        for item in validation.get(sev_key) or []:
            code, sev = item["code"], item["severity"]
            obj = objs.at_line(item.get("line"))
            occ = _occ("validation", item)
            if code in IDENTITY_CODES and item.get("object_kind") is not None:
                target = objs.project(item["object_kind"], item.get("object_id"))
                F.add(("identity", target["key"]), code="id_collision" if sev == "error" else "identity_overlap",
                      severity=sev, category="identity", message=item["message"], obj=target, occurrence=occ)
            elif code in REFERENCE_CODES:
                F.add(("reference", obj["key"], item.get("command"), item.get("argument", item["message"])),
                      code=code, severity=sev, category="references", message=item["message"], obj=obj,
                      occurrence=occ, evidence={"argument": item.get("argument"), "catalog_available": catalog_ok})
            elif code.startswith("asset_") and item.get("asset"):
                # Missing, case-mismatched or linked files are one finding per referenced path (as in readiness).
                F.add(("asset_missing", item["asset"]), code=code, severity=sev, category="assets",
                      message=item["message"], obj=obj, asset=item["asset"], occurrence=occ)
            elif code in ASSET_CODES:
                F.add((code, item.get("asset") or obj["key"], _message_key(item["message"])), code=code,
                      severity=sev, category="assets", message=item["message"], obj=obj, asset=item.get("asset"),
                      occurrence=occ)
            else:
                F.add((code, obj["key"], item.get("command"), _message_key(item["message"])), code=code,
                      severity=sev, category="validation", message=item["message"], obj=obj, occurrence=occ)


def _asset_findings(F: _Findings, model: dict[str, Any]) -> None:
    file = (model.get("provenance") or {}).get("file")
    for a in model.get("assets") or []:
        if a.get("status") != "missing":
            continue
        users = a.get("used_by") or []
        F.add(("asset_missing", a["path"]), code="asset_missing", severity="error", category="assets",
              message=f"{a['path']} is named by the .dm but is not in the mod folder.", asset=a["path"],
              evidence={"used_by": [{k: u.get(k) for k in ("uid", "name", "command", "line")} for u in users]},
              occurrence={"source": "assets", "file": file, "line": users[0].get("line") if users else None,
                          "command": users[0].get("command") if users else None, "code": "asset_missing",
                          "severity": "error", "message": f"{len(users)} reference(s)"})


def _sprite_findings(F: _Findings, objs: _Objects, model: dict[str, Any], catalog: Catalog | None) -> None:
    from .browse import sprite_statuses
    file = (model.get("provenance") or {}).get("file")
    monsters = model.get("monsters") or []
    new = {u["uid"] for u in monsters if u.get("new")}
    for s in sprite_statuses(monsters, model.get("assets") or [], catalog):
        if s["uid"] not in new:
            continue  # Selected vanilla monsters keep the game's sprite by design.
        obj = objs.at_line(s.get("line"))
        occ = {"source": "sprites", "file": file, "line": s.get("line"), "command": None, "code": None,
               "severity": None, "message": None}
        if s["status"] == "missing" and not s["missing"]:
            F.add(("no_sprite_source", obj["key"]), code="no_sprite_source", severity="warning", category="sprites",
                  message="New unit has no #spr1, #copyspr or #copystats sprite source.", obj=obj,
                  occurrence={**occ, "code": "no_sprite_source", "severity": "warning"})
        elif s["status"] == "vanilla":
            src = s.get("source") or {}
            verified = src.get("verified")
            code, sev = ("borrowed_sprite", "info") if verified else ("unverified_sprite_source", "unverified")
            F.add((code, obj["key"]), code=code, severity=sev, category="sprites",
                  message=f"Sprite comes from {src.get('via')} {src.get('ref')}"
                          + ("" if verified else " (not confirmed by a catalog)") + ".", obj=obj,
                  evidence={"via": src.get("via"), "ref": src.get("ref")},
                  occurrence={**occ, "line": src.get("line") or s.get("line"), "code": code, "severity": sev})
        for o in s.get("overwritten") or []:
            F.add(("sprite_overwritten", obj["key"], o["command"]), code="sprite_overwritten", severity="warning",
                  category="sprites", message=f"Custom {o['command']} is replaced by a later #copystats.", obj=obj,
                  occurrence={**occ, "line": o["line"], "command": o["command"], "code": "sprite_overwritten",
                              "severity": "warning"})


def _compatibility_findings(F: _Findings, objs: _Objects, model: dict[str, Any], catalog_ok: bool) -> None:
    compat = model.get("compatibility") or {}
    graph = model.get("relationships") or {}
    file = (model.get("provenance") or {}).get("file")
    for ov in compat.get("overlaps") or []:
        cls = ov.get("classification")
        target = objs.project(ov.get("context"), ov.get("id")) if isinstance(ov.get("id"), int) else \
            {"key": f"{ov.get('context')}:name:{str(ov.get('name') or '').lower()}", "kind": ov.get("context"),
             "id": None, "name": ov.get("name"), "origin": "project"}
        target = {**target, "name": target.get("name") or ov.get("name")}
        last = ov.get("last_contributor") or {}
        occ = {"source": "compatibility", "file": file if last.get("origin") == "project" else last.get("origin"),
               "line": last.get("line"), "command": last.get("opener"), "code": cls,
               "severity": ov.get("severity"), "message": ov.get("reason")}
        evidence = {"origins": ov.get("origins"), "classification": cls,
                    "actions": [a.get("action") for a in ov.get("actions") or []]}
        if cls == "hard_id_collision":
            F.add(("identity", target["key"]), code="id_collision", severity="error", category="identity",
                  message=f"New {ov.get('context')} {ov.get('id')} reuses an existing identity ({', '.join(ov.get('origins') or [])}).",
                  obj=target, occurrence={**occ, "severity": "error"}, evidence=evidence)
        elif cls == "ambiguous_named_definition":
            F.add(("ambiguous_named_definition", target["key"]), code=cls, severity="warning", category="identity",
                  message=ov.get("reason") or "", obj=target, occurrence={**occ, "severity": "warning"}, evidence=evidence)
        else:
            F.add(("identity", target["key"]), code="identity_overlap", severity="info", category="identity",
                  message=f"Selector overrides a shared {ov.get('context')} identity ({', '.join(ov.get('origins') or [])}).",
                  obj=target, occurrence={**occ, "severity": "info"}, evidence=evidence)
    ambiguous = {(g.get("source", {}).get("key"), g.get("command"), _key_part(g.get("argument")))
                 for g in compat.get("guidance") or [] if g.get("classification") == "ambiguous_reference"}
    for edge in graph.get("unresolved") or []:
        src = objs.by_key.get(edge.get("from")) or objs.mod
        is_project = src.get("origin") == "project"
        command = f"#{edge.get('command')}"
        key = ("reference", src["key"], command, edge.get("argument"))
        if (edge.get("from"), edge.get("command"), _key_part(edge.get("argument"))) in ambiguous:
            code, sev = "ambiguous_reference", "warning"
        elif not catalog_ok:
            code, sev = "unverified_reference", "unverified"
        else:
            code, sev = "uncertain_reference", "warning"
        F.add(key, code=code, severity=sev, category="references",
              message=f"{command} {edge.get('argument')}: no {edge.get('target_context')} with this ID or name in the "
                      f"project, declared dependencies{' or catalog' if catalog_ok else ' (no catalog to check vanilla)'}.",
              obj=src, evidence={"argument": edge.get("argument"), "target_kind": edge.get("target_context"),
                                 "catalog_available": catalog_ok},
              occurrence={"source": "references", "file": file if is_project else src.get("origin"),
                          "line": edge.get("line"), "command": command, "code": code, "severity": sev,
                          "message": edge.get("relation")})
    for g in compat.get("guidance") or []:
        if g.get("classification") != "order_sensitive_reference":
            continue
        src = objs.by_key.get((g.get("source") or {}).get("key")) or objs.mod
        command = f"#{g.get('command')}"
        F.add(("order_sensitive_reference", src["key"], command, g.get("argument")), code="order_sensitive_reference",
              severity="warning", category="references",
              message=f"{command} {g.get('argument')}: the copy target is only defined in a later block.", obj=src,
              occurrence={"source": "compatibility", "file": file if src.get("origin") == "project" else src.get("origin"),
                          "line": g.get("line"), "command": command, "code": "order_sensitive_reference",
                          "severity": "warning", "message": None})


def classify_recruitment(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Recruitment classes for every new project monster, from explicit commands only."""
    sites = {s["uid"]: s for s in model.get("sites") or []}
    out = []
    for u in model.get("monsters") or []:
        if not u.get("new"):
            continue
        classes: set[str] = set()
        for r in u.get("recruitment") or []:
            via = str(r.get("via") or "").lstrip("#")
            if via in NORMAL_RECRUIT:
                classes.add("normal")
            elif via in ("homemon", "homecom", "mon", "com"):
                site = sites.get(r.get("site")) or {}
                classes.add("cap_only" if via.startswith("home") and site.get("start_site_of") else "site")
        for n in u.get("nations") or []:
            via = str(n.get("via") or "").lstrip("#")
            if via in START_ARMY:
                classes.add("start_army")
            elif via in DEFENCE:
                classes.add("defence")
            elif via in HERO:
                classes.add("hero")
        if u.get("summoning"):
            classes.add("summon")
        if u.get("role") == "pretender" or any(g.get("via") == "#addgod" for g in u.get("god_commands") or []):
            classes.add("pretender")
        for ref in u.get("used_by") or []:
            ctx, cmd = ref.get("context"), str(ref.get("command") or "")
            if ctx == "spell":
                classes.add("summon")
            elif ctx == "monster" and not cmd.startswith("copy") and ref.get("id") != u.get("id"):
                # Another unit's summon-like command summons it; shape commands make it an alternate form.
                classes.add("summon" if "summon" in cmd or cmd.startswith(("makemonster", "batstart")) else
                            "form" if "shape" in cmd or "form" in cmd else "referenced")
            elif ctx == "merc":
                classes.add("merc")
            elif ctx == "event":
                classes.add("event")
            elif ctx not in ("nation", "site", "monster"):
                classes.add("referenced")
        ordered = [c for c in RECRUITMENT_CLASSES if c in classes] or ["unassigned"]
        out.append({"uid": u["uid"], "id": u.get("id"), "name": u.get("name"), "role": u.get("role"),
                    "line": (u.get("source") or {}).get("line"), "classes": ordered})
    return out


def _recruitment_findings(F: _Findings, objs: _Objects, units: list[dict[str, Any]], file: str | None) -> None:
    for u in units:
        if u["classes"] != ["unassigned"]:
            continue
        obj = objs.at_line(u.get("line"))
        F.add(("unassigned_monster", obj["key"]), code="unassigned_monster", severity="info", category="recruitment",
              message="New unit is not recruited, summoned, a hero, a pretender, a form or otherwise referenced.",
              obj=obj, occurrence={"source": "recruitment", "file": file, "line": u.get("line"), "command": None,
                                   "code": "unassigned_monster", "severity": "info", "message": None})


def _catalog_findings(F: _Findings, state: str, err: dict[str, Any] | None, ref: dict[str, Any] | None) -> None:
    occ = {"source": "catalog", "file": None, "line": None, "command": None, "message": None}
    if state == "none":
        F.add(("catalog_unavailable",), code="catalog_unavailable", severity="unverified", category="catalog",
              message="No catalog or reference snapshot: vanilla IDs, names and donors cannot be checked.",
              occurrence={**occ, "code": "catalog_unavailable", "severity": "unverified"})
    elif state == "error":
        F.add(("catalog_error",), code="catalog_error", severity="unverified", category="catalog",
              message=f"The configured catalog could not be read ({(err or {}).get('code')}); vanilla references are unverified.",
              occurrence={**occ, "code": "catalog_error", "severity": "unverified"}, evidence={"error": err})
    elif state == "snapshot_invalid":
        F.add(("reference_snapshot_invalid",), code="reference_snapshot_invalid", severity="warning",
              category="catalog", message="The project's reference snapshot failed verification and is not used.",
              occurrence={**occ, "code": "reference_snapshot_invalid", "severity": "warning"}, evidence={"error": err})
    if ref and ref.get("state") == "stale":
        F.add(("reference_snapshot_stale",), code="reference_snapshot_stale", severity="info", category="catalog",
              message="The reference snapshot differs from the live catalog; the snapshot stays in use.",
              occurrence={**occ, "code": "reference_snapshot_stale", "severity": "info"},
              evidence={"snapshot": ref.get("snapshot"), "version": ref.get("version")})
    if ref and ref.get("sprites_missing_now_count"):
        F.add(("reference_snapshot_sprites",), code="reference_snapshot_sprites", severity="info", category="catalog",
              message=f"{ref['sprites_missing_now_count']} referenced vanilla unit sprite(s) are not in the snapshot.",
              occurrence={**occ, "code": "reference_snapshot_sprites", "severity": "info"},
              evidence={"units": ref.get("sprites_missing_now")})


def _diagnostic_findings(F: _Findings, model: dict[str, Any]) -> None:
    for d in model.get("diagnostics") or []:
        sev = d.get("severity") if d.get("severity") in SEVERITY_RANK else "error"
        F.add(("diagnostic", d.get("code")), code=str(d.get("code")).split(":")[0], severity=sev, category="integrity",
              message=d.get("message") or "", evidence={"diagnostic": d.get("code")},
              occurrence={"source": "model", "file": None, "line": None, "command": None, "code": d.get("code"),
                          "severity": sev, "message": d.get("message")})


def _reconcile(findings: list[dict[str, Any]], validation: dict[str, Any] | None) -> dict[str, Any]:
    """Every validation item must appear as an occurrence of a finding at least as severe as itself."""
    counted = {"errors": 0, "warnings": 0, "unverified": 0}
    keys = {"error": "errors", "warning": "warnings", "unverified": "unverified"}
    downgraded = 0
    for f in findings:
        for o in f["occurrences"]:
            if o.get("source") == "validation" and o.get("severity") in keys:
                counted[keys[o["severity"]]] += 1
                downgraded += SEVERITY_RANK[f["severity"]] > SEVERITY_RANK[o["severity"]]
    expected = (validation or {}).get("counts")
    return {"validation_counts": expected, "accounted": counted, "downgraded": downgraded,
            "complete": expected is None or (expected == counted and not downgraded)}


def build_health(workspace: Path, slug: str, live: Catalog | None, live_error: dict[str, Any] | None = None,
                 model: dict[str, Any] | None = None, expected_revision: str | None = None) -> dict[str, Any]:
    """Project health for the captured revision. model may be a cached browser model; it is rebuilt when its
    source hash does not match the captured source."""
    from .browse import build_project_model
    from .reference import reference_status
    catalog, cat_err, cat_state = resolve_health_catalog(workspace, slug, live, live_error)
    before = capture_identity(workspace, slug, catalog, cat_state, cat_err)
    F = _Findings()
    model_error = None
    if model is None or (model.get("provenance") or {}).get("sha256") != before["source_sha256"]:
        try:
            model = build_project_model(workspace, slug, catalog)
        except (KosmoError, OSError, ValueError, UnicodeError) as exc:
            model = None
            model_error = exc.to_dict() if isinstance(exc, KosmoError) else {"code": "read_error", "message": str(exc)}
    ref = None
    try:
        ref = reference_status(workspace, slug, live, model)
    except (KosmoError, OSError, ValueError):
        ref = None
    catalog_ok = catalog is not None
    units: list[dict[str, Any]] = []
    validation = None
    if model is None:
        F.add(("model_unavailable",), code="model_unavailable", severity="error", category="integrity",
              message=f"The project could not be read: {model_error.get('message')}", evidence={"error": model_error},
              occurrence={"source": "model", "file": None, "line": None, "command": None,
                          "code": model_error.get("code"), "severity": "error", "message": model_error.get("message")})
    else:
        objs = _Objects(model)
        validation = model.get("validation")
        file = (model.get("provenance") or {}).get("file")
        _diagnostic_findings(F, model)
        if validation:
            _validation_findings(F, objs, validation, catalog_ok)
        _asset_findings(F, model)
        _sprite_findings(F, objs, model, catalog)
        _compatibility_findings(F, objs, model, catalog_ok)
        units = classify_recruitment(model)
        _recruitment_findings(F, objs, units, file)
    _catalog_findings(F, cat_state, cat_err, ref)
    after = capture_identity(workspace, slug, catalog, cat_state, cat_err)
    consistent = before["revision"] == after["revision"] and (
        model is None or (model.get("provenance") or {}).get("sha256") == before["source_sha256"])
    if not consistent:
        F.add(("changed_during_check",), code="changed_during_check", severity="warning", category="integrity",
              message="The project changed while health was read; findings may mix revisions.",
              evidence={"before": before["revision"], "after": after["revision"]},
              occurrence={"source": "health", "file": None, "line": None, "command": None,
                          "code": "changed_during_check", "severity": "warning", "message": None})
    findings = F.finish()
    reconciliation = _reconcile(findings, validation)
    counts = {s: sum(f["severity"] == s for f in findings) for s in SEVERITIES}
    status = "blocked" if counts["error"] else "attention" if counts["warning"] else \
        "unverified" if counts["unverified"] else "clear"
    recruit_counts = {c: sum(c in u["classes"] for u in units) for c in RECRUITMENT_CLASSES}
    return {
        "schema": SCHEMA, "project": slug, "tool_version": __version__,
        "revision": before["revision"], "identity": {**before, "consistent": consistent},
        "expected_revision": expected_revision,
        "stale": expected_revision is not None and expected_revision != before["revision"],
        "status": status, "ok": not counts["error"], "counts": counts,
        "findings": findings,
        "recruitment": {"counts": recruit_counts, "units": units,
                        "note": "Classes come from explicit nation, site, spell, god and form references. "
                                "Unassigned units are informational."},
        "catalog": {**_catalog_identity(catalog, cat_state, cat_err),
                    "reference_state": (ref or {}).get("state"),
                    "dataset": (catalog.meta.get("source") if catalog else None)},
        "scope": {
            "checked": ["validation", "assets", "sprites", "references", "compatibility", "recruitment", "catalog"],
            "not_checked": NOT_CHECKED,
            "dependencies": [d["label"] for d in before["dependencies"]],
            "complete": False,
        },
        "reconciliation": reconciliation,
        "reports": {"validation": "validate_mod", "readiness": "project_view.readiness",
                    "compatibility": "author_state compatibility", "references": "project_view.relationships"},
        "limitations": LIMITATIONS,
    }
