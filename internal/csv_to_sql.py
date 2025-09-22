import pandas as pd
from typing import Any


def remove_empty_or_nan_rows_or_columns(df: pd.DataFrame) -> pd.DataFrame:
    """ 移除所有單元格為 NaN 或空的列與行 """
    new_df: pd.DataFrame = df.dropna(axis=1, how='all')
    return new_df.dropna(how='all')


def infer_type(value) -> str:
    """推斷值的資料類型為 'int'、'float' 或 'str'"""
    if isinstance(value, float):
        return 'float'
    elif isinstance(value, int) and not isinstance(value, bool):
        return 'int'
    else:
        return 'str'


def find_header_row(df: pd.DataFrame) -> int:
    num_rows: int = df.shape[0]
    header_score: list[int] = [0] * num_rows

    for i in range(num_rows - 1):  # 不檢查最後一行，因為沒有下一行可以比較
        current_row: pd.Series[Any] = df.iloc[i]
        next_row: pd.Series[Any] = df.iloc[i + 1]

        if current_row.isnull().any():
            continue

        # 檢查當前行是否全由唯一值組成
        unique_values: bool = current_row.nunique() == len(current_row)
        if not unique_values:
            continue

        # 檢查當前行和下一行之間的資料類型是否一致
        current_row_types: list[str] = [
            infer_type(value) for value in current_row]
        next_row_types: list[str] = [infer_type(value) for value in next_row]
        type_consistency: bool = current_row_types == next_row_types

        # 如果當前行擁有唯一值且與下一行資料類型一致，則可能是表頭
        if unique_values and type_consistency:
            header_score[i] += 1

    # 選擇得分最高的行作為表頭
    max_score: int = max(header_score)
    if max_score > 0:
        return header_score.index(max_score)
    return 0  # 如果沒有找到明確的表頭，返回 0


def create_sql_from_df(df: pd.DataFrame, table_name: str) -> str:
    """ 從 DataFrame 建立 SQL CREATE 和 INSERT 語句 """
    create_table_statement: str = f'CREATE TABLE `{table_name}` ('
    column_definitions: list[str] = []
    for column in df.columns:
        series: pd.Series[Any] = df[column]
        assert isinstance(series, pd.Series)
        sql_type: str = infer_sql_type(series)
        column_definitions.append(f"`{column}` {sql_type}")
    create_table_statement += ', '.join(column_definitions)
    create_table_statement += ');'

    # 批量插入
    insert_statements: list[str] = []
    for index, row in df.iterrows():
        if row.isna().all():
            continue  # 跳過所有值為 NaN 的行

        values: list[str] = [escape_value(x) for x in row]
        insert_statement: str = f"INSERT INTO `{table_name}` VALUES ({', '.join(values)});"
        insert_statements.append(insert_statement)

    return create_table_statement + '\n' + '\n'.join(insert_statements)


def escape_value(value: Any) -> str:
    """ 正確地轉義 SQL 字串值 """
    if pd.isna(value):
        return 'NULL'
    elif isinstance(value, str):
        value = value.replace('"', '""')
        return f'"{value}"'  # 正確地轉義單引號
    else:
        return str(value)


def infer_sql_type(series: pd.Series) -> str:
    # 檢查整數類型，並根據範圍限制選擇 INT 或 BIGINT
    if pd.api.types.is_integer_dtype(series):
        if series.max() > 2147483647 or series.min() < -2147483648:
            return 'BIGINT'
        return 'INT'
    # 檢查浮點數類型，使用 DECIMAL 提供精度，或作為備選使用 FLOAT
    elif pd.api.types.is_float_dtype(series):
        precision, scale = calculate_float_precision_scale(series)
        if scale > 0:
            return f'DECIMAL({precision}, {scale})'
        else:
            return 'FLOAT'
    # 檢查布林值類型
    elif pd.api.types.is_bool_dtype(series):
        return 'BOOLEAN'
    # 檢查日期時間類型，並使用適當的 SQL 日期/時間類型
    elif pd.api.types.is_datetime64_any_dtype(series):
        return 'DATETIME'
    # 處理字串類型，根據長度限制選擇 VARCHAR 或 TEXT
    elif pd.api.types.is_string_dtype(series):
        max_length = series.dropna().str.len().max()
        if max_length > 255:
            return 'TEXT'
        return f'VARCHAR({int(max_length)})'
    # 對於未處理或混合類型，默認使用 TEXT
    else:
        return 'TEXT'


def calculate_float_precision_scale(series: pd.Series) -> tuple:
    """ 計算 DECIMAL SQL 資料類型的最大精度和小數位數 """
    precision = scale = 0
    for value in series.dropna():
        # 將每個非 NaN 浮點數轉換為具有固定精度的字串
        str_value: str = f'{value:.14f}'.rstrip('0')
        local_precision: int = 0
        local_scale: int = 0
        if '.' in str_value:
            int_part, dec_part = str_value.split('.')
            local_precision = len(int_part) + len(dec_part)
            local_scale = len(dec_part)
        else:
            local_precision = len(str_value)
            local_scale = 0
        # 更新最大精度和小數位數
        precision: int = max(precision, local_precision)
        scale: int = max(scale, local_scale)
    return precision, scale
