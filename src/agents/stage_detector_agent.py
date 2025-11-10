"""
Агент для определения стадии диалога
"""
import json
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

**СПИСОК СТАДИЙ:**

- greeting: Клиент только начинает диалог, здоровается или пишет впервые за долгое время.

- information_gathering: Клиент задает общие вопросы об услугах, ценах, мастерах, но еще не выразил явного желания записаться.

- booking: клиент хочет записаться на услугу

- booking_to_master: клиент явно попросил записать его к конкретному мастеру. (если в предыдущих сообщениях ты выбирал эту стадию, то выбирай ее на всем процессе записи)

- find_window: НЕ ИСПОЛЬЗУЙ ЭТУ СТАДИЮ ЕСЛИ КЛИЕНТ НЕ ПРОСИЛ НАЙТИ ОКНО, ОТКРОЙ booking_second тебе нужно найти в какой день есть свободное окно у конкретного мастера, либо у любого мастера на конкретную услугу

- cancellation_request: Клиент просит отменить существующую запись.

- reschedule: Клиент просит перенести существующую запись на другую дату или время.

- view_my_booking: Клиент хочет посмотреть свои предстоящие записи ("на когда я записан?", "какие у меня записи?").

- call_manager: Получи инструкцию (запроси инструкцию для стадии диалога call_manager) как передать диалог менеджеру в трёх случаях. 1.Когда ты не знаешь ответа на вопрос клиента. 2.Когда ты чувствуешь что клиент чем то недоволен, начинается конфликт. 3. Когда ты получил какую то техническую ошибку при использовании инструментов.

- fallback: Клиент задал вопрос не по теме салона (о погоде, политике и т.д.).

Верни ТОЛЬКО одно слово - название стадии. Не используй инструменты, у тебя достаточно информации для определения стадии.
"""
        
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
        # Убираем лишние пробелы и переносы строк
        response = response.strip().lower()
        
        # Список всех возможных стадий, отсортированный по длине (от длинных к коротким)
        # Это важно, чтобы "booking_to_master" проверялся раньше "booking"
        valid_stages = sorted([stage.value for stage in DialogueStage], key=len, reverse=True)
        
        # Сначала проверяем точное совпадение
        if response in valid_stages:
            return StageDetection(stage=response)
        
        # Если точного совпадения нет, ищем стадию в ответе
        # Проверяем от длинных к коротким, чтобы избежать проблем с подстроками
        for stage in valid_stages:
            if stage in response:
                return StageDetection(stage=stage)
        
        # Если не нашли, пытаемся найти в JSON (на случай если агент всё же вернул JSON)
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            try:
                data = json.loads(json_str)
                stage = data.get('stage', '').lower()
                if stage in valid_stages:
                    return StageDetection(stage=stage)
            except json.JSONDecodeError:
                pass
        
        # Fallback: если не удалось определить стадию, возвращаем fallback
        logger.warning(f"Не удалось определить стадию из ответа: {response}")
        return StageDetection(stage=DialogueStage.FALLBACK.value)
