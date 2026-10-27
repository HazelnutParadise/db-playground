import json

MAX_ATTACHMENT_BYTES = 32768


def serialize_attachment(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('type') not in ('code', 'table'):
        raise ValueError('invalid attachment')
    if not isinstance(value.get('label'), str) or not 1 <= len(value['label']) <= 80:
        raise ValueError('invalid label')
    if value['type'] == 'code':
        if set(value) != {'type', 'label', 'content'} or not isinstance(value['content'], str) or not value['content'].strip():
            raise ValueError('invalid code')
    else:
        tables = value.get('tables')
        if set(value) != {'type', 'label', 'tables'} or not isinstance(tables, list) or not 1 <= len(tables) <= 5:
            raise ValueError('invalid tables')
        for table in tables:
            if not isinstance(table, dict) or set(table) != {'columns', 'rows'}:
                raise ValueError('invalid table')
            columns, rows = table['columns'], table['rows']
            if not isinstance(columns, list) or not 1 <= len(columns) <= 30 or not all(isinstance(c, str) and len(c) <= 200 for c in columns):
                raise ValueError('invalid columns')
            if not isinstance(rows, list) or len(rows) > 200:
                raise ValueError('invalid rows')
            for row in rows:
                if not isinstance(row, list) or len(row) != len(columns):
                    raise ValueError('invalid row')
                if any(not isinstance(cell, (str, int, float, bool, type(None))) or isinstance(cell, str) and len(cell) > 4000 for cell in row):
                    raise ValueError('invalid cell')
    result = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    if len(result.encode('utf-8')) > MAX_ATTACHMENT_BYTES:
        raise ValueError('attachment too large')
    return result
