"""
Сервис для работы с LangGraph (Responses API)
"""
import os
from typing import Optional


class LangGraphService:
    """Сервис для работы с LangGraph (Responses API)"""
    
    def __init__(self):
        folder_id = os.getenv("YANDEX_FOLDER_ID")
        api_key = os.getenv("YANDEX_API_KEY_SECRET")
        
        if not folder_id or not api_key:
            raise ValueError("Не заданы YANDEX_FOLDER_ID или YANDEX_API_KEY_SECRET")
        
        self.folder_id = folder_id
        self.api_key = api_key
