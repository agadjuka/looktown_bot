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
        description="Стадия диалога: greeting, booking, cancel_booking, reschedule, salon_info, general, unknown"
    )


class StageDetectorAgent(BaseAgent):
    """Агент для определения стадии диалога"""
    
    # Словарь описаний стадий (можно обновлять через Prompt Manager)
    _stage_descriptions = {
        "greeting": "Приветствие, начало диалога, прощание",
        "booking": "Бронирование, запись на услугу",
        "cancel_booking": "Отмена записи",
        "reschedule": "Перенос записи на другое время",
        "salon_info": "Вопросы о салоне, рассказ о салоне",
        "general": "Общие вопросы о услугах, ценах, мастерах",
        "unknown": "Неопределённая стадия, если не подходит ни одна"
    }
    
    def __init__(self, langgraph_service: LangGraphService):
        # Получаем список стадий из enum
        stages_list = []
        for stage in DialogueStage:
            stages_list.append(f"- {stage.value} - {self._get_stage_description(stage.value)}")
        
        stages_text = "\n".join(stages_list)
        
        instruction = f"""Посмотри последнее сообщение и историю переписки. Определи стадию диалога.

Доступные стадии:
{stages_text}

Верни ТОЛЬКО одно слово - название стадии. Не используй инструменты, у тебя достаточно информации для определения стадии."""
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=None,
            agent_name="Определитель стадий диалога"
        )
    
    @classmethod
    def _get_stage_description(cls, stage_value: str) -> str:
        """Получить описание стадии для промпта"""
        return cls._stage_descriptions.get(stage_value, "")
    
    @classmethod
    def update_stage_description(cls, stage_value: str, description: str):
        """Обновить описание стадии"""
        cls._stage_descriptions[stage_value] = description
    
    def detect_stage(self, message: str, thread: Thread) -> StageDetection:
        """Определение стадии диалога"""
        try:
            # Вызываем базовый метод агента
            response = self(message, thread)
            
            # Парсим ответ
            detection = self._parse_response(response)
            
            # Валидируем стадию
            if detection.stage not in [stage.value for stage in DialogueStage]:
                logger.warning(f"Неизвестная стадия: {detection.stage}, устанавливаю unknown")
                detection.stage = DialogueStage.UNKNOWN.value
            
            return detection
            
        except Exception as e:
            logger.error(f"Ошибка при определении стадии: {e}")
            return StageDetection(stage=DialogueStage.UNKNOWN.value)
    
    def _parse_response(self, response: str) -> StageDetection:
        """Парсинг ответа агента в StageDetection"""
        # Убираем лишние пробелы и переносы строк
        response = response.strip().lower()
        
        # Список всех возможных стадий
        valid_stages = [stage.value for stage in DialogueStage]
        
        # Ищем стадию в ответе
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
        
        # Fallback: если не удалось определить стадию, возвращаем unknown
        logger.warning(f"Не удалось определить стадию из ответа: {response}")
        return StageDetection(stage=DialogueStage.UNKNOWN.value)
