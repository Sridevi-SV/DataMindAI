DataMindAI
Agentic AI-Powered Data Catalog & Metadata Intelligence Platform

DataMindAI is an enterprise-ready AI-powered metadata intelligence platform designed to automate data discovery, schema understanding, quality analysis, and conversational analytics.

It ingests structured data sources such as CSV, JSON, SQLite, and PostgreSQL databases, builds a searchable data catalog, identifies relationships between datasets, evaluates data quality, and enables users to interact with their data using an intelligent AI Copilot.

The system combines FastAPI, Streamlit, LangChain, LangGraph, Gemini, Ollama, Vector Search, and Agentic AI workflows to provide a secure and intelligent data management experience.

```
System Architecture

                          User
                           |
                           v
                    Streamlit Frontend
                           |
                           v
                    FastAPI Backend
                           |
          --------------------------------
          |              |               |
          v              v               v
   Data Ingestion    AI Agent       Metadata Engine
          |              |               |
          |              |               |
     CSV / JSON      LangGraph       Schema Analysis
     SQLite / DB     LangChain       Relationship Mapping
          |              |
          |              |
          v              v
      Vector Database    LLM Layer
                          |
                ---------------------
                |                   |
             Gemini             Ollama
          (Cloud Model)      (Local Model)
```
**Key Features**
Data Ingestion Pipeline
Upload and process CSV, JSON, SQLite, and PostgreSQL datasets.
Automated ingestion progress tracking.
Dataset indexing and metadata generation.
Automatic Schema Discovery
Extracts tables, columns, data types, constraints, and metadata.
Generates a searchable catalog for all connected datasets.
JSON Auto-Flattening
Handles complex nested JSON structures.
Converts nested fields into dot-notation paths for easier analysis.

**Relationship Discovery Engine**
Detects relationships between tables.
Calculates join confidence using:
Column name similarity.
Value overlap analysis.
Cardinality matching.

**Data Quality Analysis**
Evaluates:
Missing values and null percentage.
Duplicate records.
Data format mismatches.
Numeric outliers using IQR.
Orphaned records.

**AI Copilot & Text-to-SQL**
Ask questions about datasets using natural language.
AI agent determines intent and selects appropriate tools.
Generates SQL queries from user questions.
Validates generated SQL against the schema before execution.

**Enterprise Privacy & Security**
Privacy Mode
Allows complete local execution using Ollama and Llama 3.
Prevents sensitive data from being sent to external APIs.
PII Protection

**Automatically detects and masks:**
Email addresses.
Phone numbers.
Financial identifiers.
Sensitive personal information.

**Agent Monitoring & Tracing**
Visualizes AI agent execution flow:

Intent Detection.
Planning.
Tool Selection.
RAG Context Retrieval.
Response Validation.

**Technology Stack**
**Backend**
Python
FastAPI
LangChain
LangGraph
**Frontend**
Streamlit
**AI & LLM**
Google Gemini
Ollama
Llama 3
**Data Processing**
Pandas
NumPy
SQLite
PostgreSQL
**Search & Intelligence**
Vector Embeddings
RAG (Retrieval-Augmented Generation)
**Testing**
Pytest

```
Project Structure
DataMindAI/
│
├── backend/              # FastAPI APIs and business logic
├── frontend/             # Streamlit user interface
├── agent/                # Agent workflow and orchestration
├── mcp_tools/            # AI tools used by the agent
├── ingestion/            # Dataset processing pipeline
├── metadata/             # Schema extraction and profiling
├── vector_store/         # Semantic search and embeddings
├── tests/                # Automated test cases
├── sample_data/          # Example datasets
├── run.py                # Starts backend and frontend
├── requirements.txt      # Dependencies
└── README.md

```

**Installation Guide**
Prerequisites
Python 3.10+
Git
(Optional) Ollama with Llama 3 installed

```
Install Ollama model:
ollama run llama3
```
**Clone Repository**
```
git clone <repository-url>
cd DataMindAI
```

**Create Virtual Environment**
```
Windows:

python -m venv venv
venv\Scripts\activate

Linux/macOS:

python3 -m venv venv
source venv/bin/activate

```

**Install Dependencies**
```
pip install -r requirements.txt
```

**Environment Configuration**
```
Create a .env file:

GEMINI_API_KEY=your_google_gemini_api_key

OLLAMA_HOST=http://localhost:11434

PRIVACY_MODE=false
```

**Running the Application**
```
Start both FastAPI and Streamlit:

python run.py

Access:

FastAPI Backend
http://127.0.0.1:8000

Health Check:

http://127.0.0.1:8000/health
Streamlit Frontend
http://localhost:8501
```

**Running Test Cases**
```
Execute automated tests:

pytest tests/
```

**Example Workflow**
```
Upload CSV, JSON, SQLite, or PostgreSQL datasets.
Generate the metadata catalog.
Explore tables, columns, and relationships.
Analyze data quality reports.
Ask questions using the AI Copilot.
Generate and validate SQL queries.
Enable privacy mode for local Ollama processing.
Monitor agent reasoning and tool execution.
```

**Contributors**

Team PromptPioneers
Shanmathy
Sridevi
Raga Shruthi
Daisy Panimariyal










