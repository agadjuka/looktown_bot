"""
Агент для определения стадии диалога
"""
import json
from pathlib import Path
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
    
    # Путь к файлу с базовым промптом
    PROMPT_TEMPLATE_FILE = Path(__file__).parent / "stage_detector_prompt_template.txt"
    # Путь к файлу с описаниями стадий
    DESCRIPTIONS_FILE = Path(__file__).parent / "stage_descriptions.json"
    
    @classmethod
    def _load_stage_descriptions(cls) -> dict:
        """Загрузить описания стадий из JSON файла"""
        try:
            if cls.DESCRIPTIONS_FILE.exists():
                with open(cls.DESCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"Файл описаний стадий не найден: {cls.DESCRIPTIONS_FILE}")
                return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки описаний стадий: {e}")
            return {}
    
    @classmethod
    def _load_prompt_template(cls) -> str:
        """Загрузить базовый шаблон промпта из файла"""
        try:
            if cls.PROMPT_TEMPLATE_FILE.exists():
                with open(cls.PROMPT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                logger.warning(f"Файл шаблона промпта не найден: {cls.PROMPT_TEMPLATE_FILE}")
                return cls._get_default_template()
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблона промпта: {e}")
            return cls._get_default_template()
    
    @classmethod
    def _get_default_template(cls) -> str:
        """Получить шаблон по умолчанию"""
        return """Прочитай последнее сообщение клиента и ознакомься с историей переписки. Определи, какая стадия диалога подходит больше всего.

**СПИСОК СТАДИЙ:**
{STAGES_LIST}

Верни ТОЛЬКО одно слово - название стадии. Не используй инструменты, у тебя достаточно информации для определения стадии.
"""
    
    @classmethod
    def _build_stages_list(cls) -> str:
        """Построить список стадий с описаниями"""
        descriptions = cls._load_stage_descriptions()
        stages_list = []
        
        for stage in DialogueStage:
            stage_key = stage.value
            description = descriptions.get(stage_key, f"Стадия {stage_key}")
            stages_list.append(f"- {stage_key}: {description}")
        
        return "\n".join(stages_list)
    
    @classmethod
    def _build_instruction(cls) -> str:
        """Построить финальный промпт из шаблона и списка стадий"""
        template = cls._load_prompt_template()
        stages_list = cls._build_stages_list()
        
        # Заменяем плейсхолдер на список стадий
        instruction = template.replace("{STAGES_LIST}", stages_list)
        
        return instruction
    
    def __init__(self, langgraph_service: LangGraphService):
        # Строим промпт из шаблона и описаний стадий
        instruction = self._build_instruction()
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=None,
            agent_name="Определитель стадий диалога"
        )
    
    @classmethod
    def update_stage_description(cls, stage_key: str, description: str):
        """Обновить описание стадии в JSON файле"""
        try:
            descriptions = cls._load_stage_descriptions()
            descriptions[stage_key] = description
            
            with open(cls.DESCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(descriptions, f, ensure_ascii=False, indent=4)
            
            logger.info(f"Описание стадии '{stage_key}' обновлено")
        except Exception as e:
            logger.error(f"Ошибка обновления описания стадии: {e}")
    
    @classmethod
    def remove_stage_description(cls, stage_key: str):
        """Удалить описание стадии из JSON файла"""
        try:
            descriptions = cls._load_stage_descriptions()
            if stage_key in descriptions:
                del descriptions[stage_key]
                
                with open(cls.DESCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(descriptions, f, ensure_ascii=False, indent=4)
                
                logger.info(f"Описание стадии '{stage_key}' удалено")
        except Exception as e:
            logger.error(f"Ошибка удаления описания стадии: {e}")
    
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
