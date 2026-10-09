"""SHA-guarded configuration of explicit mod activation order."""
import contextlib
import json
from dataclasses import replace
from .author import _sha, _preview_flag
from .content import _diff
from .errors import KosmoError
from .project import open_project, dependency_texts, project_lock, reload_meta, read_dm, sha256_bytes, write_dm_locked


def _compatibility(workspace, project, deps):
    """Review the candidate order without changing metadata or claiming catalog/game verification."""
    from .resolution import relationships
    candidate = replace(project, meta={**project.meta, 'dependencies': deps})
    _, report = relationships(workspace, candidate, read_dm(project.dm_path)[1], None)
    report['catalog_available'] = False
    report['limitations'].append('Dependency preview has no catalog: unresolved vanilla references need the catalog-backed project view before deciding they are missing.')
    return report


def dependency_state(workspace, slug):
    project = open_project(workspace, slug)
    options = []
    for root in sorted(workspace.iterdir()):
        if root.name == slug or not root.is_dir() or root.is_symlink():
            continue
        try:
            other = open_project(workspace, root.name)
            options.append({'path': other.dm_path.relative_to(workspace).as_posix(), 'name': other.meta.get('name', root.name)})
        except KosmoError:
            continue
    return {'sha256': sha256_bytes(project.meta_path.read_bytes()),
            'dependencies': project.meta.get('dependencies', []), 'options': options,
            'declared_order': [*project.meta.get('dependencies', []), 'project'],
            'note': 'Kosmokrator models listed dependencies in this order, followed by this project. Match actual game activation separately; metadata does not enable mods in Dominions. Files must be inside this workspace.'}


def save_dependencies(workspace, slug, body):
    if not isinstance(body, dict) or set(body) - {'expected_sha256', 'preview', 'dependencies'}:
        raise KosmoError('bad_request', 'Use expected_sha256, preview and dependencies.')
    sha, preview = _sha(body), _preview_flag(body)
    deps = body.get('dependencies')
    if not isinstance(deps, list) or len(deps) > 32 or any(not isinstance(x, str) for x in deps) or len(set(deps)) != len(deps):
        raise KosmoError('bad_dependency', 'Choose at most 32 unique workspace .dm paths.')
    project = open_project(workspace, slug)
    deps = [label for label, _ in dependency_texts(workspace, deps)]
    if len(set(deps)) != len(deps):
        raise KosmoError('bad_dependency', 'Two paths identify the same dependency file.')
    if project.dm_path.relative_to(workspace).as_posix() in deps:
        raise KosmoError('bad_dependency', 'A project cannot depend on itself.')
    with project_lock(project) if not preview else contextlib.nullcontext():
        reload_meta(project)
        data = project.meta_path.read_bytes()
        if sha256_bytes(data) != sha:
            raise KosmoError('sha_mismatch', 'Project settings changed; reload and keep your draft.')
        changed = project.meta.get('dependencies', []) != deps
        project.meta['dependencies'] = deps
        new = (json.dumps(project.meta, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        result = {'before_sha256': sha, 'diff': _diff(data.decode('utf-8'), new.decode('utf-8'), 'kosmokrator.json'),
                  'changes': [{'dependencies': deps}] if changed else [], 'warnings': [], 'written': False,
                  'declared_order': [*deps, 'project'], 'compatibility': _compatibility(workspace, project, deps)}
        if preview or not changed:
            return result
        result['backup'] = write_dm_locked(project, project.meta_path, data, new)
        result.update(written=True, after_sha256=sha256_bytes(new))
        return result
