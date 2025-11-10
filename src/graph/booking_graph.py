"""
Граф состояний для обработки бронирований
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from .booking_state import BookingState
from ..agents.stage_detector_agent import StageDetectorAgent
from ..agents.booking_agent import BookingAgent
from ..agents.cancel_booking_agent import CancelBookingAgent
from ..agents.reschedule_agent import RescheduleAgent
from ..agents.greeting_agent import GreetingAgent
from ..agents.salon_info_agent import SalonInfoAgent



from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger


class BookingGraph:
    """Граф состояний для обработки бронирований"""
    
    # Кэш для агентов (чтобы не создавать их заново при каждом создании графа)
    _agents_cache = {}
    
    def __init__(self, langgraph_service: LangGraphService):
        self.langgraph_service = langgraph_service
        
        # Используем кэш для агентов
        cache_key = id(langgraph_service)
        
        if cache_key not in BookingGraph._agents_cache:
            # Создаём агентов только если их ещё нет в кэше
            BookingGraph._agents_cache[cache_key] = {
                'stage_detector': StageDetectorAgent(langgraph_service),
                'booking_agent': BookingAgent(langgraph_service),
                'cancel_agent': CancelBookingAgent(langgraph_service),
                'reschedule_agent': RescheduleAgent(langgraph_service),
                'greeting_agent': GreetingAgent(langgraph_service),
                'salon_info_agent': SalonInfoAgent(langgraph_service),
                }
        
        # Используем агентов из кэша
        agents = BookingGraph._agents_cache[cache_key]
        self.stage_detector = agents['stage_detector']
        self.booking_agent = agents['booking_agent']
        self.cancel_agent = agents['cancel_agent']
        self.reschedule_agent = agents['reschedule_agent']
        self.greeting_agent = agents['greeting_agent']
        self.salon_info_agent = agents['salon_info_agent']
        # Создаём граф
        self.graph = self._create_graph()
        self.compiled_graph = self.graph.compile()
    
    def _create_graph(self) -> StateGraph:
        """Создание графа состояний"""
        graph = StateGraph(BookingState)
        
        # Добавляем узлы
        graph.add_node("detect_stage", self._detect_stage)
        graph.add_node("handle_greeting", self._handle_greeting)
        graph.add_node("handle_booking", self._handle_booking)
        graph.add_node("handle_cancel", self._handle_cancel)
        graph.add_node("handle_reschedule", self._handle_reschedule)
        graph.add_node("handle_salon_info", self._handle_salon_info)
        # Добавляем рёбра
        graph.add_edge(START, "detect_stage")
        graph.add_conditional_edges(
            "detect_stage",
            self._route_by_stage,
            {
                "greeting": "handle_greeting",
                "booking": "handle_booking",
                "cancel_booking": "handle_cancel",
                "reschedule": "handle_reschedule",
                "salon_info": "handle_salon_info",
                "general": "handle_greeting",  # Общие вопросы обрабатываем как приветствие
                "unknown": "handle_greeting"    # Неопределённые тоже
            }
        )
        graph.add_edge("handle_greeting", END)
        graph.add_edge("handle_booking", END)
        graph.add_edge("handle_cancel", END)
        graph.add_edge("handle_reschedule", END)
        graph.add_edge("handle_salon_info", END)
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
    
    def _route_by_stage(self, state: BookingState) -> Literal["greeting", "booking", "cancel_booking", "reschedule", "salon_info", "general", "unknown"]:
        """Маршрутизация по стадии"""
        stage = state.get("stage", "unknown")
        logger.info(f"Маршрутизация на стадию: {stage}")
        
        # Если стадия не известна, логируем предупреждение
        if stage not in ["greeting", "booking", "cancel_booking", "reschedule", "salon_info", "general", "unknown"]:
            logger.warning(f"⚠️ Неизвестная стадия: {stage}, устанавливаю unknown")
            return "unknown"
        
        return stage
    
    def _handle_greeting(self, state: BookingState) -> BookingState:
        """Обработка приветствия"""
        logger.info("Обработка приветствия")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.greeting_agent(message, thread)
        used_tools = [tool["name"] for tool in self.greeting_agent._last_tool_calls] if hasattr(self.greeting_agent, '_last_tool_calls') and self.greeting_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "GreetingAgent", "used_tools": used_tools}
    
    def _handle_booking(self, state: BookingState) -> BookingState:
        """Обработка бронирования"""
        logger.info("Обработка бронирования")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.booking_agent(message, thread)
        used_tools = [tool["name"] for tool in self.booking_agent._last_tool_calls] if hasattr(self.booking_agent, '_last_tool_calls') and self.booking_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "BookingAgent", "used_tools": used_tools}
    
    def _handle_cancel(self, state: BookingState) -> BookingState:
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
    
    def _handle_salon_info(self, state: BookingState) -> BookingState:
        """Обработка стадии О салоне"""
        logger.info("Обработка стадии salon_info")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.salon_info_agent(message, thread)
        used_tools = [tool["name"] for tool in self.salon_info_agent._last_tool_calls] if hasattr(self.salon_info_agent, '_last_tool_calls') and self.salon_info_agent._last_tool_calls else []
        
        return {"answer": answer, "agent_name": "SalonInfoAgent", "used_tools": used_tools}

    def invoke(self, state: BookingState) -> BookingState:
        """Выполнение графа"""
        return self.compiled_graph.invoke(state)

        