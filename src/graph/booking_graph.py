"""
Граф состояний для обработки бронирований
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from .booking_state import BookingState
from ..agents.stage_detector_agent import StageDetectorAgent
from ..agents.booking_agent import BookingAgent
from ..agents.booking_to_master_agent import BookingToMasterAgent
from ..agents.cancel_booking_agent import CancelBookingAgent
from ..agents.reschedule_agent import RescheduleAgent
from ..agents.greeting_agent import GreetingAgent
from ..agents.information_gathering_agent import InformationGatheringAgent
from ..agents.view_my_booking_agent import ViewMyBookingAgent
from ..agents.tool_tester_agent import ToolTesterAgent



from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger
from ..services.escalation_service import EscalationService


class BookingGraph:
    """Граф состояний для обработки бронирований"""
    
    # Кэш для агентов (чтобы не создавать их заново при каждом создании графа)
    _agents_cache = {}
    
    @classmethod
    def clear_cache(cls):
        """Очистить кэш агентов (полезно после пересоздания Assistant)"""
        cls._agents_cache.clear()
    
    def __init__(self, langgraph_service: LangGraphService):
        self.langgraph_service = langgraph_service
        
        # Используем кэш для агентов
        cache_key = id(langgraph_service)
        
        if cache_key not in BookingGraph._agents_cache:
            # Создаём агентов только если их ещё нет в кэше
            BookingGraph._agents_cache[cache_key] = {
                'stage_detector': StageDetectorAgent(langgraph_service),
                'greeting': GreetingAgent(langgraph_service),
                'information_gathering': InformationGatheringAgent(langgraph_service),
                'booking': BookingAgent(langgraph_service),
                'booking_to_master': BookingToMasterAgent(langgraph_service),
                'cancellation_request': CancelBookingAgent(langgraph_service),
                'reschedule': RescheduleAgent(langgraph_service),
                'view_my_booking': ViewMyBookingAgent(langgraph_service),
                'tool_tester': ToolTesterAgent(langgraph_service),
            }
        
        # Используем агентов из кэша
        agents = BookingGraph._agents_cache[cache_key]
        self.stage_detector = agents['stage_detector']
        self.greeting_agent = agents['greeting']
        self.information_gathering_agent = agents['information_gathering']
        self.booking_agent = agents['booking']
        self.booking_to_master_agent = agents['booking_to_master']
        self.cancel_agent = agents['cancellation_request']
        self.reschedule_agent = agents['reschedule']
        self.view_my_booking_agent = agents['view_my_booking']
        self.tool_tester_agent = agents['tool_tester']
        
        # Создаём граф
        self.graph = self._create_graph()
        self.compiled_graph = self.graph.compile()
    
    def _create_graph(self) -> StateGraph:
        """Создание графа состояний"""
        graph = StateGraph(BookingState)
        
        # Добавляем узлы
        graph.add_node("detect_stage", self._detect_stage)
        graph.add_node("handle_greeting", self._handle_greeting)
        graph.add_node("handle_information_gathering", self._handle_information_gathering)
        graph.add_node("handle_booking", self._handle_booking)
        graph.add_node("handle_booking_to_master", self._handle_booking_to_master)
        graph.add_node("handle_cancellation_request", self._handle_cancellation_request)
        graph.add_node("handle_reschedule", self._handle_reschedule)
        graph.add_node("handle_view_my_booking", self._handle_view_my_booking)
        graph.add_node("handle_tool_tester", self._handle_tool_tester)
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
                "tool_tester": "handle_tool_tester",
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
        graph.add_edge("handle_tool_tester", END)
        return graph
    
    def _detect_stage(self, state: BookingState) -> BookingState:
        """Узел определения стадии"""
        thread = state.get("thread")
        thread_id = thread.id if thread and hasattr(thread, "id") else None
        logger.info(f"Определение стадии диалога, thread_id: {thread_id}")
        
        message = state["message"]
        chat_id = state.get("chat_id")
        
        # Сохраняем chat_id в thread для использования в CallManager
        if thread and chat_id:
            thread.chat_id = chat_id
        
        # Определяем стадию - пробрасываем исключения дальше (не обрабатываем здесь)
        stage_detection = self.stage_detector.detect_stage(message, thread)
        
        # Проверяем, был ли вызван CallManager в StageDetectorAgent
        if hasattr(self.stage_detector, '_call_manager_result') and self.stage_detector._call_manager_result:
            escalation_result = self.stage_detector._call_manager_result
            logger.info(f"CallManager был вызван в StageDetectorAgent, chat_id: {chat_id}")
            
            return {
                "answer": escalation_result.get("user_message", "Секундочку, уточняю ваш вопрос у менеджера."),
                "manager_alert": escalation_result.get("manager_alert"),
                "agent_name": "StageDetectorAgent",
                "used_tools": ["CallManager"]
            }
        
        return {
            "stage": stage_detection.stage
        }
    
    def _route_after_detect(self, state: BookingState) -> Literal[
        "greeting", "information_gathering", "booking", "booking_to_master",
        "cancellation_request", "reschedule", "view_my_booking", "tool_tester", "end"
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
            "cancellation_request", "reschedule", "view_my_booking", "tool_tester"
        ]
        
        if stage not in valid_stages:
            logger.warning(f"⚠️ Неизвестная стадия: {stage}, устанавливаю greeting")
            return "greeting"
        
        return stage
    
    def _process_agent_result(self, agent, answer: str, state: BookingState, agent_name: str) -> BookingState:
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
        
        # Проверяем, был ли вызван CallManager через инструмент
        if answer == "[CALL_MANAGER_RESULT]" and hasattr(agent, '_call_manager_result') and agent._call_manager_result:
            escalation_result = agent._call_manager_result
            chat_id = state.get("chat_id", "unknown")
            
            logger.info(f"CallManager был вызван через инструмент в агенте {agent_name}, chat_id: {chat_id}")
            
            return {
                "answer": escalation_result.get("user_message", "Секундочку, уточняю ваш вопрос у менеджера."),
                "manager_alert": escalation_result.get("manager_alert"),
                "agent_name": agent_name,
                "used_tools": used_tools
            }
        
        return {"answer": answer, "agent_name": agent_name, "used_tools": used_tools}
    
    def _prepare_thread_for_agent(self, state: BookingState):
        """Сохраняет chat_id в thread для использования в CallManager"""
        thread = state.get("thread")
        chat_id = state.get("chat_id")
        if thread and chat_id:
            thread.chat_id = chat_id
    
    def _handle_greeting(self, state: BookingState) -> BookingState:
        """Обработка приветствия"""
        logger.info("Обработка приветствия")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.greeting_agent(message, thread)
        return self._process_agent_result(self.greeting_agent, answer, state, "GreetingAgent")
    
    def _handle_information_gathering(self, state: BookingState) -> BookingState:
        """Обработка сбора информации"""
        logger.info("Обработка сбора информации")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.information_gathering_agent(message, thread)
        return self._process_agent_result(self.information_gathering_agent, answer, state, "InformationGatheringAgent")
    
    def _handle_booking(self, state: BookingState) -> BookingState:
        """Обработка бронирования"""
        logger.info("Обработка бронирования")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.booking_agent(message, thread)
        return self._process_agent_result(self.booking_agent, answer, state, "BookingAgent")
    
    def _handle_booking_to_master(self, state: BookingState) -> BookingState:
        """Обработка бронирования к мастеру"""
        logger.info("Обработка бронирования к мастеру")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.booking_to_master_agent(message, thread)
        return self._process_agent_result(self.booking_to_master_agent, answer, state, "BookingToMasterAgent")
    
    def _handle_cancellation_request(self, state: BookingState) -> BookingState:
        """Обработка отмены"""
        logger.info("Обработка отмены")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.cancel_agent(message, thread)
        return self._process_agent_result(self.cancel_agent, answer, state, "CancelBookingAgent")
    
    def _handle_reschedule(self, state: BookingState) -> BookingState:
        """Обработка переноса"""
        logger.info("Обработка переноса")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.reschedule_agent(message, thread)
        return self._process_agent_result(self.reschedule_agent, answer, state, "RescheduleAgent")
    
    def _handle_view_my_booking(self, state: BookingState) -> BookingState:
        """Обработка просмотра записей"""
        logger.info("Обработка просмотра записей")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.view_my_booking_agent(message, thread)
        return self._process_agent_result(self.view_my_booking_agent, answer, state, "ViewMyBookingAgent")
    
    def _handle_tool_tester(self, state: BookingState) -> BookingState:
        """Обработка тестирования инструментов"""
        logger.info("Обработка тестирования инструментов")
        self._prepare_thread_for_agent(state)
        message = state["message"]
        thread = state["thread"]
        
        # Пробрасываем исключения дальше (не обрабатываем здесь)
        answer = self.tool_tester_agent(message, thread)
        return self._process_agent_result(self.tool_tester_agent, answer, state, "ToolTesterAgent")
    
             