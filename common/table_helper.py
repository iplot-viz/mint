def get_value(header: dict, data_row, key, type_func=str):
    value = data_row[list(header).index(key)]
    if value is not None and value != '':
        return type_func(value)
    return None