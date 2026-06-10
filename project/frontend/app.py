import os
import sys

# Standardize path routing for Streamlit multi-directory assets
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import time
import json
import requests
import sqlite3
import streamlit as st
import pandas as pd
import networkx as nx
# pyrefly: ignore [missing-import]
import matplotlib.pyplot as plt
from dotenv import load_dotenv

from frontend.styling import apply_custom_style, draw_header, render_premium_card, render_progress_item
from backend.database import get_db_connection, add_agent_log, get_glossary_terms
from backend.mcp_server import mcp_server
from engines.sql_copilot import validate_sql_against_schema
from ai.agent_loop import run_agent_loop, memory
from ai.llm_manager import health_check, set_privacy_mode, get_privacy_mode

load_dotenv()

# API Configuration
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# Streamlit Page Setup
st.set_page_config(
    page_title="DataMind AI - Data Catalog & Intelligence Copilot",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply premium visual stylesheet
apply_custom_style()

# Session State Initialization
if "selected_dataset_id" not in st.session_state:
    st.session_state["selected_dataset_id"] = None
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# Fetch active datasets
def fetch_datasets():
    try:
        res = requests.get(f"{BACKEND_URL}/datasets", timeout=3)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    
    # Fallback to direct DB read
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM datasets ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []

datasets = fetch_datasets()
dataset_names = [d["name"] for d in datasets]

# ----------------- SIDEBAR NAVIGATION -----------------
st.sidebar.markdown("""
    <div style="text-align: center; margin-bottom: 2rem;">
        <h2 style="margin: 0; color: #FFFFFF; font-size: 1.6rem; font-family: Outfit;">🧬 DataMind AI</h2>
        <p style="color: #64748B; font-size: 0.8rem; margin: 0.2rem 0 0 0;">Intelligence Data Copilot</p>
    </div>
""", unsafe_allow_html=True)

# Select dataset in sidebar
if datasets:
    ds_options = {d["id"]: f"{d['name']} ({d['type']})" for d in datasets}
    selected_ds_id = st.sidebar.selectbox(
        "Active Catalog Scope",
        options=list(ds_options.keys()),
        format_func=lambda x: ds_options[x]
    )
    st.session_state["selected_dataset_id"] = selected_ds_id
else:
    st.sidebar.info("No active datasets cataloged. Upload a dataset to begin.")
    st.session_state["selected_dataset_id"] = None

st.sidebar.markdown("<hr style='border-color: #1E293B;' />", unsafe_allow_html=True)

pages = [
    "📊 Dashboard",
    "📁 Catalog Explorer",
    "🔗 Relationship Explorer",
    "🛡️ Data Quality Center",
    "💬 AI Copilot",
    "💻 SQL Copilot",
    "📖 Business Glossary",
    "🔒 Security Center",
    "🩺 Agent Monitor",
    "⚙️ Settings"
]

selected_page = st.sidebar.radio("Navigation Menu", pages)

# ----------------- PAGE 1: DASHBOARD -----------------
if selected_page == "📊 Dashboard":
    draw_header("Enterprise Dashboard", "Overview of structural intelligence across registered catalogs")
    
    ds_id = st.session_state["selected_dataset_id"]
    if not ds_id:
        st.warning("Please upload a data source in Settings to populate the dashboard metrics.")
    else:
        # Load dataset statistics
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Overall Stats
            cursor.execute("SELECT COUNT(*) FROM datasets")
            total_datasets = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM tables WHERE dataset_id = ?", (ds_id,))
            total_tables = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM columns c JOIN tables t ON c.table_id = t.id WHERE t.dataset_id = ?", (ds_id,))
            total_columns = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM relationships WHERE dataset_id = ?", (ds_id,))
            total_relationships = cursor.fetchone()[0]
            
            cursor.execute("SELECT AVG(health_score) FROM quality_metrics WHERE dataset_id = ?", (ds_id,))
            health_score_row = cursor.fetchone()
            health_score = round(health_score_row[0], 1) if health_score_row[0] is not None else 100.0
            
            cursor.execute("SELECT COUNT(*) FROM agent_logs")
            ai_queries = cursor.fetchone()[0]
            
            # Coverage: percentage of columns having custom descriptions
            cursor.execute(
                """SELECT COUNT(*) FROM columns c 
                   JOIN tables t ON c.table_id = t.id 
                   WHERE t.dataset_id = ? AND c.description IS NOT NULL AND c.description != ''""",
                (ds_id,)
            )
            described_cols = cursor.fetchone()[0]
            coverage = round((described_cols / total_columns * 100), 1) if total_columns > 0 else 0.0
            
        except Exception as e:
            st.error(f"Error fetching catalog dashboard stats: {str(e)}")
            total_datasets, total_tables, total_columns, total_relationships = 0, 0, 0, 0
            health_score, ai_queries, coverage = 100.0, 0, 0.0
            
        # Draw KPIs Row
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_premium_card("Total Datasets", f"{total_datasets}", "Data sources active", "📂")
        with c2:
            render_premium_card("Total Tables", f"{total_tables}", f"Mapped schemas", "📊")
        with c3:
            render_premium_card("Total Columns", f"{total_columns}", "Profiled attributes", "📋")
        with c4:
            render_premium_card("Relationships Found", f"{total_relationships}", "Foreign-key pairs", "🔗")
            
        st.markdown("<br/>", unsafe_allow_html=True)
        
        c5, c6, c7, c8 = st.columns(4)
        with c5:
            # Color health indicator
            icon = "🟢"
            if health_score < 70: icon = "🔴"
            elif health_score < 90: icon = "🟡"
            render_premium_card("Health Score", f"{health_score}%", f"Overall data quality {icon}", "🛡️")
        with c6:
            render_premium_card("AI Queries Handled", f"{ai_queries}", "Natural language calls", "💬")
        with c7:
            render_premium_card("Catalog Coverage", f"{coverage}%", "Descriptions generated", "🧬")
        with c8:
            render_premium_card("Business Domains", "4", "Sales, Finance, Ops, CRM", "🏦")
            
        st.markdown("<br/><h4>Catalog Distribution</h4>", unsafe_allow_html=True)
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            # Table size profiling
            try:
                cursor.execute("SELECT name, row_count FROM tables WHERE dataset_id = ? ORDER BY row_count DESC", (ds_id,))
                rows = cursor.fetchall()
                if rows:
                    chart_df = pd.DataFrame(rows, columns=["Table Name", "Row Count"])
                    st.bar_chart(chart_df.set_index("Table Name"))
                else:
                    st.info("No row profiles cataloged.")
            except Exception:
                pass
                
        with col_chart2:
            # Quality distribution per table
            try:
                cursor.execute("SELECT table_name, health_score FROM quality_metrics WHERE dataset_id = ?", (ds_id,))
                rows = cursor.fetchall()
                if rows:
                    chart_df = pd.DataFrame(rows, columns=["Table Name", "Health Score"])
                    st.area_chart(chart_df.set_index("Table Name"))
                else:
                    st.info("No data health metric indexes cataloged.")
            except Exception:
                pass

# ----------------- PAGE 2: CATALOG EXPLORER -----------------
elif selected_page == "📁 Catalog Explorer":
    draw_header("Catalog Explorer", "Drill down into structured metadata tables, data types, and PII status")
    
    ds_id = st.session_state["selected_dataset_id"]
    if not ds_id:
        st.warning("Please upload a dataset first.")
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT id, name, description, row_count FROM tables WHERE dataset_id = ?", (ds_id,))
            tables = [dict(row) for row in cursor.fetchall()]
            
            if not tables:
                st.info("No tables discovered in this dataset catalog.")
            else:
                table_names = [t["name"] for t in tables]
                selected_t = st.selectbox("Explore Database Table", table_names)
                
                # Load selected table details
                table_info = next(t for t in tables if t["name"] == selected_t)
                st.markdown(f"**Description:** *{table_info['description']}* | **Estimated Row Count:** `{table_info['row_count']}`")
                
                cursor.execute("SELECT * FROM columns WHERE table_id = ?", (table_info["id"],))
                cols = [dict(row) for row in cursor.fetchall()]
                
                # Format to premium table list
                tbl_data = []
                for c in cols:
                    samples = json.loads(c["sample_values_json"]) if c.get("sample_values_json") else []
                    sample_str = ", ".join([str(s) for s in samples[:3]])
                    
                    pii_tag = "🔴 SENSITIVE" if c["is_pii"] == 1 else "🟢 PUBLIC"
                    tbl_data.append({
                        "Column Name": c["name"],
                        "Data Type": c["data_type"],
                        "Sample Values": sample_str,
                        "Null Count": c["null_count"],
                        "Distinct Keys": c["distinct_count"],
                        "PII Status": pii_tag,
                        "Business Description": c["description"]
                    })
                    
                df_out = pd.DataFrame(tbl_data)
                st.dataframe(df_out, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error exploring catalog: {str(e)}")
        finally:
            conn.close()

# ----------------- PAGE 3: RELATIONSHIP EXPLORER -----------------
elif selected_page == "🔗 Relationship Explorer":
    draw_header("Relationship Explorer", "Detected schema linkages, join suggestions, and connection confidence index")
    
    ds_id = st.session_state["selected_dataset_id"]
    if not ds_id:
        st.warning("Please upload a dataset first.")
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM relationships WHERE dataset_id = ?", (ds_id,))
            rels = [dict(row) for row in cursor.fetchall()]
            
            if not rels:
                st.info("No foreign-key relationships detected. Use standard schema naming patterns like 'customer_id' to enable links.")
            else:
                st.markdown("#### Primary Join Recommendations")
                
                # Format relationships
                rel_data = []
                for r in rels:
                    details = json.loads(r["details_json"]) if r.get("details_json") else {}
                    rel_data.append({
                        "Source Asset (PK)": f"{r['source_table']}.{r['source_column']}",
                        "Target Asset (FK)": f"{r['target_table']}.{r['target_column']}",
                        "Cardinality Shape": r["type"],
                        "Confidence Level": f"{int(r['confidence'] * 100)}%",
                        "Suggested Join SQL": details.get("join_suggestion", "N/A"),
                        "Matching Logic": details.get("reason", "")
                    })
                    
                st.dataframe(pd.DataFrame(rel_data), use_container_width=True)
                
                # Render Network Graph
                st.markdown("<br/><h4>Interactive Schema Graph</h4>", unsafe_allow_html=True)
                
                G = nx.DiGraph()
                for r in rels:
                    G.add_edge(r["source_table"], r["target_table"], label=f"{r['source_column']}->{r['target_column']}")
                    
                fig, ax = plt.subplots(figsize=(8, 4), facecolor='#F8FAFC')
                pos = nx.spring_layout(G, k=0.5, seed=42)
                
                nx.draw_networkx_nodes(G, pos, ax=ax, node_color='#2563EB', node_size=1600, alpha=0.9, edgecolors='#E2E8F0')
                nx.draw_networkx_edges(G, pos, ax=ax, edge_color='#8B5CF6', width=2, arrowsize=15, connectionstyle='arc3,rad=0.1')
                nx.draw_networkx_labels(G, pos, ax=ax, font_size=9, font_family='sans-serif', font_color='white', font_weight='bold')
                
                ax.axis('off')
                st.pyplot(fig)
                
        except Exception as e:
            st.error(f"Error compiling relationships graph: {str(e)}")
        finally:
            conn.close()

# ----------------- PAGE 4: DATA QUALITY CENTER -----------------
elif selected_page == "🛡️ Data Quality Center":
    draw_header("Data Quality Center", "Audits structural health score, invalid records, outliers, and orphaned keys")
    
    ds_id = st.session_state["selected_dataset_id"]
    if not ds_id:
        st.warning("Please upload a dataset first.")
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM quality_metrics WHERE dataset_id = ?", (ds_id,))
            metrics = [dict(row) for row in cursor.fetchall()]
            
            if not metrics:
                st.info("No quality scans completed yet.")
            else:
                # Summary card health dial
                avg_health = round(sum([m["health_score"] for m in metrics]) / len(metrics), 1)
                
                c1, c2 = st.columns([1, 3])
                with c1:
                    render_premium_card("Combined Health Score", f"{avg_health}%", "Data Quality Dial", "🩺")
                    
                with c2:
                    st.markdown("##### Actionable Recommendations")
                    recs = []
                    for m in metrics:
                        table_recs = json.loads(m["recommendations_json"]) if m.get("recommendations_json") else []
                        for tr in table_recs:
                            if "No critical issues" not in tr:
                                recs.append(f"**{m['table_name']}**: {tr}")
                                
                    if recs:
                        for r in recs[:5]:
                            st.write(f"- {r}")
                    else:
                        st.success("All tables verified healthy. Data ingestion profiles are matching schemas.")
                        
                st.markdown("<br/><h4>Detailed Quality Scan Metrics</h4>", unsafe_allow_html=True)
                metrics_tbl = []
                for m in metrics:
                    metrics_tbl.append({
                        "Table Name": m["table_name"],
                        "Health Score": f"{m['health_score']}%",
                        "Missing Attributes": m["missing_count"],
                        "Duplicate Rows": m["duplicate_count"],
                        "Numeric Outliers (IQR)": m["outlier_count"],
                        "Format Anomalies": m["invalid_format_count"]
                    })
                st.dataframe(pd.DataFrame(metrics_tbl), use_container_width=True)
                
                # Check orphan keys
                st.markdown("<h4>Orphan Key Anomalies Scan</h4>", unsafe_allow_html=True)
                cursor.execute("SELECT type, file_path FROM datasets WHERE id = ?", (ds_id,))
                ds_row = cursor.fetchone()
                cursor.execute("SELECT * FROM relationships WHERE dataset_id = ?", (ds_id,))
                rels = [dict(row) for row in cursor.fetchall()]
                
                if ds_row and rels:
                    from engines.quality import scan_orphan_records
                    orphans = scan_orphan_records(ds_row[0], ds_row[1], rels)
                    if orphans:
                        orphans_df = pd.DataFrame(orphans)
                        st.dataframe(orphans_df, use_container_width=True)
                    else:
                        st.success("No orphaned keys found. Foreign keys correspond to primary tables.")
                else:
                    st.info("No cross-table connections mapped to scan orphan records.")
                    
        except Exception as e:
            st.error(f"Error conducting quality audit: {str(e)}")
        finally:
            conn.close()

# ----------------- PAGE 5: AI COPILOT -----------------
elif selected_page == "💬 AI Copilot":
    draw_header("AI Copilot", "Ask questions about catalog structure, domains, descriptions, or query planning")
    
    ds_id = st.session_state["selected_dataset_id"]
    if not ds_id:
        st.warning("Please upload and scope a dataset schema in Settings to use the Copilot.")
    else:
        # Chat display container
        for chat in st.session_state["chat_history"]:
            with st.chat_message(chat["role"]):
                st.write(chat["content"])
                
                if chat["role"] == "assistant" and "metadata" in chat:
                    # Clean premium metrics view panel
                    meta = chat["metadata"]
                    st.markdown(
                        f"""
                        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 0.8rem; border-radius: 8px; font-size: 0.85rem; margin-top: 0.5rem;">
                            <span class="ai-meta-badge ai-badge-model">AI Model: {meta['model']}</span>
                            <span class="ai-meta-badge ai-badge-conf">Confidence Score: {int(meta['confidence']*100)}%</span>
                            <br/><span style="color: #64748B;">Reasoning Intent: {meta['intent']} ({meta['routing_reason']})</span>
                            <br/><span style="color: #64748B;">Tools Dispatched: {", ".join(meta['tools'])}</span>
                            <br/><span style="color: #64748B;">Source Scopes: {", ".join(meta['sources'])}</span>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                    
        # User prompt input
        user_query = st.chat_input("Ask about schemas, e.g. Which table has orders info?")
        if user_query:
            # Display user message
            with st.chat_message("user"):
                st.write(user_query)
            st.session_state["chat_history"].append({"role": "user", "content": user_query})
            
            # Run Agent Loop
            with st.spinner("Agent Loop executing: Intent -> Planning -> Tool calls -> Reasoning..."):
                exec_state = run_agent_loop(user_query, dataset_id=ds_id)
                
            # Display assistant response
            with st.chat_message("assistant"):
                st.write(exec_state.answer)
                st.markdown(
                    f"""
                    <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 0.8rem; border-radius: 8px; font-size: 0.85rem; margin-top: 0.5rem;">
                        <span class="ai-meta-badge ai-badge-model">AI Model: {exec_state.model_used}</span>
                        <span class="ai-meta-badge ai-badge-conf">Confidence Score: {int(exec_state.confidence_score*100)}%</span>
                        <br/><span style="color: #64748B;">Reasoning Intent: {exec_state.intent} ({exec_state.routing_reason})</span>
                        <br/><span style="color: #64748B;">Tools Dispatched: {", ".join(exec_state.selected_tools)}</span>
                        <br/><span style="color: #64748B;">Source Scopes: {", ".join(exec_state.source_tables)}</span>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
            st.session_state["chat_history"].append({
                "role": "assistant",
                "content": exec_state.answer,
                "metadata": {
                    "model": exec_state.model_used,
                    "confidence": exec_state.confidence_score,
                    "intent": exec_state.intent,
                    "routing_reason": exec_state.routing_reason,
                    "tools": exec_state.selected_tools,
                    "sources": exec_state.source_tables
                }
            })

# ----------------- PAGE 6: SQL COPILOT -----------------
elif selected_page == "💻 SQL Copilot":
    draw_header("SQL Copilot", "Generates safe, validated SQL from text, runs locally, and explains aggregations")
    
    ds_id = st.session_state["selected_dataset_id"]
    if not ds_id:
        st.warning("Please upload a dataset first.")
    else:
        nl_input = st.text_input("Enter your query in plain English:", placeholder="e.g. show tables with total counts or find Bangalore orders")
        
        if nl_input:
            with st.spinner("SQL Copilot: Generating and validating schema paths..."):
                # Call generate_sql tool
                tool_res = mcp_server.call_tool("generate_sql", {"question": nl_input, "dataset_id": ds_id})
                
            if "generated_sql" in tool_res:
                generated_sql = tool_res["generated_sql"]
                st.code(generated_sql, language="sql")
                
                # Check validation status
                if tool_res.get("is_valid"):
                    st.success("✓ SQL Validation Passed: Reference matching table and column catalog schemas.")
                    
                    if st.button("Execute SQL Query"):
                        with st.spinner("Query execution running locally..."):
                            q_out = mcp_server.call_tool("query_database", {"sql_query": generated_sql, "dataset_id": ds_id})
                            
                        if "error" in q_out:
                            st.error(q_out["error"])
                        else:
                            st.markdown("##### Query Results (Limited to 50 rows)")
                            df_res = pd.DataFrame(q_out["rows"], columns=q_out["columns"])
                            st.dataframe(df_res, use_container_width=True)
                            
                            # Auto AI Explains Results (without sending raw table contents)
                            explain_prompt = f"""
                            You are a Senior Data Analyst. Explain this query result setup:
                            SQL: {generated_sql}
                            Result Shape: {len(df_res)} rows, columns: {list(df_res.columns)}
                            Question asked: {nl_input}
                            
                            Generate a 2-sentence explanation of what this result set represents to a business manager. Do NOT mention row details.
                            """
                            with st.spinner("Formulating result explanation..."):
                                explanation, _, _ = generate_response(explain_prompt, system_instruction="Response short, direct.")
                            st.markdown(f"**AI Explanation:** {explanation}")
                else:
                    st.error(f"✗ SQL Validation Failed: {tool_res.get('validation_error')}")
                    st.info("The generated SQL did not pass safety rules or references nonexistent catalog fields.")

# ----------------- PAGE 7: BUSINESS GLOSSARY -----------------
elif selected_page == "📖 Business Glossary":
    draw_header("Business Glossary", "Unified definition, contexts, meanings, and examples of business attributes")
    
    search_q = st.text_input("Search terms catalog:", placeholder="e.g. CUSTOMER, ORDER")
    
    terms = get_glossary_terms(search_q)
    
    if not terms:
        st.info("No business glossary terms matching search criteria. Upload datasets to auto-populate terms.")
    else:
        # Create detailed cards
        for t in terms:
            st.markdown(
                f"""
                <div class="premium-card">
                    <h4 style="margin: 0; color: #2563EB;">{t['term']}</h4>
                    <p style="font-size: 0.95rem; margin: 0.5rem 0 0.2rem 0;"><strong>Technical Definition:</strong> {t['definition']}</p>
                    <p style="font-size: 0.95rem; margin: 0.2rem 0;"><strong>Business Meaning:</strong> {t['business_meaning']}</p>
                    <p style="font-size: 0.85rem; margin: 0.2rem 0; color: #475569;"><strong>Business Usage Context:</strong> {t['business_usage']}</p>
                    <span style="font-size: 0.75rem; background-color: #F1F5F9; padding: 0.2rem 0.4rem; border-radius: 4px; color: #64748B;">Example Value: {t['example_val']}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

# ----------------- PAGE 8: SECURITY CENTER -----------------
elif selected_page == "🔒 Security Center":
    draw_header("Security Center", "Manage enterprise data privacy, model access routing, and metadata scrub rules")
    
    # Check health status
    h_state = health_check()
    
    # Toggle Privacy Mode
    st.markdown("<h4>Model Routing Policies</h4>", unsafe_allow_html=True)
    priv_enabled = st.toggle("Enable Enterprise Privacy Mode", value=h_state["privacy_mode"])
    
    if priv_enabled != h_state["privacy_mode"]:
        set_privacy_mode(priv_enabled)
        st.rerun()
        
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Cloud Model Routing (Gemini)")
        if priv_enabled:
            st.markdown("🚨 **Gemini cloud routing is disabled.** All AI actions are routed locally.")
        else:
            status_color = "🟢 ONLINE" if h_state["gemini"]["status"] == "online" else "🔴 OFFLINE / UNAUTHORIZED"
            st.markdown(f"Status: **{status_color}**")
            st.markdown("Model Scope: `gemini-1.5-flash`")
            
    with c2:
        st.markdown("##### Local Sandbox Routing (Ollama)")
        status_color = "🟢 ONLINE" if h_state["ollama"]["status"] == "online" else "🔴 OFFLINE"
        st.markdown(f"Status: **{status_color}**")
        st.markdown(f"Model Scope: `{h_state['ollama']['model']}`")
        st.markdown(f"Local Endpoint: `{h_state['ollama']['host']}`")
        
    st.markdown("<br/><h4>Privacy Compliance Safeguards</h4>", unsafe_allow_html=True)
    st.info("✓ Metadata-Only Transmission Enforced: Raw dataset records are never compiled into model prompts.")
    st.info("✓ Active PII Scrubbing System: Emails, addresses, and credit cards are filtered before leaving the secure perimeter.")

# ----------------- PAGE 9: AGENT MONITOR -----------------
elif selected_page == "🩺 Agent Monitor":
    draw_header("Agent Monitor Tracing", "Audit recent executions and monitor step-by-step reasoning steps of the agent loop")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM agent_logs ORDER BY id DESC LIMIT 20")
        logs = [dict(row) for row in cursor.fetchall()]
        
        if not logs:
            st.info("No queries tracked in log catalogs yet.")
        else:
            for l in logs:
                plan = json.loads(l["plan_json"]) if l.get("plan_json") else []
                tools = json.loads(l["tools_used_json"]) if l.get("tools_used_json") else []
                context = json.loads(l["context_retrieved_json"]) if l.get("context_retrieved_json") else []
                
                with st.expander(f"Question: {l['question']} | Model: {l['model_used']} | Intent: {l['intent']}"):
                    st.markdown(f"**Latency:** `{l['latency_ms']} ms` | **Validation Check:** `{l['validation_status']}`")
                    
                    st.markdown("**Executed Steps Planning:**")
                    for p in plan:
                        st.write(f"- {p}")
                        
                    st.markdown(f"**MCP Tools Selected:** {', '.join(tools)}")
                    
                    st.markdown("**ChromaDB Vector Hits:**")
                    for ctx in context[:2]:
                        st.code(ctx, language="text")
                        
                    st.markdown(f"**Final Answer:** {l['response']}")
    except Exception as e:
        st.error(f"Error querying execution log: {str(e)}")
    finally:
        conn.close()

# ----------------- PAGE 10: SETTINGS -----------------
elif selected_page == "⚙️ Settings":
    draw_header("Application Settings", "Upload and build new metadata catalogs, check system connectivity")
    
    st.markdown("<h4>Add Data Catalog Source</h4>", unsafe_allow_html=True)
    
    # 1. File Uploader
    uploaded_file = st.file_uploader("Upload local CSV, JSON or SQLite database file:", type=["csv", "json", "db", "sqlite", "sqlite3"])
    alias_name = st.text_input("Dataset Alias (Optional):", placeholder="e.g. customers_billing")
    
    # Trigger Ingestion
    if uploaded_file is not None:
        if st.button("Generate & Index Data Catalog"):
            # Prepare files for multipart upload
            name = alias_name or os.path.splitext(uploaded_file.name)[0]
            progress_key = f"upload_{name}"
            
            # Show interactive checklist
            checklist_placeholder = st.empty()
            
            # We call the FastAPI endpoint
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {"dataset_name": name}
            
            with st.spinner("Processing file through ingestion pipeline..."):
                try:
                    # Start async poll status checker in UI loop while POST is executing
                    # (For a self-contained single-process model, we can make the API call and update logs in state)
                    # Let's hit `/upload` REST API
                    res = requests.post(f"{BACKEND_URL}/upload", files=files, data=data)
                    
                    if res.status_code == 200:
                        st.success("✓ Dataset metadata successfully cataloged, analyzed, and indexed in ChromaDB!")
                        st.rerun()
                    else:
                        st.error(f"Ingestion failed: {res.text}")
                except Exception as e:
                    # Let's show progress checklist simulation for visual wow factor if backend is not up yet
                    st.error(f"Backend Ingestion Error: {str(e)}")
                    
    st.markdown("<hr/>", unsafe_allow_html=True)
    
    # 2. PG Database connector
    st.markdown("<h4>Connect PostgreSQL Database Catalog</h4>", unsafe_allow_html=True)
    pg_alias = st.text_input("Database Name Alias:", placeholder="e.g. production_rds")
    pg_uri = st.text_input("Connection URI:", placeholder="postgresql://user:password@host:port/dbname")
    
    if st.button("Inspect PG Catalog"):
        if pg_alias and pg_uri:
            with st.spinner("Querying PG schema dictionary..."):
                try:
                    res = requests.post(f"{BACKEND_URL}/connect-postgres", json={"name": pg_alias, "connection_uri": pg_uri})
                    if res.status_code == 200:
                        st.success("PostgreSQL database catalog successfully indexed.")
                        st.rerun()
                    else:
                        st.error(f"Connection failed: {res.text}")
                except Exception as e:
                    st.error(f"Connection URI request error: {str(e)}")
        else:
            st.warning("Please specify database alias and complete Postgres URI link.")
