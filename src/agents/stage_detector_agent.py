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


class StageDetection(BaseModel):
    """Структура для определения стадии"""
    stage: str = Field(
        description="Стадия диалога из DialogueStage enum"
    )


class StageDetectorAgent(BaseAgent):
    """Агент для определения стадии диалога"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """Прочитай последнее сообщение клиента и ознакомься с историей переписки. Определи, какая стадия диалога подходит больше всего.
Прочитай последнее сообщение клиента и ознакомься с историей переписки. Определи, какая стадия диалога подходит больше всего.

**СПИСОК СТАДИЙ:**

- greeting: Клиент только начинает диалог, здоровается или пишет впервые за долгое время.

- information_gathering: Клиент задает общие вопросы об услугах, ценах, мастерах, но еще не выразил явного желания записаться.

- booking: клиент хочет записаться на услугу

- booking_to_master: клиент явно попросил записать его к конкретному мастеру и написал его имя. (если в предыдущих сообщениях ты выбирал эту стадию, то выбирай ее на всем процессе записи) (Если клиент не писал имя мастера, то выбирай стадию booking)

- find_window: НЕ ИСПОЛЬЗУЙ ЭТУ СТАДИЮ ЕСЛИ КЛИЕНТ НЕ ПРОСИЛ НАЙТИ ОКНО, ОТКРОЙ booking_second тебе нужно найти в какой день есть свободное окно у конкретного мастера, либо у любого мастера на конкретную услугу

- cancellation_request: Клиент просит отменить существующую запись.

- reschedule: Клиент просит перенести существующую запись на другую дату или время.

- view_my_booking: Клиент хочет посмотреть свои предстоящие записи ("на когда я записан?", "какие у меня записи?").

- call_manager: Получи инструкцию (запроси инструкцию для стадии диалога call_manager) как передать диалог менеджеру в трёх случаях. 1.Когда ты не знаешь ответа на вопрос клиента. 2.Когда ты чувствуешь что клиент чем то недоволен, начинается конфликт. 3. Когда ты получил какую то техническую ошибку при использовании инструментов.

- fallback: Клиент задал вопрос не по теме салона (о погоде, политике и т.д.).

Верни ТОЛЬКО одно слово - название стадии. Не используй инструменты, у тебя достаточно информации для определения стадии.
Верни ТОЛЬКО одно слово - название стадии. Не используй инструменты, у тебя достаточно информации для определения стадии."""
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=None,
            agent_name="Определитель стадий диалога"
        )
    
    def detect_stage(self, message: str, thread: Thread) -> StageDetection:
        """Определение стадии диалога"""
        try:
            logger.debug(f"Начало определения стадии для сообщения: {message[:100]}")
            thread_id = thread.id if thread and hasattr(thread, "id") else "N/A"
            logger.debug(f"Thread ID: {thread_id}")
            
            # Вызываем базовый метод агента
            response = self(message, thread)
            
            logger.debug(f"Получен ответ от агента определения стадии: {response[:200] if response else 'None/Empty'}")
            
            # Парсим ответ
            detection = self._parse_response(response)
            
            logger.debug(f"Распознана стадия: {detection.stage}")
            
            # Валидируем стадию
            if detection.stage not in [stage.value for stage in DialogueStage]:
                logger.warning(f"Неизвестная стадия: {detection.stage}, устанавливаю fallback")
                logger.warning(f"Доступные стадии: {[stage.value for stage in DialogueStage]}")
                detection.stage = DialogueStage.FALLBACK.value
            
            return detection
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Ошибка при определении стадии: {e}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            logger.error(f"Сообщение: {message[:200]}")
            logger.error(f"Thread ID: {thread.id if thread and hasattr(thread, 'id') else 'N/A'}")
            logger.error(f"Traceback:\n{error_traceback}")
            return StageDetection(stage=DialogueStage.FALLBACK.value)
    
    def _parse_response(self, response: str) -> StageDetection:
        """Парсинг ответа агента в StageDetection"""
        if not response:
            logger.warning("Пустой ответ от агента определения стадии")
            return StageDetection(stage=DialogueStage.FALLBACK.value)
        
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
        return StageDetection(stage=DialogueStage.FALLBACK.value)
