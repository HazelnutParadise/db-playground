import json
import logging
import os
import re
import threading

import httpx

logger = logging.getLogger(__name__)
_slots = threading.BoundedSemaphore(2)
_TERMS = ('資料', '索引', '查詢', '欄位', '表格', '資料表', '主鍵', '外鍵', '鍵值', '交易', '視圖', '資料列', '記錄', '正規化', '資料庫', 'SQL', '表', '鍵', '索引', '資料集')


def generate_name() -> str | None:
    if not _slots.acquire(blocking=False):
        return None
    try:
        base = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434').rstrip('/')
        response = httpx.post(base + '/api/generate', json={
            'model': 'gemma4:e2b', 'stream': False, 'format': 'json',
            'prompt': '請發想一個可愛有創意的繁體中文資料庫主題匿名暱稱，包含一個資料庫詞彙，例如索引、查詢或欄位，再結合動物或其他詞語。長度 3 到 12 字，不要數字或標點。只輸出 JSON，例如 {"name":"索引海獺"}。',
            'options': {'temperature': 1.0},
        }, timeout=15.0)
        response.raise_for_status()
        name = json.loads(response.json()['response'])['name'].strip()
        if not isinstance(name, str) or not re.fullmatch(r'[\u3400-\u9fffA-Za-z]{3,12}', name):
            return None
        if not any(term.lower() in name.lower() for term in _TERMS):
            return None
        return name
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        logger.warning('Anonymous name generation unavailable')
        return None
    finally:
        _slots.release()
