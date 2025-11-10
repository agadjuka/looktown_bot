"""
Скрипт запуска Streamlit Playground
"""
import subprocess
import sys
import webbrowser
import time
from pathlib import Path

def main():
    # Определяем путь к playground.py
    script_dir = Path(__file__).parent
    playground_path = script_dir / "playground.py"
    
    if not playground_path.exists():
        print(f"Ошибка: файл {playground_path} не найден")
        sys.exit(1)
    
    # Запускаем Streamlit
    print("🚀 Запуск LangGraph Agent Playground...")
    print("📝 Откройте браузер по адресу: http://localhost:8501")
    print("⏹️  Для остановки нажмите Ctrl+C\n")
    
    # Запускаем Streamlit на порту 8501 (по умолчанию)
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(playground_path), "--server.headless", "true"],
        cwd=str(script_dir)
    )
    
    # Ждём немного и открываем браузер
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:8501")
    except Exception as e:
        print(f"Не удалось автоматически открыть браузер: {e}")
        print("Откройте вручную: http://localhost:8501")
    
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n⏹️  Остановка Playground...")
        process.terminate()
        process.wait()
        print("✅ Playground остановлен")

if __name__ == "__main__":
    main()

