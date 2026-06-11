import os
import re
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv, dotenv_values
from groq import Groq

# Define explicit path to .env file in the project root
env_path = Path(__file__).resolve().parents[1] / ".env"

# Selective env loader: only override if the .env value is not empty
if env_path.exists():
    env_vars = dotenv_values(env_path)
    for k, v in env_vars.items():
        if v is not None and v.strip():
            os.environ[k] = v
        elif k not in os.environ:
            os.environ[k] = ""
else:
    load_dotenv(override=True)

# Env variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Strip quotes if they were added inside .env
if GEMINI_API_KEY.startswith('"') and GEMINI_API_KEY.endswith('"'):
    GEMINI_API_KEY = GEMINI_API_KEY[1:-1]
elif GEMINI_API_KEY.startswith("'") and GEMINI_API_KEY.endswith("'"):
    GEMINI_API_KEY = GEMINI_API_KEY[1:-1]

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if GROQ_API_KEY.startswith('"') and GROQ_API_KEY.endswith('"'):
    GROQ_API_KEY = GROQ_API_KEY[1:-1]
elif GROQ_API_KEY.startswith("'") and GROQ_API_KEY.endswith("'"):
    GROQ_API_KEY = GROQ_API_KEY[1:-1]

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Initialize Groq client
groq_client = None
if GROQ_API_KEY.strip():
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[LLM_MANAGER] Error initializing Groq client: {e}")

# Logging setup for diagnostic tracking
print("=========================================================")
print(f"[LLM_MANAGER] Module imported from: {__file__}")
print(f"[LLM_MANAGER] Project root .env path resolved: {env_path}")
print(f"[LLM_MANAGER] Loaded .env file exists on disk: {env_path.exists()}")

# Verify environment variables
print("GEMINI_API_KEY loaded:", bool(os.getenv("GEMINI_API_KEY")))
print("GEMINI_MODEL:", os.getenv("GEMINI_MODEL"))
print("GROQ_API_KEY loaded:", bool(os.getenv("GROQ_API_KEY")))
print("GROQ_MODEL:", os.getenv("GROQ_MODEL"))

# Startup diagnostics
print(f"Env path: {env_path}")
print(f"Gemini loaded: {'yes' if os.getenv('GEMINI_API_KEY') else 'no'}")
print(f"Groq loaded: {'yes' if os.getenv('GROQ_API_KEY') else 'no'}")
print(f"Active Gemini model: {GEMINI_MODEL}")
print(f"Active Groq model: {GROQ_MODEL}")

if GROQ_API_KEY:
    preview = f"{GROQ_API_KEY[:5]}...{GROQ_API_KEY[-4:]}" if len(GROQ_API_KEY) >= 9 else GROQ_API_KEY
    print(f"[LLM_MANAGER] GROQ_API_KEY Preview: {preview}")
else:
    print("[LLM_MANAGER] GROQ_API_KEY Status: MISSING")
print("=========================================================")


# Set privacy mode
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

def clean_error_message(error_msg: str) -> str:
    """
    Scrubs sensitive parameters (like API keys or specific URLs) from exception strings
    to prevent key leakage or raw tracebacks in the UI.
    """
    if not error_msg:
        return ""
    if GEMINI_API_KEY:
        error_msg = error_msg.replace(GEMINI_API_KEY, "[REDACTED_API_KEY]")
    if GROQ_API_KEY:
        error_msg = error_msg.replace(GROQ_API_KEY, "[REDACTED_API_KEY]")
        
    error_msg = re.sub(r'key=[a-zA-Z0-9_\-]+', 'key=[REDACTED]', error_msg)
    
    return error_msg

def call_gemini_api(prompt: str, system_instruction: str = None) -> str:
    """
    Direct REST call to Gemini API.
    Highly robust against python package dependency conflicts.
    """
    print(f"[LLM_MANAGER] [Gemini] Selected Model: {GEMINI_MODEL}")
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key is missing. Set GEMINI_API_KEY in environment or .env file.")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    contents = [{"parts": [{"text": prompt}]}]
    
    payload = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
        
    # Enforce tight timeout (12 seconds) for clean fallback behaviour
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
    print(f"[LLM_MANAGER] [Gemini] API response status code: {response.status_code}")
    response.raise_for_status()
    
    resp_data = response.json()
    text_out = resp_data["candidates"][0]["content"]["parts"][0]["text"]
    return text_out

def call_groq_api(prompt: str, system_instruction: str = None) -> str:
    """
    Call Groq API using the official SDK.
    """
    global groq_client
    print(f"[LLM_MANAGER] [Groq] Selected Model: {GROQ_MODEL}")
    if not GROQ_API_KEY:
        raise ValueError("Groq API Key is missing. Set GROQ_API_KEY in environment or .env file.")
    if not groq_client:
        groq_client = Groq(api_key=GROQ_API_KEY)
        
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    
    # Enforce tight timeout (15 seconds)
    chat_completion = groq_client.chat.completions.create(
        messages=messages,
        model=GROQ_MODEL,
        temperature=0.0,
        timeout=15.0
    )
    text_out = chat_completion.choices[0].message.content
    return text_out

def metadata_rule_engine(prompt: str, system_instruction: str = None) -> str:
    """
    A metadata-based rule engine that handles intents, table descriptions, column definitions,
    or result explanations when both Gemini and Groq are offline.
    """
    prompt_lower = prompt.lower()
    
    # 1. Intent Detection
    if "classify the user query into exactly one of these categories" in prompt_lower or "router for datamind ai" in prompt_lower:
        user_q = ""
        user_q_match = re.search(r'user question:\s*"(.*?)"', prompt, re.IGNORECASE)
        if user_q_match:
            user_q = user_q_match.group(1).lower()
        else:
            user_q_match2 = re.search(r'user question:\s*(.*?)$', prompt, re.IGNORECASE | re.MULTILINE)
            if user_q_match2:
                user_q = user_q_match2.group(1).lower()
            else:
                user_q = prompt_lower
                
        if any(kw in user_q for kw in ["health", "null", "duplicate", "outlier", "quality"]):
            return "QUALITY"
        elif any(kw in user_q for kw in ["join", "link", "relationship", "foreign key", "primary key"]):
            return "RELATIONSHIP"
        elif any(kw in user_q for kw in ["sql", "query", "select", "average", "mean", "median", "count", "sum"]):
            return "SQL"
        elif any(kw in user_q for kw in ["definition", "glossary", "term", "meaning"]):
            return "GLOSSARY"
        elif any(kw in user_q for kw in ["table", "column", "schema", "database", "exist"]):
            return "METADATA"
        else:
            return "BUSINESS"
            
    # 2. Table Overview Description
    if "generate a short, business-friendly description" in prompt_lower or "overview for postgresql table:" in prompt_lower:
        tname = "the table"
        tname_match = re.search(r'table\s+name\s*:\s*([a-zA-Z0-9_-]+)', prompt, re.IGNORECASE)
        if tname_match:
            tname = tname_match.group(1)
        else:
            tname_match2 = re.search(r'table\s*:\s*([a-zA-Z0-9_-]+)', prompt, re.IGNORECASE)
            if tname_match2:
                tname = tname_match2.group(1)
            else:
                tname_match3 = re.search(r'table\s+([a-zA-Z0-9_-]+)', prompt, re.IGNORECASE)
                if tname_match3 and tname_match3.group(1).lower() not in ["name", "description", "overview", "definition"]:
                    tname = tname_match3.group(1)
        return f"This table contains structured data records for {tname} including key indicators."
        
    # 3. Column Definition
    if "create a 5-word business definition for column:" in prompt_lower or "business definition for column:" in prompt_lower:
        cname = "attribute"
        cname_match = re.search(r"column\s*:\s*'([a-zA-Z0-9_-]+)'", prompt, re.IGNORECASE)
        if cname_match:
            cname = cname_match.group(1)
        else:
            cname_match2 = re.search(r"column\s*:\s*([a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
            if cname_match2:
                cname = cname_match2.group(1)
            else:
                cname_match3 = re.search(r"column\s+([a-zA-Z0-9_-]+)", prompt, re.IGNORECASE)
                if cname_match3 and cname_match3.group(1).lower() not in ["name", "definition"]:
                    cname = cname_match3.group(1)
        return f"Business term representing {cname} identifier."
        
    # 4. Explain SQL/Query Results
    if "explain this query result setup:" in prompt_lower or "calculated query result:" in prompt_lower:
        columns_list = []
        cols_match = re.search(r'columns:\s*(.*?)$', prompt, re.IGNORECASE | re.MULTILINE)
        if cols_match:
            columns_list = cols_match.group(1).strip()
            
        return f"This result set summarizes database fields under columns {columns_list} generated via SQL query."
        
    # 5. SQL generation
    if "you are a sql architect" in prompt_lower:
        tname = "table"
        tname_match = re.search(r'table\s*:\s*([a-zA-Z0-9_-]+)', prompt, re.IGNORECASE)
        if not tname_match:
            tname_match = re.search(r'table\s+name\s*:\s*([a-zA-Z0-9_-]+)', prompt, re.IGNORECASE)
        if tname_match:
            tname = tname_match.group(1)
        return f"SELECT * FROM `{tname}` LIMIT 10;"
        
    # 6. General/Reasoning Synthesis Fallback
    if "currently selected dataset schema context:" in prompt_lower or "rag_context_summary" in prompt_lower or "you are the datamind ai intelligence copilot" in prompt_lower:
        # Extract user question from prompt
        user_q = ""
        user_q_match = re.search(r'user question:\s*(.*?)$', prompt, re.IGNORECASE | re.MULTILINE)
        if user_q_match:
            user_q = user_q_match.group(1).lower()
        else:
            user_q = prompt_lower

        # Extract active dataset name
        ds_name = "active dataset"
        ds_match = re.search(r'active dataset:\s*([a-zA-Z0-9_-]+)', prompt, re.IGNORECASE)
        if ds_match:
            ds_name = ds_match.group(1)

        # Parse tables and columns from schema context
        tables_found = []
        current_table = None
        current_cols = []
        
        for line in prompt.split("\n"):
            line_strip = line.strip()
            if line_strip.lower().startswith("table:"):
                tbl_match = re.search(r'table:\s*([a-zA-Z0-9_-]+)', line_strip, re.IGNORECASE)
                if tbl_match:
                    if current_table:
                        tables_found.append((current_table, current_cols))
                    current_table = tbl_match.group(1)
                    current_cols = []
            elif line_strip.startswith("- ") and current_table:
                col_match = re.search(r'^-\s*([a-zA-Z0-9_-]+)\s*\((.*?)\):\s*(.*?)(?:\s*\||$)', line_strip)
                if col_match:
                    cname = col_match.group(1)
                    ctype = col_match.group(2)
                    cdesc = col_match.group(3).strip()
                    current_cols.append((cname, ctype, cdesc))
                else:
                    col_match_simple = re.search(r'^-\s*([a-zA-Z0-9_-]+)', line_strip)
                    if col_match_simple:
                        current_cols.append((col_match_simple.group(1), "TEXT", ""))
                        
        if current_table:
            tables_found.append((current_table, current_cols))

        # 6a. Check if query is about columns/fields
        if any(kw in user_q for kw in ["column", "field", "attribute", "explain each", "list columns"]):
            if tables_found:
                res_lines = []
                for tbl, cols in tables_found:
                    res_lines.append(f"Here are the columns and data types for the table **{tbl}**:")
                    for cname, ctype, cdesc in cols:
                        desc_str = f" — *{cdesc}*" if cdesc else ""
                        res_lines.append(f"- **{cname}** ({ctype}){desc_str}")
                    res_lines.append("")
                return "\n".join(res_lines).strip()

        # 6b. Check if query is about quality/health
        if any(kw in user_q for kw in ["health", "quality", "null", "duplicate", "outlier", "anomaly"]):
            mcp_match = re.search(r'mcp tool call results:\s*(.*?)(?:previous chat context:|$)', prompt, re.IGNORECASE | re.DOTALL)
            if mcp_match:
                try:
                    tool_json = json.loads(mcp_match.group(1).strip())
                    if "quality_scan" in tool_json and "metrics" in tool_json["quality_scan"]:
                        metrics = tool_json["quality_scan"]["metrics"]
                        res_lines = ["Based on the data quality center scan:"]
                        for m in metrics:
                            res_lines.append(f"- Table **{m.get('table_name')}**:")
                            res_lines.append(f"  - Health Score: **{m.get('health_score')}%**")
                            res_lines.append(f"  - Missing Values: {m.get('missing_count')}")
                            res_lines.append(f"  - Duplicate Rows: {m.get('duplicate_count')}")
                            res_lines.append(f"  - Outliers: {m.get('outlier_count')}")
                            res_lines.append(f"  - Format Mismatches: {m.get('invalid_format_count')}")
                        return "\n".join(res_lines)
                except Exception:
                    pass

        # 6c. Check if RAG context has hits and extract them
        rag_hits = []
        rag_section = False
        for line in prompt.split("\n"):
            line_lower = line.lower()
            if "relevant catalog schema context (rag):" in line_lower:
                rag_section = True
                continue
            if "mcp tool call results:" in line_lower or "previous chat context:" in line_lower:
                rag_section = False
            if rag_section:
                line_strip = line.strip()
                if line_strip and not line_strip.startswith("---") and not line_strip.lower().startswith("relevant catalog"):
                    rag_hits.append(line_strip)
                    
        if len(rag_hits) > 0 and not any("empty" in r.lower() for r in rag_hits):
            res_lines = ["Based on the database catalog:"]
            for hit in rag_hits[:4]:
                res_lines.append(f"- {hit}")
            return "\n".join(res_lines)

        # 6d. Default Schema summary listing
        if tables_found:
            res_lines = [f"The active dataset '{ds_name}' contains the following catalog tables:"]
            for tbl, cols in tables_found:
                cols_str = ", ".join([c[0] for c in cols[:6]])
                if len(cols) > 6:
                    cols_str += "..."
                res_lines.append(f"- **{tbl}** ({len(cols)} columns: {cols_str})")
            res_lines.append("\nFeel free to ask specific questions about data quality or columns, or use the SQL Copilot to query this dataset.")
            return "\n".join(res_lines)
            
    return "No relevant information found in the selected dataset."

def test_groq_connection():
    """
    Diagnostic function to test Groq API connectivity.
    """
    print("=========================================================")
    print("[LLM_MANAGER] [Groq Test Connection] Starting standalone test...")
    if not GROQ_API_KEY:
        print("[LLM_MANAGER] [Groq Test Connection] Aborted: GROQ_API_KEY is missing/empty.")
        print("=========================================================")
        return
    try:
        status = groq_health_check()
        print(f"[LLM_MANAGER] [Groq Test Connection] Health status: {'Success' if status else 'Failed'}")
    except Exception as e:
        print(f"[LLM_MANAGER] [Groq Test Connection] Exception: {str(e)}")
    print("=========================================================")

def generate_response(prompt: str, system_instruction: str = None):
    # Apply PII scrubbing to prompt input
    scrubbed_prompt = scrub_sensitive_patterns(prompt)
    
    # Enforce strict anti-hallucination policy
    anti_hallucination = (
        "You are a data catalog assistant.\n"
        "You may only answer using:\n"
        "1. Retrieved dataset metadata\n"
        "2. Retrieved schema\n"
        "3. Retrieved SQL results\n"
        "4. Retrieved vector context\n\n"
        "If the answer cannot be verified from retrieved context:\n"
        "Respond:\n"
        "\"I cannot find verified information for that question in the selected dataset.\"\n\n"
        "Never fabricate.\n"
        "Never estimate.\n"
        "Never invent statistics.\n"
        "Never assume column values."
    )
    
    if system_instruction:
        combined_instruction = f"{system_instruction}\n\n{anti_hallucination}"
    else:
        combined_instruction = anti_hallucination
        
    print(f"[LLM_MANAGER] Initiating generate_response...")
    
    # Check if Privacy Mode is enabled. If true, fail Gemini instantly and start with Groq
    gemini_failed_privacy = False
    if get_privacy_mode():
        print("[LLM_MANAGER] Privacy Mode enabled. Skipping Gemini.")
        gemini_failed_privacy = True
        
    # Try Gemini first (if privacy mode is false)
    if not gemini_failed_privacy:
        start_time = time.time()
        try:
            print(f"[LLM_MANAGER] Attempting Primary Model: {GEMINI_MODEL}")
            res = call_gemini_api(scrubbed_prompt, combined_instruction)
            latency_sec = time.time() - start_time
            scrubbed_res = scrub_sensitive_patterns(res)
            return scrubbed_res, "Gemini", GEMINI_MODEL, "Primary Cloud API", latency_sec
        except Exception as gemini_err:
            gemini_latency = time.time() - start_time
            import traceback
            gemini_err_clean = clean_error_message(str(gemini_err))
            print(f"[LLM_MANAGER] FAILOVER EVENT: Gemini API call failed: {gemini_err_clean}. Falling back to Groq.")
            print(f"[LLM_MANAGER] Gemini traceback detail:")
            traceback.print_exc()
            
            # Log failover event to SQLite database
            try:
                from backend.database import add_failover_event
                add_failover_event(
                    primary_model=GEMINI_MODEL,
                    fallback_model=GROQ_MODEL,
                    error_message=gemini_err_clean,
                    latency_ms=int(gemini_latency * 1000)
                )
            except Exception as e:
                print(f"[LLM_MANAGER] Error writing failover event to DB: {e}")
                
    else:
        gemini_err_clean = "Privacy Mode enabled: Gemini bypassed."
        gemini_latency = 0.0

    # Fallback to Groq
    start_time_groq = time.time()
    try:
        print(f"[LLM_MANAGER] Attempting Fallback Model: {GROQ_MODEL}")
        res = call_groq_api(scrubbed_prompt, combined_instruction)
        latency_sec = time.time() - start_time_groq
        scrubbed_res = scrub_sensitive_patterns(res)
        return scrubbed_res, "Groq", GROQ_MODEL, "Cloud Failure Fallback", latency_sec
    except Exception as groq_err:
        groq_latency = time.time() - start_time_groq
        groq_err_clean = clean_error_message(str(groq_err))
        print(f"[LLM_MANAGER] Groq fallback API call failed: {groq_err_clean}. Falling back to Metadata Rule Engine.")
        print(f"[LLM_MANAGER] Groq traceback detail:")
        traceback.print_exc()
        
        # Log second failover event to SQLite database if Groq is unavailable
        try:
            from backend.database import add_failover_event
            add_failover_event(
                primary_model=GROQ_MODEL,
                fallback_model="Metadata Rule Engine",
                error_message=groq_err_clean,
                latency_ms=int(groq_latency * 1000)
            )
        except Exception as e:
            print(f"[LLM_MANAGER] Error writing Groq failover event to DB: {e}")
            
        # Fallback to Metadata Rule Engine
        start_time_rules = time.time()
        try:
            print(f"[LLM_MANAGER] Attempting Metadata Rule Engine Fallback")
            res = metadata_rule_engine(scrubbed_prompt, combined_instruction)
            latency_sec = time.time() - start_time_rules
            scrubbed_res = scrub_sensitive_patterns(res)
            return scrubbed_res, "Rule Engine", "Metadata Rule Engine", "Rule Engine Fallback", latency_sec
        except Exception as rule_err:
            rule_err_clean = clean_error_message(str(rule_err))
            print(f"[LLM_MANAGER] Rule Engine failed: {rule_err_clean}")
            err_msg = f"All fallback systems failed.\nGemini error: {gemini_err_clean}\nGroq error: {groq_err_clean}\nRule Engine error: {rule_err_clean}"
            return err_msg, "ERROR", "ERROR", "Cloud Failure Fallback", 0.0

def gemini_health_check() -> bool:
    if not GEMINI_API_KEY:
        return False
    try:
        call_gemini_api("health test", system_instruction="Response short")
        return True
    except Exception:
        return False

def groq_health_check() -> bool:
    global groq_client
    if not GROQ_API_KEY:
        print("[LLM_MANAGER] [Groq Health Check] Key is missing.")
        return False
    try:
        if not groq_client:
            groq_client = Groq(api_key=GROQ_API_KEY)
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": "hello"}],
            model=GROQ_MODEL,
            max_tokens=5,
            timeout=5.0
        )
        return True
    except Exception as e:
        print(f"[LLM_MANAGER] [Groq Health Check] Exception: {str(e)}")
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
        "groq": {
            "status": "online" if groq_health_check() else "offline",
            "key_configured": bool(GROQ_API_KEY)
        },
        "privacy_mode": PRIVACY_MODE
    }

# Run standalone connection test on import if a key is configured
if GROQ_API_KEY:
    test_groq_connection()
