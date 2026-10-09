"""Line-addressed advanced editing without serializing unrelated source."""
import math
from .author import _sha, _preview_flag, _nl
from .content import _write, _line_span, _apply_spans
from .dmparse import parse, block_id, block_name, OPENERS
from .errors import KosmoError
from .manual_commands import CONTEXTS, commands
from .project import open_project, read_dm, sha256_bytes


def command_state(workspace, slug, context, catalog=None):
    if context not in CONTEXTS:
        raise KosmoError('bad_context', 'Choose a supported command context.')
    project = open_project(workspace, slug)
    data, text, _ = read_dm(project.dm_path)
    schemas = commands(context)
    from .resolution import relationships
    graph, _ = relationships(workspace, project, text, catalog)
    blocks = []
    for b in parse(text).blocks:
        if b.context != context:
            continue
        key = f'{context}:line:{b.opener.line}'
        blocks.append({'key': key, 'name': block_name(b) or f'#{b.opener.command} at line {b.opener.line}',
                       'id': block_id(b), 'opener': '#' + b.opener.command,
                       'opener_args': [a.value for a in b.opener.args],
                       'line': b.opener.line, 'used_by': graph['incoming'].get(key, []),
                       'commands': [{'line': s.line, 'command': s.command, 'args': [a.value for a in s.args],
                                     'raw': s.raw, 'editable': bool(schemas.get(s.command, {}).get('editable'))}
                                    for s in b.statements]})
    return {'context': context, 'sha256': sha256_bytes(data), 'dm': project.rel(project.dm_path),
            'commands': [v for k, v in schemas.items() if k not in OPENERS], 'blocks': blocks,
            'openers': sorted([schemas[k] for k, ctx in OPENERS.items() if ctx == context and k in schemas],
                              key=lambda entry: (not entry['command'].startswith('new'), entry['command'])),
            'note': 'Printed manual signatures are exposed alongside reviewed schemas. Unknown lines remain unchanged.'}


def _render(context, command, values):
    """Validate one documented command and quote strings using the parser's exact syntax."""
    name = str(command).lstrip('#').lower()
    spec = commands(context).get(name)
    if not spec or not spec['editable'] or not isinstance(values, list):
        raise KosmoError('unsupported_command', 'This command has no editable manual schema.')
    args = spec['args']
    if not sum(not a.get('optional') for a in args) <= len(values) <= len(args):
        raise KosmoError('bad_argument', f'#{name}: wrong number of arguments.')
    encoded = []
    for value, arg in zip(values, args):
        typ = arg['type']
        numeric = typ in ('int', 'monid', 'nation', 'pathmask', 'locmask')
        reference = typ in ('mon', 'monneg', 'site', 'weapon', 'armor', 'item', 'spell', 'nationref')
        if numeric and type(value) is not int or typ == 'float' and (type(value) not in (int, float) or not math.isfinite(value)):
            raise KosmoError('bad_argument', f'#{name}: {arg["name"]} needs a number.')
        if reference and type(value) not in (int, str):
            raise KosmoError('bad_argument', f'#{name}: use an ID or quoted name.')
        if typ in ('str', 'img', 'file', 'sitename') and not isinstance(value, str):
            raise KosmoError('bad_argument', f'#{name}: {arg["name"]} needs text.')
        if isinstance(value, str):
            if '"' in value or '\x00' in value or len(value) > 1999:
                raise KosmoError('bad_argument', 'Text must be at most 1999 characters without quotes or NUL.')
            encoded.append('"' + value + '"')
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise KosmoError('bad_argument', 'Unsupported value.')
            if arg.get('min') is not None and value < arg['min'] or arg.get('max') is not None and value > arg['max']:
                raise KosmoError('bad_argument', 'Value is outside the documented range.')
            if arg.get('choices') is not None and value not in arg['choices']:
                raise KosmoError('bad_argument', 'Choose a documented value.')
            encoded.append(str(value))
    return '#' + name + (' ' + ' '.join(encoded) if encoded else '')


def save_commands(workspace, slug, catalog, body):
    if not isinstance(body, dict) or set(body) - {'expected_sha256', 'preview', 'context', 'mode', 'target', 'opener', 'changes'}:
        raise KosmoError('bad_request', 'Invalid advanced-editor request.')
    sha, preview = _sha(body), _preview_flag(body)
    context, mode = body.get('context'), body.get('mode')
    if context not in CONTEXTS or mode not in ('new', 'edit', 'delete'):
        raise KosmoError('bad_request', 'Choose a context and new, edit or delete.')
    operations = body.get('changes', [])
    if not isinstance(operations, list) or len(operations) > 200:
        raise KosmoError('bad_request', 'At most 200 command changes per request.')

    def mutate(text, rel):
        parsed = parse(text)
        nl = _nl(text)
        spans, appends = [], []
        if mode == 'new':
            opener = body.get('opener') or {}
            command = str(opener.get('command', '')).lstrip('#')
            if OPENERS.get(command) != context:
                raise KosmoError('bad_opener', 'Choose a matching block opener.')
            opening = _render(context, command, opener.get('args', []))
            ident = (opener.get('args') or [None])[0]
            if command.startswith('new') and ident is not None and any(b.context == context and block_id(b) == ident and b.new for b in parsed.blocks):
                raise KosmoError('id_conflict', 'A new object already uses that ID in this project.')
            for op in operations:
                if not isinstance(op, dict) or op.get('op') != 'add' or str(op.get('command', '')).lstrip('#') in OPENERS:
                    raise KosmoError('bad_change', 'New blocks accept only ordinary command additions.')
                appends.append(_render(context, op.get('command'), op.get('args', [])))
            candidate = text + (nl if text and not text.endswith(('\n', '\r')) else '') + nl + opening + nl + nl.join(appends) + (nl if appends else '') + '#end' + nl
        else:
            matches = [b for b in parsed.blocks if f'{b.context}:line:{b.opener.line}' == body.get('target') and b.context == context]
            if len(matches) != 1 or matches[0].end is None:
                raise KosmoError('not_editable', 'Choose one closed block from the current source.')
            b = matches[0]
            if mode == 'delete':
                from .resolution import relationships
                project = open_project(workspace, slug)
                graph, _ = relationships(workspace, project, text, catalog)
                used = graph['incoming'].get(body['target'], [])
                if used:
                    raise KosmoError('object_in_use', 'Remove references before deleting this block.', used_by=used)
                candidate = text[:b.opener.start] + text[b.end.end:]
            else:
                touched = set()
                for op in operations:
                    if not isinstance(op, dict) or op.get('op') not in ('add', 'replace', 'remove'):
                        raise KosmoError('bad_change', 'Choose add, replace or remove.')
                    if op['op'] == 'add':
                        if str(op.get('command', '')).lstrip('#') in OPENERS:
                            raise KosmoError('bad_change', 'Block openers cannot be added inside a block.')
                        appends.append(_render(context, op.get('command'), op.get('args', [])))
                        continue
                    hits = [s for s in b.statements if s.line == op.get('line')]
                    if len(hits) != 1 or hits[0].start in touched:
                        raise KosmoError('ambiguous_line', 'Each changed line must identify one statement exactly once.')
                    s = hits[0]
                    touched.add(s.start)
                    if not commands(context).get(s.command, {}).get('editable'):
                        raise KosmoError('unsupported_command', 'Unknown commands are preserved, not rewritten.')
                    if op['op'] == 'remove':
                        start, end = _line_span(text, s)
                        spans.append((start, end, ''))
                    else:
                        if str(op.get('command', '')).lstrip('#') in OPENERS:
                            raise KosmoError('bad_change', 'A statement cannot become a block opener.')
                        spans.append((s.start, s.end, _render(context, op.get('command'), op.get('args', []))))
                if appends:
                    spans.append((b.end.start, b.end.start, nl.join(appends) + nl))
                candidate = _apply_spans(text, spans)
        checked = parse(candidate)
        if len(checked.issues) > len(parsed.issues):
            raise KosmoError('preflight_failed', 'The change introduces parser errors; nothing was written.')
        from collections import Counter
        from .validate import Report, _check_statement, _block_rules
        structural = []
        for snapshot in (parsed, checked):
            report = Report()
            for block in snapshot.blocks:
                _check_statement(block.context, block.opener, report, rel, [], [])
                for statement in block.statements:
                    _check_statement(block.context, statement, report, rel, [], [])
                _block_rules(block, report, rel, catalog)
            structural.append(Counter((e['code'], e['message']) for e in report.of('error')))
        if structural[1] - structural[0]:
            raise KosmoError('preflight_failed', 'The change introduces command or ordering errors; nothing was written.',
                             problems=[message for _, message in structural[1] - structural[0]])
        from .resolution import relationships
        project = open_project(workspace, slug)
        graph, after = relationships(workspace, project, candidate, catalog)
        if mode == 'new':
            _, before = relationships(workspace, project, text, catalog)
            if sum(x['severity'] == 'error' for x in after['overlaps']) > sum(x['severity'] == 'error' for x in before['overlaps']):
                raise KosmoError('id_conflict', 'New definition conflicts with an existing project, dependency or vanilla identity.')
        warnings = ['Static editing cannot verify all effects in the game.']
        if graph['unresolved']:
            warnings.append(f"{len(graph['unresolved'])} reference(s) remain unresolved; inspect the compatibility report before exporting.")
        result = {'changes': operations if mode == 'edit' else [{'op': mode, 'command': context}, *operations],
                  'warnings': warnings, 'used_by': []}
        if mode == 'new' and checked.blocks:
            result['key'] = f'{context}:line:{checked.blocks[-1].opener.line}'
        return candidate, result
    return _write(workspace, slug, sha, preview, mutate)
