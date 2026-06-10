import os
import sys
import time
import subprocess
import signal
from dotenv import load_dotenv

load_dotenv()
os.environ["PYTHONUNBUFFERED"] = "1"


BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")

def run():
    print("=========================================================")
    print("Starting DataMind AI Catalog & Copilot Server Suite...")
    print("=========================================================")
    
    # 1. Start FastAPI Backend
    # Use python -m uvicorn to ensure correct package discovery
    backend_cmd = [
        sys.executable, "-m", "uvicorn", 
        "backend.app:app", 
        "--host", BACKEND_HOST, 
        "--port", BACKEND_PORT
    ]
    print(f"-> Launching FastAPI Backend on http://{BACKEND_HOST}:{BACKEND_PORT}")
    backend_process = subprocess.Popen(backend_cmd)
    
    # Give backend a moment to boot
    time.sleep(2)
    
    # 2. Start Streamlit Frontend
    # Use streamlit run to boot frontend
    streamlit_cmd = [
        "streamlit", "run", 
        "frontend/app.py"
    ]
    print(f"-> Launching Streamlit UI...")
    frontend_process = subprocess.Popen(streamlit_cmd)
    
    try:
        # Keep main thread alive monitoring both processes
        while True:
            time.sleep(1)
            # Check if any process terminated
            if backend_process.poll() is not None:
                print("FastAPI Backend terminated unexpectedly.")
                break
            if frontend_process.poll() is not None:
                print("Streamlit Frontend terminated unexpectedly.")
                break
    except KeyboardInterrupt:
        print("\nShutting down servers...")
    finally:
        # Terminate both
        backend_process.terminate()
        frontend_process.terminate()
        backend_process.wait()
        frontend_process.wait()
        print("DataMind AI Suite successfully stopped.")

if __name__ == "__main__":
    run()
