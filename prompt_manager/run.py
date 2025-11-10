"""
Скрипт запуска Prompt Manager
"""
import subprocess
import sys
import webbrowser
import time
import os
from pathlib import Path

def main():
    # Определяем путь к app.py
    script_dir = Path(__file__).parent
    app_path = script_dir / "app.py"
    
    if not app_path.exists():
        print(f"Ошибка: файл {app_path} не найден")
        sys.exit(1)
    
    # Запускаем Streamlit
    print("🚀 Запуск Prompt Manager...")
    print("📝 Откройте браузер по адресу: http://localhost:8502")
    print("⏹️  Для остановки нажмите Ctrl+C\n")
    
    # Запускаем Streamlit на порту 8502 (чтобы не конфликтовать с playground)
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", "8502", "--server.headless", "true"],
        cwd=str(script_dir.parent)
    )
    
    # Ждём немного и открываем браузер
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:8502")
    except Exception as e:
        print(f"Не удалось автоматически открыть браузер: {e}")
        print("Откройте вручную: http://localhost:8502")
    
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n⏹️  Остановка Prompt Manager...")
        process.terminate()
        process.wait()
        print("✅ Prompt Manager остановлен")

if __name__ == "__main__":
    main()


