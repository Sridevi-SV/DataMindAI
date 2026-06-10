# AI Assisted Development Documentation (AI_USAGE.md)

This log describes the collaborative development process between the AI and the developer to construct the DataMind AI catalog platform.

## 1. What the AI Assisted With
- **Architectural Scaffolding**: Designed the concurrent FastAPI backend + Streamlit frontend execution flow.
- **Data Quality Logic**: Formulated mathematical calculations for health score penalties based on null rates, duplicates, outliers (IQR), and format mismatches.
- **MCP Server Modeling**: Built a lightweight JSON-RPC MCP registry class standard mimicking the core Model Context Protocol definitions without requiring complex third-party system configurations.
- **RAG Configuration**: Set up local in-process indexing through ChromaDB, leveraging `sentence-transformers` for offline vector storage.
- **SQL Parser & Validator**: Developed regular expression validations to extract table names and cross-reference them against internal SQLite schema catalogs, preventing erroneous execution paths.

## 2. What the AI Got Wrong (and Lessons Learned)
- **SQLite Syntax**: In the initial sample creation script, the AI generated the column statement as `order_id INTEGER NOT None` instead of SQL standard `NOT NULL`. This resulted in a database execution error which was resolved by swapping the constraints.
- **ChromaDB Client Instantiations**: The default ChromaDB code occasionally tried loading settings using legacy APIs. We standardized on `chromadb.PersistentClient(path=...)` to ensure forward compatibility with Chroma 0.4+.
- **JSON Normalization assumptions**: When flattening arrays inside custom nested JSON files, a simple pandas normalize could lose primary attributes. We added explicit checking for lists inside dictionaries and used target flattening structures.

## 3. Best Prompts Used During Development

### Column Profiling Definition
> "Create a 5-word business definition for column: '{cname}' in table '{tname}'. Data Type: {ctype}. Only output the definition."
*Why it worked*: Strict token restrictions prevented long-winded technical jargon and forced clean enterprise phrasing.

### SQL Parsing Validation
> "Write a regex-based Python parser that extracts referenced table names from a SELECT query while ignoring comments and text strings."
*Why it worked*: It produced a modular, self-contained function that we directly integrated as a validation gate in our SQL Copilot engine.
