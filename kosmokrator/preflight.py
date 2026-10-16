"""Installation preflight: one verified export or prepared Workshop bundle against the configured mods folder.

The bundle is the exact verified artifact: an export re-hashed against its manifest, or a prepared Workshop content
folder re-hashed against its manifest (the same checks prepare and install use). Its .dm definitions are compared
with the .dm files the bounded installed-mods scan reads from the server's configured mods folder. Nothing is
written: no lock, no state folder, no cache file.

Classification of a shared numbered identity (kind and ID):
  hard_id_collision          error   the bundle creates (#new...) an ID an installed mod also defines;
  independent_nation         error   both define custom nation 150+ (#selectnation 150+ creates a new nation);
  undeclared_dependency_patch warning the bundle selects an ID only an installed, undeclared mod creates;
  shared_override            warning both select the same existing identity (e.g. a vanilla nation below 150);
  declared_dependency_patch  info    the installed file is byte-identical to a declared dependency and the bundle
                                     only selects (patches) it.
Load order between installed mods is unknown, and reordering never repairs an independent definition collision.
Installed is not enabled, and Workshop subscriptions outside the configured folder are not scanned.

The fingerprint covers the export/Workshop manifest, the bundle's .dm hashes, every scanned installed .dm (path,
hash, size), the scan's completeness, the destination's ownership state and declared dependency hashes. Install
recomputes it under the project lock immediately before its first write and refuses a stale, blocked, incomplete
or unacknowledged result. This cannot make the filesystem atomic across processes: files can still change after
the check.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .dmparse import DEFINING
from .errors import KosmoError
from .paths import contained
from .project import (MAX_SCAN_BYTES, MAX_SCAN_FILES, MAX_SCAN_TOTAL_BYTES, Project, ScanBudget, open_project,
                      scan_definitions, scan_installed_mods, sha256_bytes)

SCHEMA = "kosmokrator.preflight/1"
MAX_FINDINGS = 200
CUSTOM_NATION_MIN = 150  # #selectnation (p.41): 150+ creates a new nation

LIMITATIONS = [
    "Installed is not enabled: the game's enabled-mod list is not read, so a finding may involve a mod that is off.",
    "Only the configured mods folder is scanned (top level and one folder down). Steam Workshop subscriptions and "
    "other folders are not scanned.",
    "Load order between mods is unknown. Reordering never repairs two independent definitions of one ID.",
    "Numbered identities only (monster, site, nation, weapon, armor and numbered item/spell selectors). Named "
    "spells, items and events are not compared.",
    "Static comparison only: not proof that the game loads the mods together or that gameplay is balanced.",
    "The fingerprint is rechecked right before install writes; files can still change afterwards.",
]
ACTIONS = {
    "remap_ids": "Reserve a free ID with allocate_ids (it scans installed mods), update every reference with a guarded "
                 "edit, validate, export, prepare and check again. Changing load order does not fix this.",
    "move_installed_mod": "If that installed mod is not used, move it out of the mods folder yourself and check again. "
                          "Kosmokrator never changes other mods.",
    "review_override": "Both mods change the same identity; which commands win depends on load order, which is "
                       "unknown. Confirm both changes are intended, then acknowledge this check.",
    "declare_dependency": "If this mod patches that one on purpose, add an identical copy of its .dm to the workspace "
                          "and declare it as a dependency, then check again.",
    "none": "Declared dependency patch; no action unless the dependency changed.",
}
MESSAGES = {
    "hard_id_collision": "The bundle creates {kind} {id}, which an installed mod also defines.",
    "independent_nation": "Both define custom nation {id} (150+ creates a new nation); they cannot both load correctly.",
    "undeclared_dependency_patch": "The bundle changes {kind} {id}, which only an installed mod that is not a declared "
                                   "dependency creates.",
    "shared_override": "The bundle and an installed mod both change existing {kind} {id}.",
    "declared_dependency_patch": "The bundle changes {kind} {id} from a declared dependency.",
}


def _command(kind: str, new: bool) -> str:
    return "#" + DEFINING[kind][0 if new else 1]


def _classify(kind: str, ident: int, mine: dict[str, Any], theirs: dict[str, Any], dependency: bool
              ) -> tuple[str, str, list[str]]:
    """(classification, severity, actions) for one bundle definition sharing a numbered identity."""
    if mine["new"]:
        return "hard_id_collision", "error", ["remap_ids", "move_installed_mod"]
    if dependency:
        return "declared_dependency_patch", "info", ["none"]
    if kind == "nation" and ident >= CUSTOM_NATION_MIN:
        return "independent_nation", "error", ["remap_ids", "move_installed_mod"]
    if theirs["new"]:
        return "undeclared_dependency_patch", "warning", ["declare_dependency", "review_override"]
    return "shared_override", "warning", ["review_override", "declare_dependency"]


def _dependencies(project: Project) -> list[dict[str, Any]]:
    out = []
    for dep in project.meta.get("dependencies") or []:
        try:
            p = contained(project.workspace, dep, what="dependency")
            out.append({"label": dep, "sha256": sha256_bytes(p.read_bytes()) if p.is_file() else None})
        except (OSError, KosmoError):
            out.append({"label": dep, "sha256": None})
    return out


def load_target(workspace: Path, project: Project, target: Any) -> dict[str, Any]:
    """The verified bundle: a prepared Workshop folder (id <slug>-ws-...) or an export, re-hashed against its manifest."""
    from .workshop import WS_ID_TAIL, _entry, _export_payload, _read_manifest, _verified_content
    if not isinstance(target, str) or not target or len(target) > 120:
        raise KosmoError("bad_request", "target must be an export id or a prepared Workshop id.")
    if re.fullmatch(re.escape(project.slug) + WS_ID_TAIL, target):
        e = _entry(project, target)
        man = _read_manifest(e["manifest"])
        return {"type": "workshop", "id": target, "manifest": man, "payload": _verified_content(project, e, man),
                "sha256": man.get("sha256")}
    source, payload = _export_payload(workspace, project.slug, target)
    man = source["manifest"]
    return {"type": "export", "id": target, "manifest": man, "payload": payload,
            "sha256": (man.get("validation") or {}).get("sha256")}


def build_report(project: Project, target: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Compare one loaded, verified bundle with the installed mods. Read-only."""
    from .workshop import destination_status
    payload: dict[str, bytes] = target["payload"]
    new = {r: sha256_bytes(d) for r, d in payload.items()}
    try:
        dest = destination_status(project, config, new)
    except KosmoError as exc:  # e.g. the destination is a link: never owned, never followed
        dest = {"state": "conflict" if config.get("available") else "unavailable", "conflict": exc.message,
                "reason": exc.message, "destination": None}
    owned = dest.get("state") in ("identical", "managed")
    budget = ScanBudget()
    scan = scan_installed_mods(config, budget, skip_folder=project.slug if owned else None)
    deps = _dependencies(project)
    dep_hashes = {d["sha256"] for d in deps if d["sha256"]}

    bundle_dm = []
    mine: list[tuple[str, dict[str, Any]]] = []
    for rel in sorted(payload):
        if rel.lower().endswith(".dm"):
            digest, defs = scan_definitions(payload[rel])
            bundle_dm.append({"path": f"{project.slug}/{rel}", "sha256": digest})
            mine += [(f"{project.slug}/{rel}", d) for d in defs if d["id"] is not None]
    theirs: dict[tuple[str, int], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for src in scan["sources"]:
        for d in src["definitions"]:
            if d["id"] is not None:
                theirs.setdefault((d["kind"], d["id"]), []).append((src, d))

    findings: dict[str, dict[str, Any]] = {}
    for file, d in mine:
        for src, other in theirs.get((d["kind"], d["id"]), []):
            dependency = src["sha256"] in dep_hashes
            cls, severity, actions = _classify(d["kind"], d["id"], d, other, dependency)
            key = sha256_bytes(json.dumps([cls, d["kind"], d["id"], src["path"]]).encode())[:16]
            f = findings.get(key)
            if f is None:
                findings[key] = f = {
                    "id": key, "code": cls, "severity": severity, "kind": d["kind"], "object_id": d["id"],
                    "message": MESSAGES[cls].format(kind=d["kind"], id=d["id"]),
                    "bundle": [], "installed": [], "declared_dependency": dependency, "load_order": "unknown",
                    "installed_source": {"file": src["path"], "sha256": src["sha256"],
                                         "mods_dir": scan["mods_dir"], "enabled": "unknown"},
                    "actions": [{"action": a, "automatic": False, "reason": ACTIONS[a]} for a in actions]}
            loc = {"file": file, "line": d["line"], "command": _command(d["kind"], d["new"]), "name": d["name"]}
            if loc not in f["bundle"]:
                f["bundle"].append(loc)
            loc = {"file": src["path"], "line": other["line"], "command": _command(other["kind"], other["new"]),
                   "name": other["name"]}
            if loc not in f["installed"]:
                f["installed"].append(loc)
    items = list(findings.values())
    if dest.get("state") == "conflict":
        items.append({"id": "destination_conflict", "code": "destination_conflict", "severity": "error",
                      "kind": None, "object_id": None, "load_order": "unknown",
                      "message": f"{dest.get('destination') or 'The install destination'} exists and is not an "
                                 "unchanged install from this project; it is scanned like any other installed mod.",
                      "bundle": [], "installed": [{"file": f"{project.slug}/{r}", "line": None, "command": None,
                                                    "name": None} for r in dest.get("unmanaged") or []],
                      "evidence": {"conflict": dest.get("conflict"), "unmanaged_count": dest.get("unmanaged_count")},
                      "actions": [{"action": "move_installed_mod", "automatic": False,
                                   "reason": "Back up and move that folder yourself (keep its dom6ws_pfid if it is "
                                             "published), then check again. Nothing is overwritten."}]})
    complete = bool(scan["available"]) and budget.complete
    if not complete:
        why = scan.get("reason") if not scan["available"] else "Some installed .dm files could not be read or a " \
            "scan limit was reached; IDs defined there were not compared."
        items.append({"id": "scan_incomplete", "code": "scan_incomplete", "severity": "error", "kind": None,
                      "object_id": None, "load_order": "unknown", "message": why, "bundle": [], "installed": [],
                      "evidence": {"unreadable": budget.unreadable[:20], "scan_limit_reached": budget.truncated[:20]},
                      "actions": [{"action": "fix_scan", "automatic": False,
                                   "reason": "Fix or remove the unreadable entries (links are never followed), or "
                                             "configure the mods folder, then check again."}]})
    rank = {"error": 0, "warning": 1, "info": 2}
    items.sort(key=lambda f: (rank[f["severity"]], f["kind"] or "", f["object_id"] or 0, f["id"]))
    counts = {s: sum(f["severity"] == s for f in items) for s in rank}

    destination = {k: dest.get(k) for k in ("state", "destination", "managed", "pfid_present", "unmanaged",
                                            "unmanaged_count", "reason")}
    identity = {
        "schema": SCHEMA, "project": project.slug,
        "target": {"type": target["type"], "id": target["id"], "sha256": target["sha256"],
                   "manifest_sha256": sha256_bytes(json.dumps(target["manifest"], sort_keys=True,
                                                              ensure_ascii=False).encode("utf-8")),
                   "dm_files": bundle_dm},
        "mods_dir": scan["mods_dir"], "installed": [[s["path"], s["sha256"], s["bytes"]] for s in scan["sources"]],
        "skipped": scan["skipped"], "unreadable": budget.unreadable, "scan_limit_reached": budget.truncated,
        "available": scan["available"], "destination": destination, "dependencies": deps,
    }
    fingerprint = sha256_bytes(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    status = "incomplete" if not complete else "blocked" if counts["error"] else \
        "review" if counts["warning"] else "pass"
    workshop = target["type"] == "workshop"
    install_reason = None if workshop and status in ("pass", "review") else \
        "Install applies to prepared Workshop folders; prepare one from this export." if not workshop else \
        {"incomplete": "The installed-mods scan is incomplete.",
         "blocked": "Resolve the errors above, then check again."}[status]
    return {
        "schema": SCHEMA, "project": project.slug, "fingerprint": fingerprint, "status": status,
        "counts": counts, "findings": items[:MAX_FINDINGS], "findings_total": len(items),
        "target": identity["target"],
        "install": {"allowed": install_reason is None, "reason": install_reason,
                    "requires_acknowledgement": status == "review", "destination": destination,
                    "own_install_excluded": owned},
        "coverage": {"mods_dir": scan["mods_dir"], "source": scan["source"], "available": scan["available"],
                     "reason": scan["reason"], "dm_files_scanned": scan["dm_files"], "bytes_scanned": budget.bytes,
                     "sources": [{"file": s["path"], "sha256": s["sha256"], "bytes": s["bytes"],
                                  "definitions": len(s["definitions"])} for s in scan["sources"][:MAX_FINDINGS]],
                     "skipped": scan["skipped"], "unreadable": budget.unreadable[:20],
                     "unreadable_count": len(budget.unreadable), "scan_limit_reached": budget.truncated[:20],
                     "limits": {"files": MAX_SCAN_FILES, "bytes_per_file": MAX_SCAN_BYTES,
                                "total_bytes": MAX_SCAN_TOTAL_BYTES, "depth": "top level and one folder down"},
                     "complete": complete, "links_followed": False, "enabled_state": "unknown",
                     "not_scanned": ["Steam Workshop subscriptions outside the configured folder",
                                     "the game's enabled-mod list", "named (unnumbered) definitions"]},
        "dependencies": deps,
        "limitations": LIMITATIONS,
    }


def preflight(workspace: Path, slug: str, target: Any, config: dict[str, Any]) -> dict[str, Any]:
    """Read-only preflight of one export or prepared Workshop folder against the configured mods folder."""
    project = open_project(workspace, slug)
    return build_report(project, load_target(workspace, project, target), config)


def require_current(report: dict[str, Any], body: dict[str, Any]) -> None:
    """Refuse an install unless the caller saw exactly this passing (or acknowledged) preflight."""
    expected, ack = body.get("expected_preflight"), body.get("acknowledge_review")
    details = {"fingerprint": report["fingerprint"], "status": report["status"], "counts": report["counts"]}
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise KosmoError("preflight_required", "Check compatibility first, then install with its fingerprint "
                         "(expected_preflight).", **details)
    if expected != report["fingerprint"]:
        raise KosmoError("preflight_stale", "Installed mods, the bundle or the destination changed since the check. "
                         "Nothing was written; check compatibility again.", **details)
    if report["status"] in ("blocked", "incomplete"):
        raise KosmoError("preflight_blocked", f"The compatibility check is {report['status']}; nothing was written.",
                         **details)
    if report["status"] == "review" and ack != report["fingerprint"]:
        raise KosmoError("preflight_review", "Review the shared-identity warnings and acknowledge this check "
                         "(acknowledge_review = fingerprint) before installing.", **details)
