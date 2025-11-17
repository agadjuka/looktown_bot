"""
Агент для тестирования инструментов
"""
from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService
from .tools.service_tools import GetCategories, GetServices


class ToolTesterAgent(BaseAgent):
    """Агент для тестирования инструментов и ответов на вопросы клиентов по поводу инструментов"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """Твоя задача — тестировать инструменты, отвечать на вопросы клиентов по поводу инструментов."""
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=[GetCategories, GetServices],
            agent_name="Тестер инструментов"
        )

