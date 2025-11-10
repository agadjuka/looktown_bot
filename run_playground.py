"""
Запуск Streamlit Playground
"""
import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "streamlit", "run", "playground.py"])

