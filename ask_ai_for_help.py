from llm import ask_llm

def ask_ai_for_help(data: dict) -> str | None:
    prompt = f"""
    你是一個 SQL 專家，以下 SQL 查詢有語法錯誤，請解釋為何錯誤，並提供修正建議：
    - db_type: {data['db_type']}
    - version: {data['version']}
    - schema_sqls:
        ```sql
        {data['schema_sqls']}
        ```
    - queries:
        ```sql
        {data['queries']}
        ```
    - error_message:
        ```sql
        {data['error_message']}
        ```
    
    務必遵守以下規則：
    1. 使用html格式化輸出，並使用一個 <div> 標籤包裹你的回答。
    2. 不要在 <div> 外面添加任何內容。
    3. 提供修正後的 SQL 查詢片段。
    4. 輸出格式如下：
        ```html
        <div>
            <h5>錯誤分析</h5>
            <p>這裡是錯誤分析的內容...</p>
            <h5>修正建議</h5>
            <p>這裡是修正建議的內容...</p>
            <h5>修正後的 SQL 查詢</h5>
            <pre><code>這裡是修正後的 SQL 查詢片段...</code></pre>
        </div>
        ```
    """
    response = ask_llm(prompt)
    response = response.replace("```html", "").replace("`", "").replace("\n", "")
    return response


if __name__ == "__main__":
    data = {
        "db_type": "mysql",
        "version": "8.0",
        "schema_sqls": "CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(50));",
        "queries": "SELECT * FROM test;",
        "error_message": "Syntax error near 'FROM'"
    }
    print(ask_ai_for_help(data))