from langchain_ollama import ChatOllama

model = "gemma3:12b"
llm = ChatOllama(model=model, base_url="http://ollama:11434")

def ask_llm(prompt: str) -> (str | None):
    """
    向 LLM 提問並獲取回應
    :param prompt: 提問內容
    :return: LLM 的回應
    """
    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        print(f"呼叫 Ollama 時發生錯誤：{e}")
        return None

