"""Фабрика для создания экземпляра хранилища топиков."""

import logging
import os

from app.storage.firestore_topic_storage import FirestoreTopicStorage
from app.storage.topic_storage import BaseTopicStorage

logger = logging.getLogger(__name__)

# Глобальный экземпляр хранилища
_topic_storage: BaseTopicStorage | None = None


def get_topic_storage() -> BaseTopicStorage:
    """
    Получает или создает экземпляр хранилища топиков.
    
    Returns:
        Экземпляр хранилища топиков (по умолчанию FirestoreTopicStorage)
    """
    global _topic_storage
    
    if _topic_storage is None:
        try:
            _topic_storage = FirestoreTopicStorage()
            logger.info("Инициализирован FirestoreTopicStorage")
        except ValueError as e:
            logger.error(
                "Не удалось инициализировать FirestoreTopicStorage: %s. "
                "Убедитесь, что GOOGLE_CLOUD_PROJECT установлен.",
                str(e),
            )
            raise
        except Exception as e:
            logger.error(
                "Ошибка при инициализации хранилища топиков: %s",
                str(e),
            )
            raise
    
    return _topic_storage

