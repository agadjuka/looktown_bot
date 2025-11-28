"""Модуль для работы с хранилищем данных."""

from src.storage.topic_storage import BaseTopicStorage
from src.storage.ydb_topic_storage import YDBTopicStorage
from src.storage.topic_storage_factory import get_topic_storage

__all__ = [
    "BaseTopicStorage",
    "YDBTopicStorage",
    "get_topic_storage",
]

