import shutil
import os
from pathlib import Path

# Получаем текущую директорию
base_dir = Path(__file__).parent

# Список папок для удаления
folders_to_remove = [
    'debug_logs',
    'YC Wine Assistant',
    'Образец для деплоя'
]

# Удаляем папки
for folder in folders_to_remove:
    folder_path = base_dir / folder
    if folder_path.exists():
        try:
            shutil.rmtree(folder_path)
            print(f"✅ Удалена папка: {folder}")
        except Exception as e:
            print(f"❌ Ошибка при удалении {folder}: {e}")
    else:
        print(f"ℹ️  Папка не найдена: {folder}")

# Удаляем __pycache__ папки рекурсивно
for pycache_dir in base_dir.rglob('__pycache__'):
    try:
        shutil.rmtree(pycache_dir)
        print(f"✅ Удалена папка: {pycache_dir.relative_to(base_dir)}")
    except Exception as e:
        print(f"❌ Ошибка при удалении {pycache_dir}: {e}")

print("\n✅ Очистка завершена!")



