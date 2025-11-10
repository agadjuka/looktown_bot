"""Модуль для работы с YDB"""
import os
import ydb
import ydb.iam
from typing import Optional


class YDBClient:
    """Клиент для работы с YDB"""
    
    def __init__(self):
        self.endpoint = os.getenv("YDB_ENDPOINT")
        self.database = os.getenv("YDB_DATABASE")
        
        if not self.endpoint or not self.database:
            raise ValueError("Не заданы YDB_ENDPOINT и YDB_DATABASE в переменных окружения")
        
        # Получаем IAM токен или используем service account
        iam_token = os.getenv("YC_IAM_TOKEN")
        service_account_key_file = os.getenv("YC_SERVICE_ACCOUNT_KEY_FILE")
        
        if iam_token:
            # Используем IAM токен
            credentials = ydb.AccessTokenCredentials(iam_token)
        elif service_account_key_file:
            # Используем service account key файл
            credentials = ydb.iam.ServiceAccountCredentials.from_file(service_account_key_file)
        else:
            # Пытаемся получить креды из метаданных окружения (Serverless Containers)
            credentials = ydb.iam.MetadataUrlCredentials()
        
        # Инициализация драйвера YDB
        self.driver = ydb.Driver(
            endpoint=self.endpoint,
            database=self.database,
            credentials=credentials
        )
        self.driver.wait(fail_fast=True, timeout=10)
        self.pool = ydb.SessionPool(self.driver)
    
    def _execute_query(self, query: str, params: dict = None):
        """Выполнение запроса к YDB"""
        def _tx(session):
            prepared_query = session.prepare(query)
            # Преобразуем строки в байты для параметров
            if params:
                byte_params = {}
                for key, value in params.items():
                    if isinstance(value, str):
                        byte_params[key] = value.encode('utf-8')
                    else:
                        byte_params[key] = value
                return session.transaction().execute(prepared_query, byte_params, commit_tx=True)
            else:
                return session.transaction().execute(prepared_query, {}, commit_tx=True)
        return self.pool.retry_operation_sync(_tx)
    
    def init_schema(self):
        """Создание таблиц для маппинга chat_id -> last_response_id, thread_id и assistant_id"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS chat_threads (
            chat_id String,
            thread_id String,
            last_response_id String,
            updated_at Timestamp,
            PRIMARY KEY (chat_id)
        );
        
        CREATE TABLE IF NOT EXISTS assistants (
            assistant_name String,
            assistant_id String,
            updated_at Timestamp,
            PRIMARY KEY (assistant_name)
        );
        """
        def _tx(session):
            return session.execute_scheme(create_table_query)
        self.pool.retry_operation_sync(_tx)
    
    def get_last_response_id(self, chat_id: str) -> Optional[str]:
        """Получение last_response_id по chat_id"""
        query = """
        DECLARE $id AS String; 
        SELECT last_response_id FROM chat_threads WHERE chat_id = $id;
        """
        result = self._execute_query(query, {"$id": chat_id})
        rows = result[0].rows
        return rows[0].last_response_id.decode() if rows and rows[0].last_response_id else None
    
    def save_response_id(self, chat_id: str, response_id: str):
        """Сохранение маппинга chat_id -> last_response_id"""
        query = """
        DECLARE $cid AS String; 
        DECLARE $rid AS String;
        UPSERT INTO chat_threads (chat_id, last_response_id, updated_at)
        VALUES ($cid, $rid, CurrentUtcTimestamp());
        """
        self._execute_query(query, {
            "$cid": chat_id, 
            "$rid": response_id
        })
    
    def get_thread_id(self, chat_id: str) -> Optional[str]:
        """Получение thread_id по chat_id"""
        query = """
        DECLARE $id AS String; 
        SELECT thread_id FROM chat_threads WHERE chat_id = $id;
        """
        result = self._execute_query(query, {"$id": chat_id})
        rows = result[0].rows
        return rows[0].thread_id.decode() if rows and rows[0].thread_id else None
    
    def save_thread_id(self, chat_id: str, thread_id: str):
        """Сохранение маппинга chat_id -> thread_id"""
        query = """
        DECLARE $cid AS String; 
        DECLARE $tid AS String;
        UPSERT INTO chat_threads (chat_id, thread_id, updated_at)
        VALUES ($cid, $tid, CurrentUtcTimestamp());
        """
        self._execute_query(query, {
            "$cid": chat_id, 
            "$tid": thread_id
        })
    
    def reset_thread(self, chat_id: str):
        """Сброс thread для чата"""
        query = """
        DECLARE $cid AS String;
        UPDATE chat_threads SET thread_id = NULL, updated_at = CurrentUtcTimestamp()
        WHERE chat_id = $cid;
        """
        self._execute_query(query, {"$cid": chat_id})
    
    def reset_context(self, chat_id: str):
        """Сброс контекста для чата (очистка last_response_id и thread_id)"""
        query = """
        DECLARE $cid AS String;
        UPDATE chat_threads SET last_response_id = NULL, thread_id = NULL, updated_at = CurrentUtcTimestamp()
        WHERE chat_id = $cid;
        """
        self._execute_query(query, {"$cid": chat_id})
    
    def get_assistant_id(self, assistant_name: str) -> Optional[str]:
        """Получение assistant_id по имени"""
        query = """
        DECLARE $name AS String; 
        SELECT assistant_id FROM assistants WHERE assistant_name = $name;
        """
        result = self._execute_query(query, {"$name": assistant_name})
        rows = result[0].rows
        return rows[0].assistant_id.decode() if rows and rows[0].assistant_id else None
    
    def save_assistant_id(self, assistant_name: str, assistant_id: str):
        """Сохранение маппинга assistant_name -> assistant_id"""
        from .services.logger_service import logger
        logger.info(f"=== СОХРАНЕНИЕ ASSISTANT ID В YDB ===")
        logger.info(f"assistant_name: {assistant_name}")
        logger.info(f"assistant_id: {assistant_id}")
        
        try:
            query = """
            DECLARE $name AS String; 
            DECLARE $id AS String;
            UPSERT INTO assistants (assistant_name, assistant_id, updated_at)
            VALUES ($name, $id, CurrentUtcTimestamp());
            """
            logger.info("Выполнение запроса UPSERT...")
            self._execute_query(query, {
                "$name": assistant_name, 
                "$id": assistant_id
            })
            logger.info(f"✅ Запрос выполнен успешно")
            
            # Проверяем, что действительно сохранилось
            logger.info("Проверка сохранения...")
            saved_id = self.get_assistant_id(assistant_name)
            if saved_id == assistant_id:
                logger.info(f"✅ Проверка пройдена: ID корректно сохранён")
            else:
                logger.error(f"❌ Проверка не прошла! Ожидалось: {assistant_id}, получено: {saved_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения assistant_id в YDB: {e}", exc_info=True)
            raise
    
    def close(self):
        """Закрытие соединения с YDB"""
        if self.driver:
            self.driver.stop()


# Глобальный экземпляр клиента
ydb_client = None

def get_ydb_client() -> YDBClient:
    """Получение глобального экземпляра YDB клиента"""
    global ydb_client
    if ydb_client is None:
        ydb_client = YDBClient()
        ydb_client.init_schema()
    return ydb_client

