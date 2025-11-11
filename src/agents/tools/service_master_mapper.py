"""
Модуль для сопоставления услуг с типами мастеров
Анализирует services.json и создает маппинг услуг к типам мастеров
"""
from typing import Dict, List, Set
from .services_data_loader import _data_loader


class ServiceMasterMapper:
    """Класс для сопоставления услуг с типами мастеров"""
    
    def __init__(self):
        """Инициализация маппера"""
        self._service_to_master_type: Dict[str, Set[str]] = {}
        self._load_mapping()
    
    def _load_mapping(self):
        """Загружает маппинг услуг к типам мастеров из services.json"""
        try:
            data = _data_loader.load_data()
            
            # Маппинг категорий услуг к типам мастеров
            # Учитываем все возможные варианты должностей из API
            category_to_master_type = {
                "Маникюр": {
                    "Мастер", "мастер", "Топ-мастер", "топ-мастер",
                    "Мастер маникюра", "мастер маникюра", "младший мастер маникюра",
                    "Мастер ногтевого сервиса", "мастер ногтевого сервиса",
                    "Юниор", "юниор"
                },
                "Педикюр": {
                    "Мастер", "мастер", "Топ-мастер", "топ-мастер",
                    "Мастер маникюра", "мастер маникюра", "младший мастер маникюра",
                    "Мастер ногтевого сервиса", "мастер ногтевого сервиса",
                    "Юниор", "юниор"
                },
                "Массаж": {
                    "Массажист", "массажист"
                },
                "Брови": {
                    "Бровист", "бровист"
                },
                "Ресницы": {
                    "Мастер по наращиванию ресниц", "мастер по наращиванию ресниц"
                },
                "Макияж": {
                    "Визажист", "визажист"
                },
                "Парикмахерские услуги": {
                    "Парикмахер-колорист", "парикмахер-колорист", "Парикмахер", "парикмахер"
                },
                "Пирсинг": set(),  # Может быть разный тип мастера
                "Лазерная эпиляция": set(),  # Может быть разный тип мастера
                "Косметология": {
                    "Косметолог", "косметолог", "Косметолог-эстетист", "косметолог-эстетист"
                },
                "Депиляция": set(),  # Может быть разный тип мастера
                "LOOKTOWN SPA": {
                    "Массажист", "массажист"
                },
                "Услуги для мужчин": set(),  # Может быть разный тип мастера
            }
            
            # Создаем маппинг для каждой услуги
            for category_id, category_data in data.items():
                category_name = category_data.get("category_name", "")
                master_types = category_to_master_type.get(category_name, set())
                
                services = category_data.get("services", [])
                for service in services:
                    service_name = service.get("name", "").lower()
                    service_id = str(service.get("id", ""))
                    
                    # Добавляем маппинг для ID услуги
                    if service_id not in self._service_to_master_type:
                        self._service_to_master_type[service_id] = set()
                    self._service_to_master_type[service_id].update(master_types)
                    
                    # Добавляем маппинг для названия услуги
                    if service_name not in self._service_to_master_type:
                        self._service_to_master_type[service_name] = set()
                    self._service_to_master_type[service_name].update(master_types)
            
            # Добавляем прямые маппинги по ключевым словам
            keyword_mappings = {
                "маникюр": {
                    "Мастер", "мастер", "Топ-мастер", "топ-мастер",
                    "Мастер маникюра", "мастер маникюра", "младший мастер маникюра",
                    "Мастер ногтевого сервиса", "мастер ногтевого сервиса",
                    "Юниор", "юниор"
                },
                "маник": {
                    "Мастер", "мастер", "Топ-мастер", "топ-мастер",
                    "Мастер маникюра", "мастер маникюра", "младший мастер маникюра",
                    "Мастер ногтевого сервиса", "мастер ногтевого сервиса",
                    "Юниор", "юниор"
                },
                "педикюр": {
                    "Мастер", "мастер", "Топ-мастер", "топ-мастер",
                    "Мастер маникюра", "мастер маникюра", "младший мастер маникюра",
                    "Мастер ногтевого сервиса", "мастер ногтевого сервиса",
                    "Юниор", "юниор"
                },
                "ногти": {
                    "Мастер", "мастер", "Топ-мастер", "топ-мастер",
                    "Мастер маникюра", "мастер маникюра", "младший мастер маникюра",
                    "Мастер ногтевого сервиса", "мастер ногтевого сервиса",
                    "Юниор", "юниор"
                },
                "массаж": {"Массажист", "массажист"},
                "массажист": {"Массажист", "массажист"},
                "брови": {"Бровист", "бровист"},
                "ресницы": {"Мастер по наращиванию ресниц", "мастер по наращиванию ресниц"},
                "макияж": {"Визажист", "визажист"},
                "стрижка": {"Парикмахер-колорист", "парикмахер-колорист", "Парикмахер", "парикмахер"},
                "косметология": {"Косметолог", "косметолог", "Косметолог-эстетист", "косметолог-эстетист"},
            }
            
            for keyword, master_types in keyword_mappings.items():
                if keyword not in self._service_to_master_type:
                    self._service_to_master_type[keyword] = set()
                self._service_to_master_type[keyword].update(master_types)
                
        except Exception as e:
            # Если не удалось загрузить, используем базовые маппинги
            self._service_to_master_type = {
                "маникюр": {"Мастер маникюра", "мастер маникюра", "младший мастер маникюра"},
                "педикюр": {"Мастер маникюра", "мастер маникюра", "младший мастер маникюра"},
                "массаж": {"Массажист", "массажист"},
            }
    
    def get_master_types_for_service(self, service_name: str) -> Set[str]:
        """
        Получает типы мастеров для указанной услуги
        
        Args:
            service_name: Название услуги (может быть неточным)
            
        Returns:
            Set[str]: Множество типов мастеров
        """
        service_lower = service_name.lower()
        
        # Прямой поиск
        if service_lower in self._service_to_master_type:
            return self._service_to_master_type[service_lower]
        
        # Поиск по ключевым словам
        master_types = set()
        for keyword, types in self._service_to_master_type.items():
            if keyword in service_lower or service_lower in keyword:
                master_types.update(types)
        
        return master_types
    
    def is_master_suitable(
        self, 
        master_position_title: str, 
        service_name: str,
        master_position_description: str = "",
        master_specialization: str = ""
    ) -> bool:
        """
        Проверяет, подходит ли мастер для указанной услуги
        
        Args:
            master_position_title: Название должности мастера (из position.title)
            service_name: Название услуги
            master_position_description: Описание должности (из position.description)
            master_specialization: Специализация мастера (из specialization)
            
        Returns:
            bool: True если мастер подходит для услуги
        """
        if not master_position_title:
            return False
        
        master_types = self.get_master_types_for_service(service_name)
        
        if not master_types:
            # Если нет специфичных требований, принимаем любого мастера
            return True
        
        # Проверяем все поля мастера
        master_title_lower = master_position_title.lower()
        master_desc_lower = (master_position_description or "").lower()
        master_spec_lower = (master_specialization or "").lower()
        
        # Объединяем все текстовые поля мастера для проверки
        all_master_text = f"{master_title_lower} {master_desc_lower} {master_spec_lower}".lower()
        
        # Проверяем, соответствует ли должность мастера требуемым типам
        for master_type in master_types:
            master_type_lower = master_type.lower()
            # Проверяем в title, description и specialization
            if (master_type_lower in master_title_lower or 
                master_type_lower in master_desc_lower or 
                master_type_lower in master_spec_lower or
                master_type_lower in all_master_text):
                return True
        
        return False


# Глобальный экземпляр маппера
_service_master_mapper = ServiceMasterMapper()


def get_service_master_mapper() -> ServiceMasterMapper:
    """Получить глобальный экземпляр маппера"""
    return _service_master_mapper

