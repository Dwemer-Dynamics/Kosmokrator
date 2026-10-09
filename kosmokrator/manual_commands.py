"""Manual-indexed command forms for the lossless advanced editor."""
from .manual_commands_data import ROWS
from .commands import REGISTRY
from .dmparse import OPENERS
from functools import lru_cache
from .docindex import MONSTER_DOCUMENTED, NATION_DOCUMENTED, SITE_DOCUMENTED

CONTEXTS = ('monster', 'nation', 'site', 'spell', 'weapon', 'armor', 'item', 'merc', 'event')


@lru_cache(maxsize=16)
def commands(context):
    """Prefer reviewed schemas and retain the printed signature for every manual entry."""
    out = {}
    for ctx, name, signature, page, summary, args in ROWS:
        if ctx != context or name == 'end' or name.startswith(('clearall',)):
            continue
        if name in OPENERS and OPENERS[name] != ctx:
            continue
        reviewed = REGISTRY.get((ctx, name))
        if ctx == 'spell' and name == 'nogeosrc':
            signature = '<terrain mask>'
            args = [{'name': 'terrain_mask', 'type': 'int', 'optional': False}]
        if reviewed:
            args = [a.to_dict() for a in reviewed.args]
        if args and any(a['type'] == 'ref' for a in args):
            args = None
        normalized = []
        for a in args or []:
            item = dict(a)
            if item['type'] == 'str':
                for word, typ in [('monster_name', 'mon'), ('spell_name', 'spell'), ('weapon_name', 'weapon'),
                                  ('armor_name', 'armor'), ('item_name', 'item'), ('site_name', 'sitename')]:
                    if word in item['name']:
                        item['type'] = typ
            if 'range' in a:
                item['min'], item['max'] = a['range']
            if 'allowed' in a:
                item['choices'] = a['allowed']
            normalized.append(item)
        out[name] = {'command': name, 'label': '#' + name, 'signature': signature,
                     'summary': summary, 'args': normalized, 'editable': args is not None,
                     'schema_status': 'reviewed' if reviewed else 'manual signature',
                     'source': {'document': 'Dominions 6 Event Modding Manual' if ctx == 'event' else 'Dominions 6 Modding Manual',
                                'version': '6.36', 'page': page}}
    for (ctx, name), spec in REGISTRY.items():
        if ctx != context or name in out or name == 'end':
            continue
        entry = spec.to_dict()
        entry.update(command=name, label='#' + name, editable=True, schema_status='reviewed')
        for arg in entry['args']:
            if 'range' in arg:
                arg['min'], arg['max'] = arg['range']
            if 'allowed' in arg:
                arg['choices'] = arg['allowed']
        out[name] = entry
    if context == 'nation':
        for terrain in ('plain', 'forest', 'mountain', 'swamp', 'waste', 'farm', 'cave', 'drip', 'coast', 'sea', 'deep', 'kelp', 'foreign'):
            for suffix in ('rec', 'com', 'fortrec', 'fortcom'):
                if terrain in ('sea', 'deep', 'kelp') and suffix.startswith('fort') or terrain == 'foreign' and not suffix.startswith('fort'):
                    continue
                name = terrain + suffix
                out[name] = {'command': name, 'label': '#' + name, 'summary': 'Terrain-specific recruitment. Command family expanded from the manual.',
                             'args': [{'name': 'monster', 'type': 'mon', 'optional': False}], 'editable': True,
                             'source': {'document': 'Dominions 6 Modding Manual', 'version': '6.36', 'page': 44},
                             'schema_status': 'manual family'}
        for name in NATION_DOCUMENTED:
            if name.startswith('uwdef') and name[2:] in out:
                out[name] = {**out[name[2:]], 'command': name, 'label': '#' + name,
                             'summary': 'Underwater province defence counterpart to #' + name[2:],
                             'source': {'document': 'Dominions 6 Modding Manual', 'version': '6.36', 'page': 46}}
    documented = {'monster': MONSTER_DOCUMENTED, 'nation': NATION_DOCUMENTED, 'site': SITE_DOCUMENTED}.get(context, ())
    for name in documented:
        if name not in out and name != 'end':
            out[name] = {'command': name, 'label': '#' + name, 'args': [], 'editable': False,
                         'summary': 'Documented name; this index has no established argument schema. Preserved as source.',
                         'source': {'document': 'Dominions 6 Modding Manual', 'version': '6.36'}, 'schema_status': 'unverified signature'}
    return out
