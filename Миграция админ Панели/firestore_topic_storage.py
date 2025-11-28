"""Реализация хранилища топиков на базе Firestore."""

import logging
import os
from typing import Optional

from google.cloud import firestore

from app.storage.topic_storage import BaseTopicStorage

logger = logging.getLogger(__name__)


class FirestoreTopicStorage(BaseTopicStorage):
    """
    Реализация хранилища топиков на базе Firestore.
    
    Структура хранения:
    - Коллекция: adminpanel
    - Документ: {user_id} - содержит topic_id и topic_name
    - Индекс: по topic_id для обратного поиска (через запрос)
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        database_id: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        """
        Инициализирует хранилище топиков в Firestore.
        
        Args:
            project_id: ID проекта GCP (если None, берется из GOOGLE_CLOUD_PROJECT)
            database_id: ID базы данных Firestore (если None, берется из FIRESTORE_DATABASE или "(default)")
            collection_name: Название коллекции (если None, используется "adminpanel")
        """
        project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT должен быть установлен для использования FirestoreTopicStorage"
            )
        
        database_id = database_id or os.getenv("FIRESTORE_DATABASE", "(default)")
        collection_name = collection_name or "adminpanel"
        
        self.client = firestore.Client(project=project_id, database=database_id)
        self.collection = self.client.collection(collection_name)
        
        logger.debug(
            "Инициализирован FirestoreTopicStorage (project=%s, database=%s, collection=%s)",
            project_id,
            database_id,
            collection_name,
        )

    def save_topic(self, user_id: int, topic_id: int, topic_name: str) -> None:
        """
        Сохраняет связь между пользователем и топиком.
        
        Args:
            user_id: ID пользователя Telegram
            topic_id: ID топика в Telegram Forum
            topic_name: Название топика
        """
        try:
            doc_ref = self.collection.document(str(user_id))
            doc_ref.set({
                "user_id": user_id,
                "topic_id": topic_id,
                "topic_name": topic_name,
            }, merge=True)
            
            logger.debug(
                "Сохранена связь: user_id=%s -> topic_id=%s (%s)",
                user_id,
                topic_id,
                topic_name,
            )
        except Exception as e:
            logger.error(
                "Ошибка при сохранении связи user_id=%s -> topic_id=%s: %s",
                user_id,
                topic_id,
                str(e),
            )
            raise

    def get_topic_id(self, user_id: int) -> int | None:
        """
        Получает ID топика по ID пользователя.
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            ID топика или None, если связь не найдена
        """
        try:
            doc_ref = self.collection.document(str(user_id))
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            topic_id = data.get("topic_id")
            
            return int(topic_id) if topic_id is not None else None
        except Exception as e:
            logger.error(
                "Ошибка при получении topic_id для user_id=%s: %s",
                user_id,
                str(e),
            )
            return None

    def get_user_id(self, topic_id: int) -> int | None:
        """
        Получает ID пользователя по ID топика (обратная связь).
        
        Args:
            topic_id: ID топика в Telegram Forum
            
        Returns:
            ID пользователя или None, если связь не найдена
        """
        try:
            # Используем запрос для поиска по topic_id
            query = self.collection.where("topic_id", "==", topic_id).limit(1)
            docs = list(query.stream())
            
            if not docs:
                return None
            
            doc = docs[0]
            data = doc.to_dict()
            user_id = data.get("user_id")
            
            return int(user_id) if user_id is not None else None
        except Exception as e:
            logger.error(
                "Ошибка при получении user_id для topic_id=%s: %s",
                topic_id,
                str(e),
            )
            return None

    def set_mode(self, user_id: int, mode: str) -> None:
        """
        Устанавливает режим работы для пользователя.
        
        Args:
            user_id: ID пользователя Telegram
            mode: Режим работы ("auto" или "manual")
        """
        if mode not in ("auto", "manual"):
            raise ValueError(f"Недопустимый режим: {mode}. Допустимые значения: 'auto', 'manual'")
        
        try:
            doc_ref = self.collection.document(str(user_id))
            doc_ref.set({
                "mode": mode,
            }, merge=True)
            
            logger.debug(
                "Установлен режим для user_id=%s: %s",
                user_id,
                mode,
            )
        except Exception as e:
            logger.error(
                "Ошибка при установке режима для user_id=%s: %s",
                user_id,
                str(e),
            )
            raise

    def get_mode(self, user_id: int) -> str:
        """
        Получает режим работы для пользователя.
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            Режим работы ("auto" или "manual"). По умолчанию "auto", если поле не установлено.
        """
        try:
            doc_ref = self.collection.document(str(user_id))
            doc = doc_ref.get()
            
            if not doc.exists:
                return "auto"
            
            data = doc.to_dict()
            mode = data.get("mode")
            
            # Возвращаем режим или "auto" по умолчанию
            return mode if mode in ("auto", "manual") else "auto"
        except Exception as e:
            logger.error(
                "Ошибка при получении режима для user_id=%s: %s",
                user_id,
                str(e),
            )
            # В случае ошибки возвращаем "auto" по умолчанию
            return "auto"

