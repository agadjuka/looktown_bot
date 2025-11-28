"""
Основной граф состояний для обработки всех стадий диалога (Responses API)
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from .conversation_state import ConversationState
from ..agents.stage_detector_agent import StageDetectorAgent
from ..agents.booking_agent import BookingAgent
from ..agents.booking_to_master_agent import BookingToMasterAgent
from ..agents.cancel_booking_agent import CancelBookingAgent
from ..agents.reschedule_agent import RescheduleAgent
from ..agents.greeting_agent import GreetingAgent
from ..agents.information_gathering_agent import InformationGatheringAgent
from ..agents.view_my_booking_agent import ViewMyBookingAgent

from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger


class MainGraph:
    """Основной граф состояний для обработки всех стадий диалога"""
    
    # Кэш для агентов (чтобы не создавать их заново при каждом создании графа)
    _agents_cache = {}
    
    @classmethod
    def clear_cache(cls):
        """Очистить кэш агентов"""
        cls._agents_cache.clear()
    
    def __init__(self, langgraph_service: LangGraphService):
        self.langgraph_service = langgraph_service
        
        # Используем кэш для агентов
        cache_key = id(langgraph_service)
        
        if cache_key not in MainGraph._agents_cache:
            # Создаём агентов только если их ещё нет в кэше
            MainGraph._agents_cache[cache_key] = {
                'stage_detector': StageDetectorAgent(langgraph_service),
                'greeting': GreetingAgent(langgraph_service),
                'information_gathering': InformationGatheringAgent(langgraph_service),
                'booking': BookingAgent(langgraph_service),
                'booking_to_master': BookingToMasterAgent(langgraph_service),
                'cancellation_request': CancelBookingAgent(langgraph_service),
                'reschedule': RescheduleAgent(langgraph_service),
                'view_my_booking': ViewMyBookingAgent(langgraph_service),
            }
        
        # Используем агентов из кэша
        agents = MainGraph._agents_cache[cache_key]
        self.stage_detector = agents['stage_detector']
        self.greeting_agent = agents['greeting']
        self.information_gathering_agent = agents['information_gathering']
        self.booking_agent = agents['booking']
        self.booking_to_master_agent = agents['booking_to_master']
        self.cancel_agent = agents['cancellation_request']
        self.reschedule_agent = agents['reschedule']
        self.view_my_booking_agent = agents['view_my_booking']
        
        # Создаём граф
        self.graph = self._create_graph()
        self.compiled_graph = self.graph.compile()
    
    def _create_graph(self) -> StateGraph:
        """Создание графа состояний"""
        graph = StateGraph(ConversationState)
        
        # Добавляем узлы
        graph.add_node("detect_stage", self._detect_stage)
        graph.add_node("handle_greeting", self._handle_greeting)
        graph.add_node("handle_information_gathering", self._handle_information_gathering)
        graph.add_node("handle_booking", self._handle_booking)
        graph.add_node("handle_booking_to_master", self._handle_booking_to_master)
        graph.add_node("handle_cancellation_request", self._handle_cancellation_request)
        graph.add_node("handle_reschedule", self._handle_reschedule)
        graph.add_node("handle_view_my_booking", self._handle_view_my_booking)
        
        # Добавляем рёбра
        graph.add_edge(START, "detect_stage")
        graph.add_conditional_edges(
            "detect_stage",
            self._route_after_detect,
            {
                "greeting": "handle_greeting",
                "information_gathering": "handle_information_gathering",
                "booking": "handle_booking",
                "booking_to_master": "handle_booking_to_master",
                "cancellation_request": "handle_cancellation_request",
                "reschedule": "handle_reschedule",
                "view_my_booking": "handle_view_my_booking",
                "end": END
            }
        )
        graph.add_edge("handle_greeting", END)
        graph.add_edge("handle_information_gathering", END)
        graph.add_edge("handle_booking", END)
        graph.add_edge("handle_booking_to_master", END)
        graph.add_edge("handle_cancellation_request", END)
        graph.add_edge("handle_reschedule", END)
        graph.add_edge("handle_view_my_booking", END)
        return graph
    
    def _detect_stage(self, state: ConversationState) -> ConversationState:
        """Узел определения стадии"""
        logger.info("Определение стадии диалога")
        
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        # Определяем стадию
        stage_detection = self.stage_detector.detect_stage(message, previous_response_id, chat_id=chat_id)
        
        # Проверяем, был ли вызван CallManager в StageDetectorAgent
        if hasattr(self.stage_detector, '_call_manager_result') and self.stage_detector._call_manager_result:
            escalation_result = self.stage_detector._call_manager_result
            logger.info(f"CallManager был вызван в StageDetectorAgent, chat_id: {chat_id}")
            
            return {
                "answer": escalation_result.get("user_message"),
                "manager_alert": escalation_result.get("manager_alert"),
                "agent_name": "StageDetectorAgent",
                "used_tools": ["CallManager"],
                "response_id": None  # CallManager не возвращает response_id
            }
        
        return {
            "stage": stage_detection.stage
        }
    
    def _route_after_detect(self, state: ConversationState) -> Literal[
        "greeting", "information_gathering", "booking", "booking_to_master",
        "cancellation_request", "reschedule", "view_my_booking", "end"
    ]:
        """Маршрутизация после определения стадии"""
        # Если CallManager был вызван, завершаем граф
        if state.get("answer") and state.get("manager_alert"):
            logger.info("CallManager был вызван в StageDetectorAgent, завершаем граф")
            return "end"
        
        # Иначе маршрутизируем по стадии
        stage = state.get("stage", "greeting")
        logger.info(f"Маршрутизация на стадию: {stage}")
        
        # Валидация стадии
        valid_stages = [
            "greeting", "information_gathering", "booking", "booking_to_master",
            "cancellation_request", "reschedule", "view_my_booking"
        ]
        
        if stage not in valid_stages:
            logger.warning(f"⚠️ Неизвестная стадия: {stage}, устанавливаю greeting")
            return "greeting"
        
        return stage
    
    def _process_agent_result(self, agent, answer: str, state: ConversationState, agent_name: str) -> ConversationState:
        """
        Обработка результата агента с проверкой на CallManager
        
        Args:
            agent: Экземпляр агента
            answer: Ответ агента
            state: Текущее состояние графа
            agent_name: Имя агента
            
        Returns:
            Обновленное состояние графа
        """
        used_tools = [tool["name"] for tool in agent._last_tool_calls] if hasattr(agent, '_last_tool_calls') and agent._last_tool_calls else []
        
        # Агент всегда возвращает кортеж (answer, response_id)
        # Извлекаем ответ и response_id
        if isinstance(answer, tuple) and len(answer) == 2:
            answer_text, response_id = answer
        else:
            # Если по какой-то причине не кортеж, response_id остается None
            answer_text = answer
            response_id = None
        
        # Проверяем, был ли вызван CallManager через инструмент
        if answer_text == "[CALL_MANAGER_RESULT]" and hasattr(agent, '_call_manager_result') and agent._call_manager_result:
            escalation_result = agent._call_manager_result
            chat_id = state.get("chat_id", "unknown")
            
            logger.info(f"CallManager был вызван через инструмент в агенте {agent_name}, chat_id: {chat_id}")
            
            return {
                "answer": escalation_result.get("user_message"),
                "manager_alert": escalation_result.get("manager_alert"),
                "agent_name": agent_name,
                "used_tools": used_tools,
                "response_id": response_id
            }
        
        # Обычный ответ агента
        answer = answer_text
        
        return {
            "answer": answer,
            "agent_name": agent_name,
            "used_tools": used_tools,
            "response_id": response_id
        }
    
    def _handle_greeting(self, state: ConversationState) -> ConversationState:
        """Обработка приветствия"""
        logger.info("Обработка приветствия")
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        agent_result = self.greeting_agent(message, previous_response_id, chat_id=chat_id)
        return self._process_agent_result(self.greeting_agent, agent_result, state, "GreetingAgent")
    
    def _handle_information_gathering(self, state: ConversationState) -> ConversationState:
        """Обработка сбора информации"""
        logger.info("Обработка сбора информации")
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        agent_result = self.information_gathering_agent(message, previous_response_id, chat_id=chat_id)
        return self._process_agent_result(self.information_gathering_agent, agent_result, state, "InformationGatheringAgent")
    
    def _handle_booking(self, state: ConversationState) -> ConversationState:
        """Обработка бронирования"""
        logger.info("Обработка бронирования")
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        agent_result = self.booking_agent(message, previous_response_id, chat_id=chat_id)
        return self._process_agent_result(self.booking_agent, agent_result, state, "BookingAgent")
    
    def _handle_booking_to_master(self, state: ConversationState) -> ConversationState:
        """Обработка бронирования к мастеру"""
        logger.info("Обработка бронирования к мастеру")
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        agent_result = self.booking_to_master_agent(message, previous_response_id, chat_id=chat_id)
        return self._process_agent_result(self.booking_to_master_agent, agent_result, state, "BookingToMasterAgent")
    
    def _handle_cancellation_request(self, state: ConversationState) -> ConversationState:
        """Обработка отмены"""
        logger.info("Обработка отмены")
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        agent_result = self.cancel_agent(message, previous_response_id, chat_id=chat_id)
        return self._process_agent_result(self.cancel_agent, agent_result, state, "CancelBookingAgent")
    
    def _handle_reschedule(self, state: ConversationState) -> ConversationState:
        """Обработка переноса"""
        logger.info("Обработка переноса")
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        agent_result = self.reschedule_agent(message, previous_response_id, chat_id=chat_id)
        return self._process_agent_result(self.reschedule_agent, agent_result, state, "RescheduleAgent")
    
    def _handle_view_my_booking(self, state: ConversationState) -> ConversationState:
        """Обработка просмотра записей"""
        logger.info("Обработка просмотра записей")
        message = state["message"]
        previous_response_id = state.get("previous_response_id")
        chat_id = state.get("chat_id")
        
        agent_result = self.view_my_booking_agent(message, previous_response_id, chat_id=chat_id)
        return self._process_agent_result(self.view_my_booking_agent, agent_result, state, "ViewMyBookingAgent")

