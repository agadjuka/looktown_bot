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
from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger


class BookingGraph:
    """Граф состояний для обработки бронирований"""
    
    def __init__(self, langgraph_service: LangGraphService):
        self.langgraph_service = langgraph_service
        
        # Создаём агентов
        self.stage_detector = StageDetectorAgent(langgraph_service)
        self.booking_agent = BookingAgent(langgraph_service)
        self.cancel_agent = CancelBookingAgent(langgraph_service)
        self.reschedule_agent = RescheduleAgent(langgraph_service)
        self.greeting_agent = GreetingAgent(langgraph_service)
        
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
                "general": "handle_greeting",  # Общие вопросы обрабатываем как приветствие
                "unknown": "handle_greeting"    # Неопределённые тоже
            }
        )
        graph.add_edge("handle_greeting", END)
        graph.add_edge("handle_booking", END)
        graph.add_edge("handle_cancel", END)
        graph.add_edge("handle_reschedule", END)
        
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
            "stage": stage_detection.stage,
            "extracted_info": stage_detection.extracted_info or {}
        }
    
    def _route_by_stage(self, state: BookingState) -> Literal["greeting", "booking", "cancel_booking", "reschedule", "general", "unknown"]:
        """Маршрутизация по стадии"""
        stage = state.get("stage", "unknown")
        logger.info(f"Маршрутизация на стадию: {stage}")
        return stage
    
    def _handle_greeting(self, state: BookingState) -> BookingState:
        """Обработка приветствия"""
        logger.info("Обработка приветствия")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.greeting_agent(message, thread)
        
        return {"answer": answer}
    
    def _handle_booking(self, state: BookingState) -> BookingState:
        """Обработка бронирования"""
        logger.info("Обработка бронирования")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.booking_agent(message, thread)
        
        return {"answer": answer}
    
    def _handle_cancel(self, state: BookingState) -> BookingState:
        """Обработка отмены"""
        logger.info("Обработка отмены")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.cancel_agent(message, thread)
        
        return {"answer": answer}
    
    def _handle_reschedule(self, state: BookingState) -> BookingState:
        """Обработка переноса"""
        logger.info("Обработка переноса")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.reschedule_agent(message, thread)
        
        return {"answer": answer}
    
    def invoke(self, state: BookingState) -> BookingState:
        """Выполнение графа"""
        return self.compiled_graph.invoke(state)

