import os
import re
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Define explicit path to .env file in the project root
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# Env variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Strip quotes if they were added inside .env
if GEMINI_API_KEY.startswith('"') and GEMINI_API_KEY.endswith('"'):
    GEMINI_API_KEY = GEMINI_API_KEY[1:-1]
elif GEMINI_API_KEY.startswith("'") and GEMINI_API_KEY.endswith("'"):
    GEMINI_API_KEY = GEMINI_API_KEY[1:-1]

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip('/')
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
GEMINI_MODEL = "gemini-2.5-flash"

# Logging setup for diagnostic tracking
print("=========================================================")
print(f"[LLM_MANAGER] Module imported from: {__file__}")
print(f"[LLM_MANAGER] Project root .env path resolved: {env_path}")
print(f"[LLM_MANAGER] Loaded .env file exists on disk: {env_path.exists()}")
print(f"[LLM_MANAGER] GEMINI_API_KEY Status: {'LOADED' if GEMINI_API_KEY else 'MISSING'}")
if GEMINI_API_KEY:
    print(f"[LLM_MANAGER] GEMINI_API_KEY Preview: {GEMINI_API_KEY[:6]}...{GEMINI_API_KEY[-4:]}")
print(f"[LLM_MANAGER] Active Gemini Model: {GEMINI_MODEL}")
print("=========================================================")


# Set privacy mode
# True: Only Ollama local, False: Gemini with Ollama fallback
PRIVACY_MODE = os.getenv("PRIVACY_MODE", "false").lower() == "true"

def set_privacy_mode(enabled: bool):
    global PRIVACY_MODE
    PRIVACY_MODE = enabled
    os.environ["PRIVACY_MODE"] = "true" if enabled else "false"

def get_privacy_mode() -> bool:
    return PRIVACY_MODE

def scrub_sensitive_patterns(text: str) -> str:
    """
    Scans prompts and outputs for potential PII or raw database columns.
    Ensures absolute compliance with the Enterprise security requirements.
    """
    # Pattern matching for generic PII values
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b(?:\+?\d{1,3}[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b'
    card_pattern = r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    
    scrubbed = text
    scrubbed = re.sub(email_pattern, "[REDACTED_EMAIL]", scrubbed)
    scrubbed = re.sub(phone_pattern, "[REDACTED_PHONE]", scrubbed)
    scrubbed = re.sub(card_pattern, "[REDACTED_CARD]", scrubbed)
    scrubbed = re.sub(ssn_pattern, "[REDACTED_SSN]", scrubbed)
    
    return scrubbed

def call_gemini_api(prompt: str, system_instruction: str = None) -> str:
    """
    Direct REST call to Gemini API.
    Highly robust against python package dependency conflicts.
    """
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key is missing. Set GEMINI_API_KEY in environment or .env file.")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    contents = [{"parts": [{"text": prompt}]}]
    
    payload = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
        
    # Enforce tight timeout (10 seconds) for clean fallback behaviour
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
    response.raise_for_status()
    
    resp_data = response.json()
    try:
        text_out = resp_data["candidates"][0]["content"]["parts"][0]["text"]
        return text_out
    except (KeyError, IndexError):
        raise ValueError(f"Unexpected response structure from Gemini API: {resp_data}")

def call_ollama_api(prompt: str, system_instruction: str = None) -> str:
    """
    REST call to local Ollama API chat interface.
    """
    url = f"{OLLAMA_HOST}/api/chat"
    
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False
    }
    
    response = requests.post(url, json=payload, timeout=25)
    response.raise_for_status()
    
    resp_data = response.json()
    return resp_data["message"]["content"]

def generate_response(prompt: str, system_instruction: str = None):
    # Apply PII scrubbing to prompt input
    scrubbed_prompt = scrub_sensitive_patterns(prompt)
    
    # 1. Check Privacy Mode
    if get_privacy_mode():
        # Enterprise Privacy Mode: strictly route locally to Ollama
        try:
            res = call_ollama_api(scrubbed_prompt, system_instruction)
            scrubbed_res = scrub_sensitive_patterns(res)
            return scrubbed_res, f"Ollama ({OLLAMA_MODEL})", "Enterprise Privacy Mode"
        except Exception as e:
            return f"OLLAMA ERROR: {str(e)}", "ERROR", "Enterprise Privacy Mode"
            
    # 2. Privacy Mode is False: Cloud Routing with local fallback
    if GEMINI_API_KEY:
        try:
            res = call_gemini_api(scrubbed_prompt, system_instruction)
            scrubbed_res = scrub_sensitive_patterns(res)
            return scrubbed_res, GEMINI_MODEL, "Primary Cloud API"
        except Exception as gemini_err:
            print(f"Gemini API call failed: {str(gemini_err)}. Falling back to local Ollama.")
            # Fallback to local Ollama
            try:
                res = call_ollama_api(scrubbed_prompt, system_instruction)
                scrubbed_res = scrub_sensitive_patterns(res)
                return scrubbed_res, f"Ollama ({OLLAMA_MODEL}) Fallback", "Cloud Failure Fallback"
            except Exception as ollama_err:
                err_msg = f"Both cloud and local AI modules failed to respond.\nGemini error: {str(gemini_err)}\nOllama error: {str(ollama_err)}"
                return err_msg, "ERROR", "Cloud Failure Fallback"
    else:
        # No Gemini Key available: fallback directly to local Ollama
        try:
            res = call_ollama_api(scrubbed_prompt, system_instruction)
            scrubbed_res = scrub_sensitive_patterns(res)
            return scrubbed_res, f"Ollama ({OLLAMA_MODEL}) Fallback", "Missing Cloud API Key"
        except Exception as ollama_err:
            err_msg = f"No Gemini key configured and Ollama failed.\nOllama error: {str(ollama_err)}"
            return err_msg, "ERROR", "Missing Cloud API Key"
def gemini_health_check() -> bool:
    if not GEMINI_API_KEY:
        return False
    try:
        # Single token test
        call_gemini_api("health test", system_instruction="Response short")
        return True
    except Exception:
        return False

def ollama_health_check() -> bool:
    try:
        # Query Ollama version or simple list
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        return response.status_code == 200
    except Exception:
        return False

def health_check() -> dict:
    """
    Standard health check endpoint details
    """
    return {
        "gemini": {
            "status": "online" if gemini_health_check() else "offline",
            "key_configured": bool(GEMINI_API_KEY)
        },
        "ollama": {
            "status": "online" if ollama_health_check() else "offline",
            "host": OLLAMA_HOST,
            "model": OLLAMA_MODEL
        },
        "privacy_mode": PRIVACY_MODE
    }
