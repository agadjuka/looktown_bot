"""
Состояние для графа бронирования (Responses API)
"""
from typing import TypedDict, Optional, List, Dict, Any


class BookingState(TypedDict):
    """Состояние графа бронирования"""
    message: str                                    # Исходное сообщение пользователя
    conversation_history: Optional[List[Dict[str, Any]]]  # История диалога (вместо thread)
    chat_id: Optional[str]                         # ID чата в Telegram
    stage: Optional[str]                           # Определённая стадия диалога
    extracted_info: Optional[dict]                 # Извлечённая информация
    answer: str                                    # Финальный ответ пользователю
    manager_alert: Optional[str]                   # Сообщение для менеджера (если нужно)
    agent_name: Optional[str]                      # Имя агента, который дал ответ
    used_tools: Optional[list]                    # Список использованных инструментов
