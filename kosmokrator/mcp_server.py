"""Optional MCP stdio server exposing the same core operations as the CLI.

Requires the 'mcp' extra (official MCP Python SDK v1, FastMCP). Nothing in this module
writes to stdout: stdout carries the MCP protocol; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from . import DEFAULT_TARGET_GAME_VERSION
from .core import Kosmokrator, envelope

INSTRUCTIONS = """Kosmokrator: static tooling for Dominions 6 mod (.dm) projects inside one explicit workspace.
Workflow:
1. Research before writing: lookup_command for manual-indexed syntax/context/ranges,
   search_game_data for vanilla ids/names (local third-party catalog; may differ from the installed game).
2. Reserve numbers with allocate_ids before adding #newmonster/#newsite/#selectnation blocks.
3. Use author_state and author_save for structured preview/save edits. For exact source patches, use
   inspect_mod then apply_mod_patch with its sha256. Preserve unrelated source and unknown commands.
4. validate_mod after every change; fix errors, review warnings, and treat 'unverified' as needing human or
   in-game confirmation. author_state kind 'health' gives the combined prioritized findings for one revision.
   Before larger work, author_save kind 'revisions' {action: checkpoint} lets the user compare or undo it later.
   export_mod refuses sources with errors and never overwrites.
Be explicit with users: these checks are static. They do not prove the mod loads, plays or balances in game;
say so, and recommend an in-game test. Do not claim parity with the game or ownership of catalog data."""


def build_server(k: Kosmokrator):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    mcp = FastMCP("kosmokrator", instructions=INSTRUCTIONS, log_level="WARNING")  # SDK logs go to stderr
    ro = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    rw = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    @mcp.tool(annotations=ro)
    def project_view(project: str) -> dict[str, Any]:
        """Resolved unit sheets, used-by references, identities and dependency activation/conflict report."""
        return envelope(k.project_view, project)

    @mcp.tool(annotations=rw)
    def create_project(slug: str, name: str | None = None, description: str | None = None) -> dict[str, Any]:
        """Create <workspace>/<slug> with mod/<slug>/<slug>.dm as the authoritative source. Refuses to overwrite."""
        return envelope(k.create_project, slug, name, description)

    @mcp.tool(annotations=ro)
    def inspect_mod(project: str, file: str | None = None) -> dict[str, Any]:
        """Parse a project's .dm without modifying it: sha256, blocks, commands, definitions, unverified commands."""
        return envelope(k.inspect_mod, project, file)

    @mcp.tool(annotations=rw)
    def apply_mod_patch(project: str, expected_sha256: str, old: str | None = None, new: str | None = None,
                        insert_line: int | None = None, text: str | None = None,
                        file: str | None = None) -> dict[str, Any]:
        """Guarded edit: replace `old` (must occur exactly once) with `new`, OR insert `text` before 1-based
        `insert_line` (last line + 1 appends). Requires the current file sha256; backs up the previous bytes and
        returns before/after hashes and a unified diff. Untouched bytes are preserved."""
        return envelope(k.apply_mod_patch, project, expected_sha256, old=old, new=new,
                        insert_line=insert_line, text=text, file=file)

    @mcp.tool(annotations=ro)
    def lookup_command(command: str | None = None, context: str | None = None) -> dict[str, Any]:
        """Manual-indexed command reference with reviewed schemas, ranges and source citations.
        Omit `command` to list commands; optionally filter by definition context or top."""
        return envelope(k.lookup_command, command, context)

    @mcp.tool(annotations=rw)
    def allocate_ids(project: str, kind: str, count: int = 1, labels: list[str] | None = None,
                     dependencies: list[str] | None = None) -> dict[str, Any]:
        """Reserve free ids (monster, site, nation, weapon, armor) in the documented modding range, avoiding the
        project, explicit dependency .dm files (workspace paths), the catalog and earlier reservations."""
        return envelope(k.allocate_ids, project, kind, count, labels, dependencies)

    @mcp.tool(annotations=ro)
    def search_game_data(query: str, category: str = "all", limit: int = 20,
                         project: str | None = None) -> dict[str, Any]:
        """Search the local dom6inspector catalog by id or name. Categories: all, units, nations, weapons, armors,
        sites, spells, items. Results are capped (max 50) and include catalog source/revision metadata.
        With project, search that project's reference snapshot when it has one."""
        return envelope(k.search_game_data, query, category, limit, project)

    @mcp.tool(annotations=ro)
    def validate_mod(project: str, dependencies: list[str] | None = None) -> dict[str, Any]:
        """Static validation with file/line errors, warnings and unverified items. Not a load/balance guarantee."""
        return envelope(k.validate_mod, project, dependencies)

    @mcp.tool(annotations=rw)
    def export_mod(project: str, dest: str | None = None, format: str = "zip",
                   dependencies: list[str] | None = None) -> dict[str, Any]:
        """Export an error-free project as <slug>/<slug>.dm plus referenced assets to a NEW zip or folder inside
        the workspace, with a sha256 manifest beside it. Never overwrites."""
        return envelope(k.export_mod, project, dest, format, dependencies)

    @mcp.tool(annotations=ro)
    def author_state(project: str, kind: str) -> dict[str, Any]:
        """State for commands:<context>, dependencies, maps, maps:<id>, map-builds, content or playtests.
        Read-only reports: inheritance, compatibility and balance[:comma-separated nation IDs].
        health returns one prioritized, deduplicated finding list (error, warning, unverified, info) with stable ids,
        locations, evidence and next actions for a captured revision, plus recruitment classes, scope and caveats.
        reference-snapshot reports the project's local reference snapshot (state, coverage, missing data).
        revisions lists local checkpoints, the review baseline and the current content revision;
        revisions:<checkpoint id> or revisions:baseline compares the current files (raw .dm diff, authored
        definition changes, assets, map bundles, metadata) with that checkpoint.
        mercs lists #newmerc companies with #com/#unit/#item names resolved and the structured form options.
        Includes source revision, reviewed schemas, authored values and preserved unknown lines."""
        return envelope(k.author_state, project, kind)

    @mcp.tool(annotations=rw)
    def author_save(project: str, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        """Preview then save a bounded authoring request. Includes commands:<context>, dependencies and maps:<id>
        or maps:import. map-builds supports create/review/accept for agent-produced bundles.
        reference-snapshot (expected_sha256, expected_snapshot, sprites, preview) copies the catalog data and local
        reference art the project needs into its .kosmokrator folder; it is never exported.
        mercs (expected_sha256, preview, company) appends one #newmerc company; commander/troop/items are
        {origin: catalog, id} or {origin: project, key} and are written as their exact names (manual p.63).
        Mod edits need expected_sha256; map edits and jobs need expected_revision; acceptance also binds output.
        revisions takes {action: checkpoint (label, note, actor)} to store every authored file locally;
        {action: review, reviewer_kind: human|agent (required; never claim a human review you did not receive),
        expected_revision or checkpoint}; {action: restore, checkpoint, preview: true} for a plan, then the same
        with preview: false, expected_revision, plan_hash and confirm: true; {action: recover, journal, confirm}.
        Uses project locking, backups and reviewed command forms."""
        return envelope(k.author_save, project, kind, body)

    @mcp.tool(annotations=ro)
    def reference_game_data(category: str, query: str | None = None, id: int | None = None,
                            project: str | None = None) -> dict[str, Any]:
        """Catalog spells/sites/weapons/armors: search by query, or one row by id with labelled raw columns
        (spells also give their effect record and a documented summon monster). Raw vanilla values only.
        With project, read that project's reference snapshot when it has one."""
        return envelope(k.reference, category, query, id, project)

    @mcp.tool(annotations=rw)
    def import_mod(source: str, slug: str, name: str | None = None, preview: bool = True) -> dict[str, Any]:
        """Import an existing .dm (and assets it references from its folder) as a NEW project. Never overwrites
        the source or an existing project. Defaults to preview."""
        return envelope(k.import_dm, source, slug, name, preview)

    @mcp.tool(annotations=rw)
    def import_map(project: str, source: str, preview: bool = True) -> dict[str, Any]:
        """Import an explicit .map with its planes and referenced assets into a project. Defaults to preview;
        never overwrites. Use author_state maps:<id> and author_save maps:<id> for subsequent edits."""
        return envelope(k.import_map, project, source, preview)

    @mcp.tool(annotations=rw)
    def export_map(project: str, map_id: str, expected_revision: str) -> dict[str, Any]:
        """Export a statically checked, saved map bundle into a new separate ZIP. Requires its whole-bundle revision."""
        return envelope(k.export_map, project, map_id, expected_revision)

    @mcp.tool(annotations=ro)
    def external_tools() -> dict[str, Any]:
        """Inspect administrator-configured local tools. No execution or automatic installation."""
        return envelope(k.external_tools)

    @mcp.tool(annotations=ro)
    def preview_external_tool(tool: str, request: dict[str, Any]) -> dict[str, Any]:
        """Fingerprint options, executable/data and copied project inputs before a fixed adapter run."""
        return envelope(k.preview_external_tool, tool, request)

    @mcp.tool(annotations=rw)
    def run_external_tool(tool: str, request: dict[str, Any], expected_preview_sha256: str) -> dict[str, Any]:
        """Execute a trusted local tool with fixed arguments and copied inputs; retain isolated outputs/logs.
        Requires the exact preview SHA. GUI-only tools provide manual handoffs, not unattended runners."""
        return envelope(k.run_external_tool, tool, request, expected_preview_sha256)

    @mcp.tool(annotations=ro)
    def external_tool_runs(run_id: str | None = None) -> dict[str, Any]:
        """List retained tool runs, or inspect one run receipt including diagnostic logs and output hashes."""
        return envelope(k.external_tool_runs, run_id)

    return mcp


def serve(workspace: str | None, catalog: str | None, target_version: str | None) -> int:
    k = Kosmokrator(workspace, catalog, target_version)
    try:
        k.ws  # fail fast on a missing/invalid workspace, before speaking the protocol
    except Exception as exc:  # noqa: BLE001
        print(f"kosmokrator-mcp: {exc}", file=sys.stderr)
        return 2
    try:
        server = build_server(k)
    except ImportError:
        print("kosmokrator-mcp: the 'mcp' package is not installed. Install with: pip install \"kosmokrator[mcp]\"",
              file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kosmokrator-mcp", description="Kosmokrator MCP stdio server")
    ap.add_argument("--workspace", "-w", required=True, help="Explicit workspace root")
    ap.add_argument("--catalog", help="Local dom6inspector checkout (default: $KOSMOKRATOR_CATALOG)")
    ap.add_argument("--target-version", default=DEFAULT_TARGET_GAME_VERSION)
    a = ap.parse_args(argv)
    return serve(a.workspace, a.catalog, a.target_version)


if __name__ == "__main__":
    sys.exit(main())
