"""Модуль для работы с хранилищем данных."""

from app.storage.topic_storage import BaseTopicStorage
from app.storage.firestore_topic_storage import FirestoreTopicStorage
from app.storage.topic_storage_factory import get_topic_storage

__all__ = [
    "BaseTopicStorage",
    "FirestoreTopicStorage",
    "get_topic_storage",
]

