"""
Скрипт запуска Tool Manager
"""
import subprocess
import sys
import webbrowser
import time
from pathlib import Path


def main():
    # Определяем путь к app.py
    script_dir = Path(__file__).parent
    app_path = script_dir / "app.py"
    
    if not app_path.exists():
        print(f"Ошибка: файл {app_path} не найден")
        sys.exit(1)
    
    # Запускаем Streamlit
    print("🚀 Запуск Tool Manager...")
    print("📝 Откройте браузер по адресу: http://localhost:8502")
    print("⏹️  Для остановки нажмите Ctrl+C\n")
    
    # Запускаем Streamlit на порту 8502 (чтобы не конфликтовать с другими приложениями)
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.headless", "true", "--server.port", "8502"],
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
        print("\n⏹️  Остановка Tool Manager...")
        process.terminate()
        process.wait()
        print("✅ Tool Manager остановлен")


if __name__ == "__main__":
    main()







