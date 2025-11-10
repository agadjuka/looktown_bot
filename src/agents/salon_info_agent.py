"""
Агент для стадии О салоне
"""
from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService


class SalonInfoAgent(BaseAgent):
    """Агент для стадии О салоне"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """Скажи, что у нас лучший салон в Москве."""
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=None,
            agent_name="О салоне"
        )
