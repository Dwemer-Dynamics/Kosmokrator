"""Read-only inheritance evidence over the browser model; never simulates game behavior."""
from __future__ import annotations

import copy
from typing import Any


def _reference(value: Any) -> int | str | None:
    text = str(value).strip().strip('"') if value is not None else ""
    try:
        return int(text)
    except ValueError:
        return text or None


def _fields(value: Any, path: str = "") -> list[dict[str, Any]]:
    """Flatten existing resolver evidence without changing its confidence or values."""
    out = []
    if isinstance(value, dict):
        if "source" in value and ("value" in value or "ref" in value or "mask" in value):
            status = str(value.get("status", "resolved"))
            source = value.get("source")
            state = ("unresolved" if value.get("unresolved") or "unresolved" in status or "not modelled" in status or
                     "assumed" in status else "cleared" if source == "cleared" else
                     "retained" if source in ("donor", "catalog") else
                     "authored" if source == "authored" else "unresolved")
            out.append({"field": path, "state": state, **copy.deepcopy(value)})
        elif "status" in value:
            status = str(value["status"])
            out.append({"field": path, "state": "unresolved" if "unresolved" in status else
                        "recorded", **copy.deepcopy(value)})
        else:
            for key, child in value.items():
                if key not in ("authored_traits", "authored_traits_note", "note"):
                    child_fields = _fields(child, f"{path}.{key}" if path else key)
                    list_status = value.get(f"{key}_status", {})
                    if isinstance(list_status, dict) and "unresolved" in str(list_status.get("status", "")):
                        for field in child_fields:
                            field["state"] = "unresolved"
                            field["list_status"] = copy.deepcopy(list_status)
                    out.extend(child_fields)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            out.extend(_fields(child, f"{path}[{index}]"))
    return out


def inheritance_report(model: dict[str, Any], catalog=None) -> dict[str, Any]:
    """Explain copy/reset history and resolver limits for every monster in a project model."""
    units = model.get("monsters", [])
    by_id = {u.get("id"): u for u in units if u.get("id") is not None}
    rows = {}
    catalog_issue = None
    if catalog is not None:
        try:
            rows = {str(r.get("id")): r for r in catalog.table("units")}
        except (OSError, ValueError, KeyError) as exc:
            catalog_issue = str(exc)
        except Exception as exc:
            # Catalog adapters report their own typed errors; preserve the evidence as uncertainty.
            catalog_issue = f"{type(exc).__name__}: {exc}"

    def donor_entry(ref, line, owner):
        row = rows.get(str(ref))
        saved = owner.get("donor") or {}
        if row is None and saved.get("ref") == ref:
            row = saved.get("catalog_row")
        local = by_id.get(ref)
        entry = {"ref": ref, "line": line, "origin": "catalog" if row else
                 "project" if local else "unknown", "name": (row or local or {}).get("name")}
        if local and row:
            entry.update(status="unresolved", reason="project and catalog IDs overlap; source ordering needs review")
        elif row:
            entry.update(status="catalog_reference", catalog=(model.get("provenance") or {}).get("catalog"))
        elif local:
            entry.update(status="unresolved", reason="project donor chain is not resolved by the unit resolver",
                         uid=local.get("uid"), donor_line=(local.get("source") or {}).get("line"))
            if (local.get("source") or {}).get("line", 0) >= (line or 0):
                entry["ordering_uncertainty"] = "donor is declared at or after this copy"
        else:
            entry.update(status="unresolved", reason="donor not found" if catalog is not None else
                         "catalog not supplied; donor existence cannot be checked")
        return entry

    # All authored project-copy edges are evidence, including copies later overwritten.
    edges = {u.get("id"): [_reference((a.get("args") or [None])[0]) for a in u.get("authored", [])
                           if a.get("command", "").lstrip("#") == "copystats"] for u in units}
    reports = []
    for u in units:
        history, donors, issues = [], [], copy.deepcopy(u.get("unresolved", []))
        traits = {t.get("line"): t for t in (u.get("resolved") or {}).get("authored_traits", [])}
        for a in u.get("authored", []):
            command = a.get("command", "").lstrip("#")
            effect = a.get("effect", "not modelled")
            trait_status = str(traits.get(a.get("line"), {}).get("status", ""))
            state = ("overwritten" if "overwritten" in effect else
                     "cleared" if trait_status.startswith("ended by") else
                     "unresolved" if "unsupported" in effect or "unresolved" in effect or
                     "not modelled" in effect else "recorded")
            item = {"line": a.get("line"), "command": a.get("command"),
                    "args": copy.deepcopy(a.get("args", [])), "raw": a.get("raw"),
                    "effect": effect, "state": state}
            if trait_status:
                item["trait_status"] = trait_status
            if command in ("copystats", "selectmonster"):
                donor = donor_entry(_reference((a.get("args") or [None])[0]), a.get("line"), u)
                donor["command"] = a.get("command")
                donors.append(donor)
                item["donor"] = copy.deepcopy(donor)
                if donor["status"] == "unresolved":
                    issues.append({"line": a.get("line"), "reason": donor["reason"]})
            if command in ("clear", "clearspec", "clearmagic", "clearweapons", "cleararmor"):
                item["reset"] = True
                item["scope"] = {"clear": "all modelled fields", "clearspec":
                    "modelled specials and god costs; other ability clearing remains uncertain",
                    "clearmagic": "magic paths and random picks", "clearweapons": "weapons",
                    "cleararmor": "armour"}[command]
            history.append(item)

        cycles = []
        pending = [(u.get("id"), [u.get("id")])]
        visited = set()
        while pending:
            current, chain = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            for target in edges.get(current, []):
                if target not in by_id:
                    continue
                if target in chain:
                    cycle = chain + [target]
                    if cycle not in cycles:
                        cycles.append(cycle)
                elif len(chain) <= len(by_id):
                    pending.append((target, chain + [target]))
        if cycles:
            issues.append({"line": (u.get("source") or {}).get("line"),
                           "reason": "project copy graph contains a cycle; no effective values inferred",
                           "chains": cycles})
        fields = _fields(u.get("resolved") or {})
        unusual = copy.deepcopy((u.get("resolved") or {}).get("unmodelled_donor_columns", {}))
        authored_unmodelled = [copy.deepcopy(a) for a in u.get("unsupported", [])]
        reports.append({"uid": u.get("uid"), "id": u.get("id"), "name": u.get("name"),
                        "source": {k: v for k, v in (u.get("source") or {}).items() if k != "text"},
                        "donors": donors, "history": history, "fields": fields,
                        "unmodelled_donor_columns": unusual, "unsupported": authored_unmodelled,
                        "issues": issues, "cycles": cycles,
                        "counts": {state: sum(f["state"] == state for f in fields)
                                   for state in ("retained", "authored", "cleared", "unresolved")}})
    return {"schema": "kosmokrator.inheritance/1", "provenance": copy.deepcopy(model.get("provenance", {})),
            "monsters": reports, "catalog_issue": catalog_issue,
            "counts": {"monsters": len(reports), "with_issues": sum(bool(r["issues"]) for r in reports),
                       "with_unmodelled_abilities": sum(bool(r["unmodelled_donor_columns"] or r["unsupported"])
                                                        for r in reports)},
            "limits": ["Static source and catalog evidence, not game execution.",
                       "Project donor chains and cycles are reported, not resolved.",
                       "Reset assumptions for unmodelled abilities remain unresolved.",
                       "History retains overwritten lines; earlier unresolved diagnostics may be historical.",
                       "Fields show the existing resolver's final model, not a complete game-state simulation."]}
