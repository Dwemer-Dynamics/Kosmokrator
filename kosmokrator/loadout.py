"""Explicit complete equipment replacement; inherited loadouts are never partly guessed."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .author import _sha, _preview_flag, _end_pos, _nl
from .browse import build_project_model
from .catalog import Catalog
from .content import _write, _line_span, _apply_spans
from .dmparse import parse, block_id, block_name
from .errors import KosmoError
from .project import open_project, read_dm, sha256_bytes


def equipment_state(workspace: Path, slug: str, mid: int, catalog: Catalog | None) -> dict[str, Any]:
    model = build_project_model(workspace, slug, catalog)
    unit = next((u for u in model['monsters'] if u['id'] == mid), None)
    if unit is None:
        raise KosmoError('object_missing', 'Unit is not defined in the project.')
    project = open_project(workspace, slug)
    _, text, _ = read_dm(project.dm_path)
    options = {}
    for group, context, category in [('weapons','weapon','weapons'),('armor','armor','armors')]:
        entries = {int(r['id']): {'id':int(r['id']), 'name':r.get('name'), 'source':'catalog'}
                   for r in catalog.table(category) if str(r.get('id','')).isdigit()} if catalog else {}
        for block in parse(text).blocks:
            if block.context == context and isinstance(block_id(block), int):
                entries[block_id(block)] = {'id':block_id(block), 'name':block_name(block), 'source':'project'}
        options[group] = sorted(entries.values(), key=lambda r: (str(r['name']).lower(), r['id']))
    return {'sha256':model['provenance']['sha256'], 'id':mid, 'name':unit['name'],
            'equipment':unit['resolved']['equipment'], 'options':options,
            'note':'Replacement writes #clearweapons/#cleararmor and the complete selected list. It removes inherited equipment in that group. Unchecked groups are preserved. Final equipped combat stats are not calculated.',
            'max_entries':8, 'limit_source':'Kosmokrator sanity limit, not a game limit'}


def save_equipment(workspace: Path, slug: str, mid: int, catalog: Catalog | None, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) - {'expected_sha256','preview','weapons','armor'}:
        raise KosmoError('bad_request','Body needs expected_sha256, preview and weapons and/or armor lists.')
    sha, preview = _sha(body), _preview_flag(body)
    state = equipment_state(workspace,slug,mid,catalog)
    if state['sha256'] != sha:
        raise KosmoError('sha_mismatch','The unit source changed; reload while keeping the draft.')
    replacements = {}
    for group in ('weapons','armor'):
        if group not in body:
            continue
        values = body[group]
        valid = {row['id'] for row in state['options'][group]}
        if (not isinstance(values,list) or len(values)>8 or
                any(type(value) is not int or value not in valid for value in values)):
            raise KosmoError('bad_value',f'{group}: choose at most eight known equipment IDs.',field=group)
        replacements[group] = values
    if not replacements:
        raise KosmoError('bad_request','Choose an equipment group to replace.')

    def mutate(text: str, rel: str) -> tuple[str, dict[str, Any]]:
        blocks = [b for b in parse(text).blocks if b.context=='monster' and block_id(b)==mid]
        if len(blocks)!=1 or blocks[0].end is None:
            raise KosmoError('not_editable','Equipment needs one uniquely closed monster block.')
        block = blocks[0]
        end = _end_pos(text,block)
        nl = _nl(text)
        reset = max((s.start for s in block.statements if s.command in ('copystats','clear')),default=-1)
        spans, additions, changes = [], [], []
        for group, values in replacements.items():
            command, clear = ('weapon','clearweapons') if group=='weapons' else ('armor','cleararmor')
            for statement in block.statements:
                if statement.start > reset and statement.command in (command,clear):
                    start, stop = _line_span(text,statement)
                    spans.append((start,stop,''))
            additions.extend([f'#{clear}']+[f'#{command} {value}' for value in values])
            changes.append({'field':group,'action':'replace_complete_list','after':values})
        spans.append((end,end,nl.join(additions)+nl))
        candidate = _apply_spans(text,spans)
        before, after = parse(text),parse(candidate)
        if len(after.issues)!=len(before.issues) or candidate[:block.opener.start]!=text[:block.opener.start] or not candidate.endswith(text[block.end.end:]):
            raise KosmoError('preflight_failed','Equipment edit would alter unrelated source or syntax.')
        updated = next(b for b in after.blocks if b.context=='monster' and b.opener.start==block.opener.start)
        for group, wanted in replacements.items():
            command, clear = ('weapon','clearweapons') if group=='weapons' else ('armor','cleararmor')
            marker = max(s.start for s in updated.statements if s.command==clear)
            actual = [s.args[0].value for s in updated.statements if s.command==command and s.start>marker]
            if actual!=wanted:
                raise KosmoError('preflight_failed','Equipment read-back did not match.')
        return candidate,{'id':mid,'changes':changes if candidate != text else [],'warnings':[state['note']]}
    return _write(workspace,slug,sha,preview,mutate)
