"""🎚️ Save project views without changing card order."""
import copy

FILTER_KEYS = ('query', 'type', 'priority', 'label', 'due')


def clean_filters(value):
    return {key: item for key, item in value.items() if key in FILTER_KEYS and isinstance(item, str)} if isinstance(value, dict) else {}


def clean_view(value):
    if not isinstance(value, dict) or not isinstance(value.get('name'), str) or not value['name'].strip():
        return None
    columns = {}
    if isinstance(value.get('columns'), dict):
        for identifier, state in value['columns'].items():
            if isinstance(identifier, str) and isinstance(state, dict):
                width = state.get('width')
                columns[identifier] = {'width': max(220, min(900, width)) if isinstance(width, int) and not isinstance(width, bool) else None,
                    'sort_key': state.get('sort_key') if state.get('sort_key') in ('type', 'priority') else None,
                    'descending': state.get('descending') is True,
                    'type_filter': state.get('type_filter') if isinstance(state.get('type_filter'), str) else None}
    sort = value.get('list_sort')
    if not isinstance(sort, list) or len(sort) != 2 or not isinstance(sort[0], int) or isinstance(sort[0], bool) or not 0 <= sort[0] < 7 or not isinstance(sort[1], bool):
        sort = [0, False]
    return {'name': value['name'].strip(), 'mode': 'list' if value.get('mode') == 'list' else 'board',
            'filters': clean_filters(value.get('filters')), 'columns': columns, 'list_sort': list(sort)}


def capture_view(project, widgets, name):
    return {'name': name.strip(), 'mode': project.view_mode, 'filters': dict(project.view_filters),
            'list_sort': list(project.list_sort),
            'columns': {c.id: {'width': c.width, 'sort_key': c.sort_key, 'descending': c.sort_descending,
                        'type_filter': getattr(widgets.get(c.id), '_type_filter', None)} for c in project.columns}}


def apply_view(project, value):
    state = clean_view(value)
    if state is None:
        raise ValueError('That saved view is not valid.')
    project.view_mode = state['mode']
    project.view_filters = dict(state['filters'])
    project.list_sort = list(state['list_sort'])
    for column in project.columns:
        if column.id in state['columns']:
            saved = state['columns'][column.id]
            column.width, column.sort_key, column.sort_descending = saved['width'], saved['sort_key'], saved['descending']
    return state


def remap_view_columns(project, mapping):
    for view in project.saved_views:
        view['columns'] = {mapping.get(key, key): copy.deepcopy(value) for key, value in view.get('columns', {}).items()}
