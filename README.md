# Voice-to-SQL Business Intelligence Dashboard

An AI-powered Business Intelligence (BI) dashboard that allows users to interact with and query business databases using natural language voice recordings or text queries. The system automatically transcribes spoken audio, extracts relevant database schema context using Retrieval-Augmented Generation (RAG), writes validated SQL SELECT queries, executes them on a local SQLite instance, and visualizes the results on an interactive Plotly dashboard accompanied by plain-English business summaries.

---

## Architecture Diagram

This diagram displays the flow of data through the system from user input to dashboard display:

```text
       User Question (Voice / Text)
                │
                ▼
       ┌──────────────────┐
       │  Speech-to-Text  │ (Gemini Multimodal Transcription / Whisper Fallback)
       └────────┬─────────┘
                │
                ▼
      [Question (Plain Text)]
                │
                ▼
       ┌──────────────────┐
       │  RAG Engine      │ (Query matches in ChromaDB vector store)
       └────────┬─────────┘
                │
                ▼
      [Retrieved Schema Tables]
                │
                ▼
       ┌──────────────────┐
       │  Gemini SQL Gen  │ (Translate text + schema context to SQLite query)
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │  SQL Validator   │ (Enforces SELECT-only, blocks destructive actions)
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │   SQLite DB      │ (Executes SQL query)
       └────────┬─────────┘
                │
                ▼
       ┌────────┴─────────┐
       │ Gemini Summarize │ (Generates plain-English business insights)
       └────────┬─────────┘
                │
                ▼
       ┌──────────────────┐
       │ Plotly Engine    │ (Auto-selects charts and displays dashboard)
       └──────────────────┘
```

---

## Workflow Diagram

This diagram explains the startup indexing and execution pipeline:

```text
  [Setup/Upload Phase]
  Database File (Demo DB or Uploaded CSV/Excel/SQLite)
         │
         ▼
  Introspect DB Schema (Extract Tables, Column Types, PKs, FKs, Sample Rows)
         │
         ▼
  Create Textual Schema Metadata Documents
         │
         ▼
  Index Schema Documents in ChromaDB (Using local embeddings / Gemini Fallback)

  -------------------------------------------------------------------------

  [Query Execution Phase]
  User Input (Speech -> Gemini Audio Transcription OR Text Input)
         │
         ▼
  Query ChromaDB with Question (Retrieve top-matching Table Metadata)
         │
         ▼
  Construct Prompt (System Instruction + Retrieved Table Schemas + User Question)
         │
         ▼
  Gemini SQL Generation -> Output SQL Query
         │
         ▼
  SQL Validation Interceptor (Validate SELECT, Block DROP/DELETE, Cap Limit)
         │
         ▼
  Execute SQL on SQLite -> Return Pandas DataFrame
         │
         ├─────────────────────────────────────────┐
         ▼                                         ▼
  Analyze Data Shape                       Gemini Summarizer
         │                                         │
         ▼                                         ▼
  Auto-Select Plotly Chart                  Bullet-point Business Insights
  (Line/Bar/Pie/Scatter)                           │
         │                                         ▼
         └─────────────────┬───────────────────────┘
                           │
                           ▼
                  Streamlit UI Render
```

---

## Key Features

- **Co-equal Voice Workflow**: Input questions via browser microphone recording or file uploads (`.wav`/`.mp3`/`.m4a`).
- **Precision RAG Schema Matcher**: Introspects databases (including dynamic data types, constraints, and sample records) and stores them in a ChromaDB vector store.
- **SQL Validator & Guardrails**: Sanitizes LLM outputs at word-boundaries, permitting only read-only `SELECT` statements, blocking harmful commands (`DROP`, `DELETE`, etc.), and enforcing a configurable row cap (`MAX_ROW_LIMIT`).
- **AI Self-Healing Queries**: If a generated query fails SQLite execution, the traceback error is fed back to Gemini to automatically correct syntax or schema assumptions.
- **Automated Visualization Heuristics**: Analyzes the datatypes and rows of query result dataframes to automatically render the best Plotly chart (Line, Bar, Pie, Scatter, or Table).
- **Dual-Prompt Pipeline**: Incorporates distinct prompts for SQL query generation and natural-language business summary insights.
- **Dynamic Database Uploader**: Support for SQLite databases, CSV files, and Excel sheets. It handles automatic SQLite table generation, column sanitization, and data type inference.
- **Production-Ready Logging**: Logs all transaction times, user queries, generated SQL codes, and execution statuses to `logs/app.log`.
- **Smoke-Testing Suite**: Includes an interactive UI and CLI test script (`tests/run_eval.py`) running a catalog of 15 queries to smoke-test translation accuracy.

---

## Tech Stack

- **Core**: Python
- **Interface**: Streamlit
- **AI Provider**: Google Gemini API (`gemini-1.5-flash` for generation & transcription)
- **Vector Database**: ChromaDB
- **Embeddings**: Local HuggingFace sentence-transformers (`all-MiniLM-L6-v2`) with automatic Gemini API fallback (`text-embedding-004`)
- **Query Database**: SQLite
- **Plotting**: Plotly Express
- **Data Engineering**: Pandas

---

## Folder Structure

```
voice_to_sql_dashboard/
├── .env                     # Local API keys and cap settings
├── .gitignore               # Ignored local files (cache, db files, keys)
├── requirements.txt         # Pinned packages
├── app.py                   # Streamlit Frontend application
├── config.py                # App Configuration & secrets loader
├── README.md                # Documentation and setup guides
│
├── database/
│   ├── db_manager.py        # SQLite interfaces, query executors, CSV imports
│   └── demo_db.py           # Seed script for the built-in database
│
├── rag/
│   ├── schema_extractor.py  # SQLite introspection helper
│   └── vector_store.py      # ChromaDB client wrapping & indexing manager
│
├── llm/
│   ├── gemini_client.py     # Gemini client initialization and audio transcriber
│   └── sql_generator.py     # SQL Prompt, Validator, Self-Healer, and Summarizer
│
├── services/
│   ├── speech_service.py    # Speech-to-text wrapper
│   └── viz_service.py       # Heuristic Plotly chart generator
│
├── utils/
│   └── common.py            # Logging utility and handler setup
│
├── tests/
│   ├── eval_queries.json    # Evaluation queries smoke test catalog
│   └── run_eval.py          # Command line pipeline evaluation script
│
├── uploads/
│   └── .gitkeep             # Directory placeholder for uploads
└── logs/
    └── app.log              # Query execution log file
```

---

## Installation & Setup

### 1. Clone the Project & Navigate
```bash
git clone <repository-url>
cd voice_to_sql_dashboard
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure API Credentials
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=AIzaSyYourGeminiApiKeyHere
MAX_ROW_LIMIT=100
```

---

## Running the Project

### Local Launch
Initialize the Streamlit web dashboard:
```bash
streamlit run app.py
```

### Running Command-Line Pipeline Evaluation
To test the translation pipeline against the 15-question evaluation suite:
```bash
python -m tests.run_eval --api-key YOUR_GEMINI_API_KEY
```

---

## RAG & Prompt Engineering Design

### 1. Schema Introspection Document
For each table, `SchemaExtractor` creates a metadata summary:
```text
TABLE: customers
COLUMNS:
  - customer_id (INTEGER) (PRIMARY KEY)
  - first_name (TEXT) (NOT NULL)
  - email (TEXT)
RELATIONSHIPS:
  - None
SAMPLE DATA:
  Row 1: {'customer_id': 1, 'first_name': 'Mary', 'email': 'mary.smith1@example-business.com'}
```
This summary is vectorized and stored in ChromaDB.

### 2. Prompts

#### SQL Generation Prompt
- **System Instructions**: Defines rules for returning ONLY a SELECT query, matching strings with `LIKE`, using SQLite `strftime` for date aggregations, and prohibiting data-modifying queries.
- **Retrieval Context**: retrieved schemas from ChromaDB are injected to limit the search space.

#### SQL Self-Healing Prompt
- **Trigger**: Fired when SQLite execution fails.
- **Input**: The failing query + the SQLite error traceback.
- **Goal**: Re-write the query avoiding the syntax/relationship error.

#### Insight Summarizer Prompt
- **Role**: Business BI Analyst.
- **Goal**: Translates Pandas DataFrame output data structures into 3-4 bullet-point summaries in plain English, citing specific names and figures.

---

## Deployment Guide (Streamlit Community Cloud)

To deploy the dashboard:
1. Push your project folder to a public GitHub repository. Ensure `.env`, local SQLite files `database/*.db`, logs, and `chroma_db/` cache directories are excluded by `.gitignore`.
2. Connect your GitHub account to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create a new App, select the repository, branch, and specify `app.py` as the entry file.
4. **Important**: Go to the App Settings -> **Secrets** panel. Input your Gemini API key in the secrets textbox:
   ```toml
   GEMINI_API_KEY = "AIzaSyYourGeminiApiKeyHere"
   ```
5. Deploy! Streamlit Cloud automatically spins up the server, downloads dependencies, detects the secrets key, seeds the demo database, indexes the tables in ChromaDB, and renders the dashboard.

---

## License
Distributed under the MIT License. See `LICENSE` for more details.
