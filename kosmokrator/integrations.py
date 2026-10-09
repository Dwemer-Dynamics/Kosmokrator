"""Optional local tools: fixed adapters, reproducible previews and isolated outputs.

Configuration is administrator-owned JSON in the workspace, never browser supplied.
GUI-only tools provide a handoff rather than pretending to have a generation API.
"""
from __future__ import annotations

import datetime as dt
import json
import io
import os
from pathlib import Path
import secrets
import subprocess
import re
import zipfile
from typing import Any

from .errors import KosmoError
from .dmparse import decode_dm, parse
from .paths import atomic_write_bytes, contained, is_link
from .project import open_project, sha256_bytes

TOOLS = {
    "domerger": {"url": "https://github.com/Leiriri/domerger", "mode": "merge", "license": "GPL-3.0",
                 "limitations": "Name-reference conflicts and some event references remain unsupported; preserve reported load order."},
    "spritegen": {"url": "https://github.com/elmokki/nationgen", "mode": "manual", "license": "not established",
                  "limitations": "Interactive Java sprite composer; no verified unattended generation interface. Import exported frames through the unit artwork editor."},
}
CONFIG = ".kosmokrator-tools.json"
RUN_ID = re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{10}$")


def _config(workspace: Path) -> dict[str, Any]:
    path = contained(workspace, CONFIG)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except (ValueError, OSError) as exc:
        raise KosmoError("tool_config_invalid", "Cannot read local tool configuration.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tools", {}), dict):
        raise KosmoError("tool_config_invalid", "Configuration needs a tools object.")
    return data.get("tools", {})


def _entry(workspace: Path, tool: str) -> dict[str, Any]:
    if tool not in TOOLS:
        raise KosmoError("unknown_tool", "Unknown external tool.")
    entry = _config(workspace).get(tool, {})
    if not isinstance(entry, dict):
        raise KosmoError("tool_config_invalid", "Tool configuration must be an object.")
    return entry


def _installation(entry: dict[str, Any]) -> tuple[Path, Path]:
    if not isinstance(entry.get("directory", ""), str) or not isinstance(entry.get("executable", ""), str):
        raise KosmoError("tool_config_invalid", "Tool directory and executable must be strings.")
    root = Path(entry.get("directory", "")).expanduser()
    if not root.is_absolute() or not root.is_dir() or is_link(root):
        raise KosmoError("tool_not_configured", "Configure an existing absolute tool directory in local administrator configuration.")
    root = root.resolve()
    executable = contained(root, entry.get("executable", ""), what="tool executable")
    if not executable.is_file():
        raise KosmoError("tool_missing", "Configured executable is missing.")
    return root, executable


def tool_status(workspace: Path) -> dict[str, Any]:
    result = []
    for tool, info in TOOLS.items():
        entry = _entry(workspace, tool)
        status = "not_configured"
        fingerprint = None
        try:
            _, executable = _installation(entry)
            status = "manual_handoff" if info["mode"] == "manual" else "ready"
            fingerprint = sha256_bytes(executable.read_bytes())
        except KosmoError:
            if entry:
                status = "missing_or_invalid"
        result.append({"id": tool, **info, "status": status,
                       "runner_available": info["mode"] != "manual",
                       "version": entry.get("version"), "version_provenance": "administrator supplied",
                       "executable_sha256": fingerprint})
    return {"tools": result, "configuration": CONFIG,
            "note": "No bundled tools or automatic downloads; configure locally, then preview. Outputs never install into the game."}


def _number(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise KosmoError("bad_tool_request", f"{name} must be an integer between {low} and {high}.")
    return value


def _data_manifest(root: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Fingerprint runtime data as well as the executable for stale-preview detection."""
    files = []
    for name in names:
        source = contained(root, name)
        paths = sorted(source.rglob("*")) if source.is_dir() else [source]
        for path in paths:
            safe = contained(root, path)
            if safe.is_file():
                files.append({"path": safe.relative_to(root).as_posix(),
                              "sha256": sha256_bytes(safe.read_bytes()), "bytes": safe.stat().st_size})
    return files


def preview_tool(workspace: Path, tool: str, request: dict[str, Any]) -> dict[str, Any]:
    """Produce a stable fingerprint of configuration, options and every input file."""
    if not isinstance(request, dict):
        raise KosmoError("bad_tool_request", "Tool request must be an object.")
    entry = _entry(workspace, tool)
    info = TOOLS[tool]
    allowed = {"projects"} if tool == "domerger" else set()
    if set(request) - allowed:
        raise KosmoError("bad_tool_request", "Unexpected tool option; inspect the adapter's supported options.")
    if info["mode"] == "manual":
        return {"tool": tool, "mode": "manual", "runnable": False, "instructions": info["limitations"],
                "source_url": info["url"]}
    root, executable = _installation(entry)
    options: dict[str, Any] = {}
    inputs = []
    if tool == "domerger":
        projects = request.get("projects")
        if (not isinstance(projects, list) or not 1 <= len(projects) <= 20
                or not all(isinstance(p, str) for p in projects) or len(set(projects)) != len(projects)):
            raise KosmoError("bad_tool_request", "Choose 1–20 distinct project slugs.")
        for slug in projects:
            project = open_project(workspace, slug)
            files = []
            for path in sorted(project.mod_dir.rglob("*")):
                safe = contained(project.mod_dir, path)
                if safe.is_file():
                    files.append({"path": safe.relative_to(project.mod_dir).as_posix(),
                                  "sha256": sha256_bytes(safe.read_bytes()), "bytes": safe.stat().st_size})
            if sum(f["bytes"] for f in files) > 256 * 1024 * 1024:
                raise KosmoError("tool_input_large", "A project exceeds the 256 MB adapter input limit.")
            inputs.append({"project": slug, "files": files})
        options["projects"] = projects
    plan = {"tool": tool, "mode": info["mode"], "runnable": True, "options": options, "inputs": inputs,
            "configuration_sha256": sha256_bytes(json.dumps(entry, sort_keys=True).encode()),
            "executable_sha256": sha256_bytes(executable.read_bytes()), "version": entry.get("version"),
            "source_url": info["url"], "limitations": info["limitations"],
            "output": "A new isolated directory under workspace/tool-runs; original projects are unchanged."}
    plan["runtime_data"] = _data_manifest(root, ("gamedata",))
    plan["preview_sha256"] = sha256_bytes(json.dumps(plan, sort_keys=True).encode())
    return plan


def run_tool(workspace: Path, tool: str, request: dict[str, Any], expected_preview_sha256: str) -> dict[str, Any]:
    """Run only a fixed adapter against a fresh snapshot and retain a diagnostic receipt."""
    plan = preview_tool(workspace, tool, request)
    if not plan["runnable"]:
        raise KosmoError("manual_tool", plan["instructions"])
    if plan["preview_sha256"] != expected_preview_sha256:
        raise KosmoError("sha_mismatch", "Tool configuration or inputs changed; preview again.")
    entry = _entry(workspace, tool)
    installation, executable = _installation(entry)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(5)
    run_root = contained(workspace, f"tool-runs/{run_id}")
    run_root.mkdir(parents=True, exist_ok=False)
    cwd = run_root / "runtime"
    cwd.mkdir()
    for record in plan["runtime_data"]:
        source = contained(installation, record["path"])
        raw = source.read_bytes()
        if sha256_bytes(raw) != record["sha256"]:
            raise KosmoError("sha_mismatch", "Tool data changed during snapshot; preview again.")
        target = contained(cwd, record["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    if tool == "domerger":
        for input_project in plan["inputs"]:
            project = open_project(workspace, input_project["project"])
            for record in input_project["files"]:
                source = contained(project.mod_dir, record["path"])
                raw = source.read_bytes()
                if sha256_bytes(raw) != record["sha256"]:
                    raise KosmoError("sha_mismatch", "Input changed while copying; preview again.")
                dest = contained(run_root, f"inputs/{project.slug}/{record['path']}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
        gamedata = contained(installation, "gamedata")
        if not gamedata.is_dir():
            raise KosmoError("tool_data_missing", "Domerger installation needs its gamedata directory.")
        args = [str(executable), "--mods-path", str(run_root / "inputs"), "--target-path", str(run_root / "output")]
    receipt = {**plan, "run_id": run_id, "argv": args, "status": "running", "exit_code": None,
               "output_directory": f"tool-runs/{run_id}", "stdout": "stdout.txt", "stderr": "stderr.txt"}
    atomic_write_bytes(run_root / "receipt.json", (json.dumps(receipt, indent=2) + "\n").encode())
    with (run_root / "stdout.txt").open("wb") as stdout, (run_root / "stderr.txt").open("wb") as stderr:
        try:
            process = subprocess.Popen(args, cwd=cwd, stdout=stdout, stderr=stderr, shell=False,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                       start_new_session=os.name != "nt")
        except OSError as exc:
            receipt["status"] = "failed"
            receipt["launch_error"] = str(exc)
            atomic_write_bytes(run_root / "receipt.json", (json.dumps(receipt, indent=2) + "\n").encode())
            raise KosmoError("tool_launch_failed", "External tool could not start; diagnostic receipt was retained.") from exc
        try:
            receipt["exit_code"] = process.wait(timeout=300)
            receipt["status"] = "completed" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            receipt["status"] = "timed_out"
    receipt["diagnostics"] = {name: (run_root / f"{name}.txt").read_bytes()[-32000:].decode("utf-8", errors="replace")
                              for name in ("stdout", "stderr")}
    outputs = []
    output_root = run_root / "output"
    if output_root.exists():
        for path in sorted(output_root.rglob("*")):
            safe = contained(run_root, path)
            if safe.is_file():
                outputs.append({"path": safe.relative_to(run_root).as_posix(), "bytes": safe.stat().st_size,
                                "sha256": sha256_bytes(safe.read_bytes())})
    receipt["outputs"] = outputs
    receipt["review_warnings"] = []
    for record in outputs:
        if record["path"].lower().endswith(".dm"):
            text, _ = decode_dm(contained(run_root, record["path"]).read_bytes())
            parsed = parse(text)
            for block in parsed.blocks:
                if (block.context == "nation" and block.opener.args
                        and block.opener.args[0].kind == "int" and block.opener.args[0].value < 150
                        and any(s.command == "clearnation" for s in block.statements)):
                    receipt["review_warnings"].append({"file": record["path"], "line": block.opener.line,
                        "message": "Output clears a nation below the supported new-nation range (150+); inspect before adopting."})
    if receipt["status"] == "completed" and not any(f["path"].endswith(".dm") for f in outputs):
        receipt["status"] = "no_mod_output"
    atomic_write_bytes(run_root / "receipt.json", (json.dumps(receipt, indent=2) + "\n").encode())
    return receipt


def tool_receipt(workspace: Path, run_id: str) -> dict[str, Any]:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise KosmoError("bad_tool_run", "Invalid run id.")
    path = contained(workspace, f"tool-runs/{run_id}/receipt.json")
    if not path.is_file():
        raise KosmoError("tool_run_missing", "Tool run receipt is missing.")
    try:
        result = json.loads(path.read_text("utf-8"))
    except (ValueError, OSError) as exc:
        raise KosmoError("tool_run_invalid", "Tool run receipt cannot be read.") from exc
    if not isinstance(result, dict) or result.get("run_id") != run_id:
        raise KosmoError("tool_run_invalid", "Tool run receipt identity differs.")
    return result


def list_tool_runs(workspace: Path) -> dict[str, Any]:
    root = contained(workspace, "tool-runs")
    runs = []
    if root.is_dir():
        for path in sorted(root.iterdir(), reverse=True):
            if RUN_ID.fullmatch(path.name):
                try:
                    receipt = tool_receipt(workspace, path.name)
                except KosmoError as exc:
                    if exc.code != "tool_run_missing":
                        raise
                    runs.append({"run_id": path.name, "status": "incomplete", "tool": None})
                    continue
                runs.append({key: receipt.get(key) for key in
                             ("run_id", "tool", "status", "exit_code", "version", "options", "review_warnings")})
                if len(runs) >= 100:
                    break
    return {"runs": runs}


def tool_archive(workspace: Path, run_id: str) -> bytes:
    """Download only hashed output files, retaining the external mod directory layout."""
    receipt = tool_receipt(workspace, run_id)
    root = contained(workspace, f"tool-runs/{run_id}")
    files = receipt.get("outputs", [])
    if not files or sum(record["bytes"] for record in files) > 256 * 1024 * 1024:
        raise KosmoError("tool_output_unavailable", "No output files or output exceeds the 256 MB download limit.")
    prefix = "output/" if receipt["tool"] == "domerger" else "runtime/mods/"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for record in files:
            relative = record["path"]
            if not relative.startswith(prefix):
                raise KosmoError("tool_run_invalid", "Output manifest contains an unexpected path.")
            raw = contained(root, relative).read_bytes()
            if sha256_bytes(raw) != record["sha256"]:
                raise KosmoError("sha_mismatch", "Tool output changed since the run; download refused.")
            archive.writestr(relative[len(prefix):], raw)
        archive.writestr("kosmokrator-tool-receipt.json", json.dumps({key: receipt.get(key) for key in
                         ("tool", "run_id", "version", "options", "executable_sha256", "review_warnings")}, indent=2))
    return buffer.getvalue()
