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
from ..agents.find_window_agent import FindWindowAgent
from ..agents.view_my_booking_agent import ViewMyBookingAgent
from ..agents.call_manager_agent import CallManagerAgent
from ..agents.fallback_agent import FallbackAgent

from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger


class BookingGraph:
    """Граф состояний для обработки бронирований"""
    
    # Кэш для агентов (чтобы не создавать их заново при каждом создании графа)
    _agents_cache = {}
    
    @classmethod
    def clear_cache(cls):
        """Очистить кэш агентов (полезно после пересоздания Assistant)"""
        cls._agents_cache.clear()
        logger.info("✅ Кэш агентов очищен")
    
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
                'find_window': FindWindowAgent(langgraph_service),
                'cancellation_request': CancelBookingAgent(langgraph_service),
                'reschedule': RescheduleAgent(langgraph_service),
                'view_my_booking': ViewMyBookingAgent(langgraph_service),
                'call_manager': CallManagerAgent(langgraph_service),
                'fallback': FallbackAgent(langgraph_service),
            }
        
        # Используем агентов из кэша
        agents = BookingGraph._agents_cache[cache_key]
        self.stage_detector = agents['stage_detector']
        self.greeting_agent = agents['greeting']
        self.information_gathering_agent = agents['information_gathering']
        self.booking_agent = agents['booking']
        self.booking_to_master_agent = agents['booking_to_master']
        self.find_window_agent = agents['find_window']
        self.cancel_agent = agents['cancellation_request']
        self.reschedule_agent = agents['reschedule']
        self.view_my_booking_agent = agents['view_my_booking']
        self.call_manager_agent = agents['call_manager']
        self.fallback_agent = agents['fallback']
        
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
        graph.add_node("handle_find_window", self._handle_find_window)
        graph.add_node("handle_cancellation_request", self._handle_cancellation_request)
        graph.add_node("handle_reschedule", self._handle_reschedule)
        graph.add_node("handle_view_my_booking", self._handle_view_my_booking)
        graph.add_node("handle_call_manager", self._handle_call_manager)
        graph.add_node("handle_fallback", self._handle_fallback)
        
        # Добавляем рёбра
        graph.add_edge(START, "detect_stage")
        graph.add_conditional_edges(
            "detect_stage",
            self._route_by_stage,
            {
                "greeting": "handle_greeting",
                "information_gathering": "handle_information_gathering",
                "booking": "handle_booking",
                "booking_to_master": "handle_booking_to_master",
                "find_window": "handle_find_window",
                "cancellation_request": "handle_cancellation_request",
                "reschedule": "handle_reschedule",
                "view_my_booking": "handle_view_my_booking",
                "call_manager": "handle_call_manager",
                "fallback": "handle_fallback",
            }
        )
        graph.add_edge("handle_greeting", END)
        graph.add_edge("handle_information_gathering", END)
        graph.add_edge("handle_booking", END)
        graph.add_edge("handle_booking_to_master", END)
        graph.add_edge("handle_find_window", END)
        graph.add_edge("handle_cancellation_request", END)
        graph.add_edge("handle_reschedule", END)
        graph.add_edge("handle_view_my_booking", END)
        graph.add_edge("handle_call_manager", END)
        graph.add_edge("handle_fallback", END)
        return graph
    
    def _detect_stage(self, state: BookingState) -> BookingState:
        """Узел определения стадии"""
        thread = state.get("thread")
        thread_id = thread.id if thread and hasattr(thread, "id") else None
        logger.info(f"Определение стадии диалога, thread_id: {thread_id}")
        
        message = state["message"]
        
        # Определяем стадию
        stage_detection = self.stage_detector.detect_stage(message, thread)
        
        return {
            "stage": stage_detection.stage
        }
    
    def _route_by_stage(self, state: BookingState) -> Literal[
        "greeting", "information_gathering", "booking", "booking_to_master",
        "find_window", "cancellation_request", "reschedule", "view_my_booking",
        "call_manager", "fallback"
    ]:
        """Маршрутизация по стадии"""
        stage = state.get("stage", "fallback")
        logger.info(f"Маршрутизация на стадию: {stage}")
        
        # Валидация стадии
        valid_stages = [
            "greeting", "information_gathering", "booking", "booking_to_master",
            "find_window", "cancellation_request", "reschedule", "view_my_booking",
            "call_manager", "fallback"
        ]
        
        if stage not in valid_stages:
            logger.warning(f"⚠️ Неизвестная стадия: {stage}, устанавливаю fallback")
            return "fallback"
        
        return stage
    
    def _handle_greeting(self, state: BookingState) -> BookingState:
        """Обработка приветствия"""
        logger.info("Обработка приветствия")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.greeting_agent(message, thread)
        used_tools = [tool["name"] for tool in self.greeting_agent._last_tool_calls] if hasattr(self.greeting_agent, '_last_tool_calls') and self.greeting_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "GreetingAgent", "used_tools": used_tools}
    
    def _handle_information_gathering(self, state: BookingState) -> BookingState:
        """Обработка сбора информации"""
        logger.info("Обработка сбора информации")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.information_gathering_agent(message, thread)
        used_tools = [tool["name"] for tool in self.information_gathering_agent._last_tool_calls] if hasattr(self.information_gathering_agent, '_last_tool_calls') and self.information_gathering_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "InformationGatheringAgent", "used_tools": used_tools}
    
    def _handle_booking(self, state: BookingState) -> BookingState:
        """Обработка бронирования"""
        logger.info("Обработка бронирования")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.booking_agent(message, thread)
        used_tools = [tool["name"] for tool in self.booking_agent._last_tool_calls] if hasattr(self.booking_agent, '_last_tool_calls') and self.booking_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "BookingAgent", "used_tools": used_tools}
    
    def _handle_booking_to_master(self, state: BookingState) -> BookingState:
        """Обработка бронирования к мастеру"""
        logger.info("Обработка бронирования к мастеру")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.booking_to_master_agent(message, thread)
        used_tools = [tool["name"] for tool in self.booking_to_master_agent._last_tool_calls] if hasattr(self.booking_to_master_agent, '_last_tool_calls') and self.booking_to_master_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "BookingToMasterAgent", "used_tools": used_tools}
    
    def _handle_find_window(self, state: BookingState) -> BookingState:
        """Обработка поиска окна"""
        logger.info("Обработка поиска окна")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.find_window_agent(message, thread)
        used_tools = [tool["name"] for tool in self.find_window_agent._last_tool_calls] if hasattr(self.find_window_agent, '_last_tool_calls') and self.find_window_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "FindWindowAgent", "used_tools": used_tools}
    
    def _handle_cancellation_request(self, state: BookingState) -> BookingState:
        """Обработка отмены"""
        logger.info("Обработка отмены")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.cancel_agent(message, thread)
        used_tools = [tool["name"] for tool in self.cancel_agent._last_tool_calls] if hasattr(self.cancel_agent, '_last_tool_calls') and self.cancel_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "CancelBookingAgent", "used_tools": used_tools}
    
    def _handle_reschedule(self, state: BookingState) -> BookingState:
        """Обработка переноса"""
        logger.info("Обработка переноса")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.reschedule_agent(message, thread)
        used_tools = [tool["name"] for tool in self.reschedule_agent._last_tool_calls] if hasattr(self.reschedule_agent, '_last_tool_calls') and self.reschedule_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "RescheduleAgent", "used_tools": used_tools}
    
    def _handle_view_my_booking(self, state: BookingState) -> BookingState:
        """Обработка просмотра записей"""
        logger.info("Обработка просмотра записей")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.view_my_booking_agent(message, thread)
        used_tools = [tool["name"] for tool in self.view_my_booking_agent._last_tool_calls] if hasattr(self.view_my_booking_agent, '_last_tool_calls') and self.view_my_booking_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "ViewMyBookingAgent", "used_tools": used_tools}
    
    def _handle_call_manager(self, state: BookingState) -> BookingState:
        """Обработка передачи менеджеру"""
        logger.info("Обработка передачи менеджеру")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.call_manager_agent(message, thread)
        used_tools = [tool["name"] for tool in self.call_manager_agent._last_tool_calls] if hasattr(self.call_manager_agent, '_last_tool_calls') and self.call_manager_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "CallManagerAgent", "used_tools": used_tools}
    
    def _handle_fallback(self, state: BookingState) -> BookingState:
        """Обработка fallback"""
        logger.info("Обработка fallback")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.fallback_agent(message, thread)
        used_tools = [tool["name"] for tool in self.fallback_agent._last_tool_calls] if hasattr(self.fallback_agent, '_last_tool_calls') and self.fallback_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "FallbackAgent", "used_tools": used_tools}

    def invoke(self, state: BookingState) -> BookingState:
        """Выполнение графа"""
        return self.compiled_graph.invoke(state)

        