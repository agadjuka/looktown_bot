"""
Агент для определения стадии диалога
"""
import json
import re
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread
from .base_agent import BaseAgent
from .dialogue_stages import DialogueStage
from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger
from .tools.call_manager_tools import CallManager


class StageDetection(BaseModel):
    """Структура для определения стадии"""
    stage: str = Field(
        description="Стадия диалога из DialogueStage enum"
    )


class StageDetectorAgent(BaseAgent):
    """Агент для определения стадии диалога"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """Прочитай последнее сообщение клиента и ознакомься с историей переписки. Определи, какая стадия диалога подходит больше всего.
ОЧЕНЬ ВНИМАТЕЛЬНО СМОТРИ ИСТОРИЮ СООБЩЕНИЙ. ЧАСТО ТЫ МОЖЕШЬ ПОНЯТЬ КАКАЯ СТАДИЯ ТОЛЬКО ИЗ ПРОШЛЫХ СООБЩЕНИЙ.

**СПИСОК СТАДИЙ:**

- greeting: Клиент только начинает диалог, здоровается или пишет впервые за долгое время.

- information_gathering: Клиент задает общие вопросы об услугах, ценах, мастерах, но еще не выразил явного желания записаться.

- booking: клиент хочет записаться на услугу

- booking_to_master: клиент явно попросил записать его к конкретному мастеру и написал его имя. (если в предыдущих сообщениях ты выбирал эту стадию, то выбирай ее на всем процессе записи) (Если клиент не писал имя мастера, то выбирай стадию booking)

- cancellation_request: Клиент просит отменить существующую запись.

- reschedule: Клиент просит перенести существующую запись на другую дату или время.

- view_my_booking: Клиент хочет посмотреть свои предстоящие записи ("на когда я записан?", "какие у меня записи?").


Верни ТОЛЬКО одно слово - название стадии. Не используй инструменты, у тебя достаточно информации для определения стадии.  Снизу кратко объясни почему выбрал именно эту стадию
ИСКЛЮЧЕНИЕ: используй инструмент CallManager, если клиент явно просит позвать менеджера."""
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=[CallManager],
            agent_name="Определитель стадий диалога"
        )
    
    def detect_stage(self, message: str, thread: Thread) -> StageDetection:
        """Определение стадии диалога"""
        # Не обрабатываем исключения здесь - пробрасываем их дальше на нижний уровень
        logger.debug(f"Начало определения стадии для сообщения: {message[:100]}")
        thread_id = thread.id if thread and hasattr(thread, "id") else "N/A"
        logger.debug(f"Thread ID: {thread_id}")
        
        # Вызываем базовый метод агента - исключения пробрасываются дальше
        response = self(message, thread)
        
        logger.debug(f"Получен ответ от агента определения стадии: {response[:200] if response else 'None/Empty'}")
        
        # Если CallManager был вызван, BaseAgent вернет "[CALL_MANAGER_RESULT]"
        # Это будет обработано в графе через проверку _call_manager_result
        # Здесь мы просто возвращаем валидную стадию, граф сам обработает CallManager
        if response == "[CALL_MANAGER_RESULT]":
            logger.info("CallManager был вызван в StageDetectorAgent")
            # Возвращаем валидную стадию, граф обработает CallManager через _call_manager_result
            return StageDetection(stage=DialogueStage.GREETING.value)
        
        # Парсим ответ
        detection = self._parse_response(response)
        
        logger.debug(f"Распознана стадия: {detection.stage}")
        
        # Валидируем стадию
        if detection.stage not in [stage.value for stage in DialogueStage]:
            logger.warning(f"Неизвестная стадия: {detection.stage}, устанавливаю greeting")
            logger.warning(f"Доступные стадии: {[stage.value for stage in DialogueStage]}")
            detection.stage = DialogueStage.GREETING.value
        
        return detection
    
    def _parse_response(self, response: str) -> StageDetection:
        """Парсинг ответа агента в StageDetection"""
        if not response:
            logger.warning("Пустой ответ от агента определения стадии")
            return StageDetection(stage=DialogueStage.GREETING.value)
        
        # Убираем лишние пробелы и переносы строк, приводим к нижнему регистру
        response_clean = response.strip().lower()
        
        # Получаем все возможные стадии
        valid_stages = [stage.value for stage in DialogueStage]
        
        # ШАГ 1: Проверяем точное совпадение (самый надежный способ)
        if response_clean in valid_stages:
            logger.debug(f"Найдено точное совпадение стадии: {response_clean}")
            return StageDetection(stage=response_clean)
        
        # ШАГ 2: Извлекаем первое слово из ответа (агент должен вернуть только название стадии)
        first_word = response_clean.split()[0] if response_clean.split() else ""
        if first_word in valid_stages:
            logger.debug(f"Найдена стадия в первом слове: {first_word}")
            return StageDetection(stage=first_word)
        
        # ШАГ 3: Ищем стадию как целое слово через регулярные выражения
        # Сортируем от длинных к коротким, чтобы "booking_to_master" проверялся раньше "booking"
        sorted_stages = sorted(valid_stages, key=len, reverse=True)
        for stage in sorted_stages:
            # Ищем стадию как целое слово (с границами слов)
            pattern = r'\b' + re.escape(stage) + r'\b'
            if re.search(pattern, response_clean):
                logger.debug(f"Найдена стадия через regex: {stage}")
                return StageDetection(stage=stage)
        
        # ШАГ 4: Пытаемся найти в JSON (на случай если агент вернул JSON)
        json_start = response_clean.find('{')
        json_end = response_clean.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = response_clean[json_start:json_end]
            try:
                data = json.loads(json_str)
                stage = data.get('stage', '').lower().strip()
                if stage in valid_stages:
                    logger.debug(f"Найдена стадия в JSON: {stage}")
                    return StageDetection(stage=stage)
            except json.JSONDecodeError:
                pass
        
        # ШАГ 5: Последняя попытка - ищем подстроку (но только если ничего не нашли)
        # Сортируем от длинных к коротким
        for stage in sorted_stages:
            if stage in response_clean:
                logger.warning(f"Найдена стадия как подстрока (может быть неточно): {stage} в ответе: {response_clean}")
                return StageDetection(stage=stage)
        
        # Fallback: если не удалось определить стадию
        logger.warning(f"Не удалось определить стадию из ответа: {response_clean}")
        logger.warning(f"Доступные стадии: {valid_stages}")
        return StageDetection(stage=DialogueStage.GREETING.value)
