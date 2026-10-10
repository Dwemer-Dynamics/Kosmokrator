"""The single set of core operations exposed identically by the CLI and the MCP server."""

from __future__ import annotations

from typing import Any, Callable

from . import commands as cmdreg
from . import project as proj
from .catalog import load_catalog, search
from .demo import build_demo
from .errors import KosmoError
from .export import export_mod as _export
from .paths import resolve_workspace
from .validate import validate_project


class Kosmokrator:
    """Holds the explicit workspace root, optional catalog path and target game version."""

    def __init__(self, workspace: str | None, catalog: str | None = None, target_version: str | None = None) -> None:
        self.workspace_arg = workspace
        self.catalog_arg = catalog
        self.target_version = target_version

    @property
    def ws(self):
        return resolve_workspace(self.workspace_arg)

    def _catalog(self, required: bool = False):
        return load_catalog(self.catalog_arg, required=required)

    def _project_catalog(self, project: str, required: bool = False):
        """The project's verified reference snapshot when it has one (never mixed with the live catalog), else the
        live catalog. A snapshot that fails verification is an error, not a silent fallback."""
        from .reference import project_reference
        cat, _manifest, sid = project_reference(self.ws, project)
        return cat if sid is not None else self._catalog(required=required)

    def create_project(self, slug: str, name: str | None = None, description: str | None = None) -> dict[str, Any]:
        return proj.create_project(self.ws, slug, name, description, self.target_version)

    def inspect_mod(self, project: str, file: str | None = None) -> dict[str, Any]:
        return proj.inspect_mod(self.ws, project, file)

    def project_view(self, project: str) -> dict[str, Any]:
        """The same resolved sheets, references and compatibility report as the browser."""
        from .browse import build_project_model
        return build_project_model(self.ws, project, self._project_catalog(project))

    def apply_mod_patch(self, project: str, expected_sha256: str, old: str | None = None, new: str | None = None,
                        insert_line: int | None = None, text: str | None = None,
                        file: str | None = None) -> dict[str, Any]:
        return proj.apply_mod_patch(self.ws, project, expected_sha256, old=old, new=new,
                                    insert_line=insert_line, text=text, file=file)

    def lookup_command(self, command: str | None = None, context: str | None = None) -> dict[str, Any]:
        from .manual_commands import CONTEXTS, commands
        if context is not None and context not in (*cmdreg.CORE_CONTEXTS, *CONTEXTS):
            raise KosmoError("bad_context", f"context must be one of {list(cmdreg.CORE_CONTEXTS)}")
        if not command:
            return {"curated": cmdreg.list_commands(context), "manual_version": cmdreg.MANUAL_VERSION,
                    'manual_commands': list(commands(context).values()) if context in CONTEXTS else
                    [entry for ctx in CONTEXTS for entry in commands(ctx).values()]}
        if context in CONTEXTS and not cmdreg.get(context, command.lstrip('#').lower()):
            entry = commands(context).get(command.lstrip('#').lower())
            if entry:
                return {'context': context, **entry}
        return cmdreg.lookup(command, context)

    def allocate_ids(self, project: str, kind: str, count: int = 1, labels: list[str] | None = None,
                     dependencies: list[str] | None = None) -> dict[str, Any]:
        return proj.allocate_ids(self.ws, project, kind, count, labels, dependencies, self._project_catalog(project))

    def search_game_data(self, query: str, category: str = "all", limit: int = 20,
                         project: str | None = None) -> dict[str, Any]:
        """Search the live catalog, or with project the catalog that project reads (its snapshot, if any)."""
        cat = self._project_catalog(project, required=True) if project else self._catalog(required=True)
        if cat is None:
            raise KosmoError("catalog_missing", "No game-data catalog configured.")
        return search(cat, query, category, limit)

    def validate_mod(self, project: str, dependencies: list[str] | None = None) -> dict[str, Any]:
        return validate_project(self.ws, project, self._project_catalog(project), dependencies)

    def export_mod(self, project: str, dest: str | None = None, format: str = "zip",
                   dependencies: list[str] | None = None) -> dict[str, Any]:
        return _export(self.ws, project, dest, format, self._project_catalog(project), dependencies)

    def build_demo(self, slug: str = "hebdomad", export: str | None = None,
                   export_dest: str | None = None) -> dict[str, Any]:
        return build_demo(self.ws, slug, self._catalog(), export, export_dest)

    # ---- bounded authoring (same functions as the web routes) ----
    def author_state(self, project: str, kind: str) -> dict[str, Any]:
        """Read reviewed authoring state, including commands, dependencies and map bundles."""
        from . import content, playtest
        if kind == 'reference-snapshot':
            from .browse import build_project_model
            from .reference import reference_status
            catalog = self._project_catalog(project)
            return reference_status(self.ws, project, self._catalog(), build_project_model(self.ws, project, catalog))
        if kind in ('inheritance','balance','compatibility'):
            return self.project_view(project)[kind]
        if kind.startswith('balance:'):
            import re
            from .balance import balance_report
            refs = kind.split(':',1)[1]
            if not re.fullmatch(r'\d+(?:,\d+){0,11}',refs):
                raise KosmoError('bad_request','Use balance:<up to 12 comma-separated nation IDs>.')
            return balance_report(self.project_view(project),self._project_catalog(project),[int(x) for x in refs.split(',')])
        if kind == 'map-builds':
            from .map_builds import map_build_state
            return map_build_state(self.ws, project)
        if kind == 'maps':
            from .maps import list_maps
            return list_maps(self.ws, project, self._project_catalog(project))
        if kind.startswith('maps:'):
            from .maps import map_state
            return map_state(self.ws, project, kind.split(':', 1)[1], self._project_catalog(project))
        if kind == 'dependencies':
            from .dependencies import dependency_state
            return dependency_state(self.ws, project)
        if kind.startswith('commands:'):
            from .command_edit import command_state
            return command_state(self.ws, project, kind.split(':', 1)[1], self._project_catalog(project))
        if kind == "playtests":
            return playtest.list_playtests(self.ws, project)
        if kind.startswith("equipment:") and kind[10:].isdigit():
            from .loadout import equipment_state
            return equipment_state(self.ws, project, int(kind[10:]), self._project_catalog(project))
        if kind.startswith("heroes:") and kind[7:].isdigit():
            return content.heroes_state(self.ws, project, int(kind[7:]), self._project_catalog(project))
        return content.content_state(self.ws, project, kind, self._project_catalog(project))

    def author_save(self, project: str, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        """Preview ({"preview": true}) or save one authoring request; body as for the web route."""
        from . import content, playtest
        if kind == 'reference-snapshot':
            from .reference import create_snapshot
            return create_snapshot(self.ws, project, self._catalog(required=True), body)
        if kind == 'map-builds':
            from .map_builds import save_map_build
            return save_map_build(self.ws, project, body, self._project_catalog(project))
        if kind == 'maps:import':
            from .maps import import_map
            return import_map(self.ws, project, body, self._project_catalog(project))
        if kind.startswith('maps:'):
            from .maps import save_map
            return save_map(self.ws, project, kind.split(':', 1)[1], body, self._project_catalog(project))
        if kind == 'dependencies':
            from .dependencies import save_dependencies
            return save_dependencies(self.ws, project, body)
        if kind.startswith('commands:'):
            from .command_edit import save_commands
            return save_commands(self.ws, project, self._project_catalog(project), {**body, 'context': kind.split(':', 1)[1]})
        if kind == "playtests":
            return playtest.add_playtest(self.ws, project, body)
        if kind.startswith("equipment:") and kind[10:].isdigit():
            from .loadout import save_equipment
            return save_equipment(self.ws, project, int(kind[10:]), self._project_catalog(project), body)
        if kind.startswith("heroes:") and kind[7:].isdigit():
            return content.save_heroes(self.ws, project, int(kind[7:]), self._project_catalog(project), body)
        return content.save_content(self.ws, project, kind, self._project_catalog(project), body)

    def reference(self, category: str, query: str | None = None, ident: int | None = None,
                  project: str | None = None) -> dict[str, Any]:
        from . import content
        cat = self._project_catalog(project, required=True) if project else self._catalog(required=True)
        if ident is not None:
            return content.reference_detail(cat, category, ident)
        return content.reference_search(cat, category, query or "")

    def import_dm(self, source: str, slug: str, name: str | None = None, preview: bool = False) -> dict[str, Any]:
        from .importdm import import_from_path
        return import_from_path(self.ws, slug, name, source, preview)

    def import_map(self, project: str, source: str, preview: bool = True) -> dict[str, Any]:
        from .maps import import_map_path
        return import_map_path(self.ws, project, source, preview, self._project_catalog(project))

    def export_map(self, project: str, map_id: str, expected_revision: str) -> dict[str, Any]:
        from .maps import export_map
        return export_map(self.ws, project, map_id, {'expected_revision': expected_revision}, self._project_catalog(project))

    def external_tools(self) -> dict[str, Any]:
        from .integrations import tool_status
        return tool_status(self.ws)

    def preview_external_tool(self, tool: str, request: dict[str, Any]) -> dict[str, Any]:
        from .integrations import preview_tool
        return preview_tool(self.ws, tool, request)

    def run_external_tool(self, tool: str, request: dict[str, Any], expected_preview_sha256: str) -> dict[str, Any]:
        from .integrations import run_tool
        return run_tool(self.ws, tool, request, expected_preview_sha256)

    def external_tool_runs(self, run_id: str | None = None) -> dict[str, Any]:
        from .integrations import list_tool_runs, tool_receipt
        return tool_receipt(self.ws, run_id) if run_id else list_tool_runs(self.ws)


def envelope(fn: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run an operation and wrap the outcome as {ok, result} or {ok: false, error}."""
    try:
        return {"ok": True, "result": fn(*args, **kwargs)}
    except KosmoError as exc:
        return {"ok": False, "error": exc.to_dict()}
    except OSError as exc:
        return {"ok": False, "error": {"code": "os_error", "message": str(exc)}}
