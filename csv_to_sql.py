import pandas as pd

def remove_empty_or_nan_rows_or_columns(df: pd.DataFrame) -> pd.DataFrame:
    """ Remove rows where all cells are NaN or empty. """
    new_df = df.dropna(axis=1, how='all')
    return new_df.dropna(how='all')

def infer_type(value) -> str:
    """尝试识别数据值的类型以匹配 SQL 类型。"""
    try:
        int_value = int(value)
        return 'int'
    except ValueError:
        try:
            float_value = float(value)
            return 'float'
        except ValueError:
            return 'str'

def find_header_row(df: pd.DataFrame) -> int:
    num_rows = df.shape[0]
    header_score = [0] * num_rows

    for i in range(num_rows - 1):  # 不检查最后一行，因为没有下一行可以比较
        current_row = df.iloc[i]
        next_row = df.iloc[i + 1]

        if current_row.isnull().any():
            continue

        # 检查当前行是否全由唯一值组成
        unique_values = current_row.nunique() == len(current_row)
        if not unique_values:
            continue

        # 检查当前行和下一行之间的数据类型是否一致
        current_row_types = [infer_type(value) for value in current_row]
        next_row_types = [infer_type(value) for value in next_row]
        type_consistency = current_row_types == next_row_types

        # 如果当前行拥有唯一值且与下一行数据类型一致，则可能是表头
        if unique_values and type_consistency:
            header_score[i] += 1

    # 选择得分最高的行作为表头
    max_score = max(header_score)
    if max_score > 0:
        return header_score.index(max_score)
    return 0  # 如果没有找到明确的表头，返回 0

def create_sql_from_df(df: pd.DataFrame, table_name: str) -> str:
    """ Create SQL CREATE and INSERT statements from DataFrame """
    create_table_statement = f'CREATE TABLE `{table_name}` ('
    column_definitions = []
    for column in df.columns:
        sql_type = infer_sql_type(df[column])
        column_definitions.append(f"`{column}` {sql_type}")
    create_table_statement += ', '.join(column_definitions)
    create_table_statement += ');'

    # 批量插入
    insert_statements = []
    for index, row in df.iterrows():
        if row.isna().all():
            continue  # Skip rows where all values are NaN

        values = [escape_value(x) for x in row]
        insert_statement = f"INSERT INTO `{table_name}` VALUES ({', '.join(values)});"
        insert_statements.append(insert_statement)

    return create_table_statement + '\n' + '\n'.join(insert_statements)

def escape_value(value) -> str:
    """ Properly escape string values for SQL. """
    if pd.isna(value):
        return 'NULL'
    elif isinstance(value, str):
        value = value.replace('"', '""')
        return f'"{value}"'  # Properly escape single quotes
    else:
        return str(value)

def infer_sql_type(series: pd.Series) -> str:
    # Check for integer type with range constraints for INT and BIGINT
    if pd.api.types.is_integer_dtype(series):
        if series.max() > 2147483647 or series.min() < -2147483648:
            return 'BIGINT'
        return 'INT'
    # Check for float type and use DECIMAL for precision, or FLOAT as a fallback
    elif pd.api.types.is_float_dtype(series):
        precision, scale = calculate_float_precision_scale(series)
        if scale > 0:
            return f'DECIMAL({precision}, {scale})'
        else:
            return 'FLOAT'
    # Check for boolean type
    elif pd.api.types.is_bool_dtype(series):
        return 'BOOLEAN'
    # Check for datetime type and use the appropriate SQL date/time types
    elif pd.api.types.is_datetime64_any_dtype(series):
        return 'DATETIME'
    # Handle string types with length constraints for VARCHAR and TEXT
    elif pd.api.types.is_string_dtype(series):
        max_length = series.dropna().str.len().max()
        if max_length > 255:
            return 'TEXT'
        return f'VARCHAR({int(max_length)})'
    # Fallback to TEXT for unhandled or mixed types
    else:
        return 'TEXT'

def calculate_float_precision_scale(series: pd.Series) -> tuple:
    """ Calculate the maximum precision and scale for DECIMAL SQL data type. """
    precision = scale = 0
    for value in series.dropna():
        # Convert each non-NaN float to a string with a fixed precision
        str_value = f'{value:.14f}'.rstrip('0')
        if '.' in str_value:
            int_part, dec_part = str_value.split('.')
            local_precision = len(int_part) + len(dec_part)
            local_scale = len(dec_part)
        else:
            local_precision = len(str_value)
            local_scale = 0
        # Update maximum precision and scale
        precision = max(precision, local_precision)
        scale = max(scale, local_scale)
    return precision, scale