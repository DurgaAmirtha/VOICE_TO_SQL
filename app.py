import streamlit as st
import pandas as pd
from pathlib import Path
import os
import time
import json

# Set page configuration
st.set_page_config(
    page_title="Voice-to-SQL Business Intelligence Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Config imports and initialization

from config import Config
from database.db_manager import DBManager
from rag.vector_store import VectorStoreManager
from llm.gemini_client import GeminiClient
from llm.sql_generator import SQLGenerator
from services.speech_service import SpeechService
from services.viz_service import VizService
from utils.common import logger

# Resolve API Key strictly from config (.env or Streamlit secrets)
api_key = Config.GEMINI_API_KEY
if api_key == "your_gemini_api_key_here":
    api_key = ""

# Initialize Session State Variables
if "api_key" not in st.session_state:
    st.session_state["api_key"] = api_key
if "db_path" not in st.session_state:
    st.session_state["db_path"] = str(Config.DEMO_DB_PATH)
if "db_mode" not in st.session_state:
    st.session_state["db_mode"] = "Built-in Demo Database"
if "query_history" not in st.session_state:
    st.session_state["query_history"] = []
if "last_query_results" not in st.session_state:
    st.session_state["last_query_results"] = None
if "rag_context" not in st.session_state:
    st.session_state["rag_context"] = None
if "generated_sql" not in st.session_state:
    st.session_state["generated_sql"] = ""
if "error_message" not in st.session_state:
    st.session_state["error_message"] = None
if "ai_insight" not in st.session_state:
    st.session_state["ai_insight"] = ""
if "transcription" not in st.session_state:
    st.session_state["transcription"] = ""

# Helper to index database in ChromaDB
def index_active_db():
    try:
        with st.spinner("Indexing database schema..."):
            VectorStoreManager.index_database_schema(st.session_state["db_path"])
            st.toast("Schema indexed successfully.")
    except Exception as e:
        st.error(f"Failed to index schema in ChromaDB: {e}")

# Startup index check (critical for ephemeral Streamlit Cloud environments)
if "db_indexed" not in st.session_state:
    st.session_state["db_indexed"] = False

if not st.session_state["db_indexed"]:
    try:
        # Check if the demo database needs seeding
        if st.session_state["db_path"] == str(Config.DEMO_DB_PATH) and not Config.DEMO_DB_PATH.exists():
            from database.demo_db import seed_demo_database
            seed_demo_database(Config.DEMO_DB_PATH)
            
        # Build local JSON schema cache and index database
        VectorStoreManager.index_database_schema(st.session_state["db_path"])
        st.session_state["db_indexed"] = True
    except Exception as startup_err:
        logger.warning(f"Startup schema indexing check failed: {startup_err}")
        st.session_state["db_indexed"] = True

# Sidebar Configuration
with st.sidebar:
    st.title("Database Configuration")
    
    # Database selection
    db_mode = st.radio(
        "Select Database Source",
        options=["Built-in Demo Database", "Upload Custom Data"],
        index=0 if st.session_state["db_mode"] == "Built-in Demo Database" else 1
    )
    st.session_state["db_mode"] = db_mode
    old_db_path = st.session_state["db_path"]
    
    if db_mode == "Built-in Demo Database":
        st.session_state["db_path"] = str(Config.DEMO_DB_PATH)
        # Check if the demo db exists, seed if not
        if not Config.DEMO_DB_PATH.exists():
            from database.demo_db import seed_demo_database
            with st.spinner("Seeding demo business database..."):
                seed_demo_database(Config.DEMO_DB_PATH)
            st.success("Demo database initialized.")
            index_active_db()
            
    else:
        st.markdown("**Upload Database File (.db), CSV, or Excel (.xlsx)**")
        uploaded_file = st.file_uploader(
            "Upload file", 
            type=["db", "csv", "xlsx"]
        )
        
        if uploaded_file is not None:
            # Save file
            temp_path = Config.UPLOADS_DIR / uploaded_file.name
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            if uploaded_file.name.endswith(".db"):
                # Direct SQLite Database
                st.session_state["db_path"] = str(temp_path)
                st.success(f"Attached database: {uploaded_file.name}")
                if st.button("Index Database Schema", width="stretch"):
                    index_active_db()
            else:
                # CSV or Excel
                target_db = Config.DATABASE_DIR / "uploaded_business.db"
                st.session_state["db_path"] = str(target_db)
                
                try:
                    if uploaded_file.name.endswith(".csv"):
                        DBManager.import_csv_to_sqlite(temp_path, target_db)
                        st.success(f"Imported CSV as table: {Path(temp_path).stem}")
                    else:
                        tables = DBManager.import_excel_to_sqlite(temp_path, target_db)
                        st.success(f"Imported Excel sheets as tables: {', '.join(tables)}")
                        
                    index_active_db()
                except Exception as ex:
                    st.error(f"Failed to parse and import file: {ex}")

    if st.session_state["db_path"] != old_db_path:
        st.session_state["db_indexed"] = False
        st.rerun()

    st.divider()
    
    # Quick Database Schema Browser (Sidebar Tree View)
    st.subheader("Active Database Schema")
    try:
        active_tables = DBManager.get_table_names(st.session_state["db_path"])
        if active_tables:
            for tbl in active_tables:
                st.markdown(f"Table: `{tbl}`")
        else:
            st.info("No tables detected in active database.")
    except Exception as e:
        st.sidebar.error(f"Could not load tables: {e}")

# Main Layout
st.title("Voice-to-SQL Business Intelligence Dashboard")
st.markdown("Execute SQL queries and extract visualization metrics from relational databases using natural language.")

# Ensure client is setup
gemini_client = GeminiClient(api_key=st.session_state["api_key"])
sql_generator = SQLGenerator(gemini_client)
speech_service = SpeechService(gemini_client)

# Define Main Application Tabs
tab_workspace, tab_inspector, tab_history = st.tabs([
    "Voice Query", 
    "Database Explorer", 
    "History"
])

# ==========================================
# TAB 1: QUERY WORKSPACE
# ==========================================
with tab_workspace:
    if not st.session_state["api_key"] and not Config.GROQ_API_KEY:
        st.warning("No API Keys configured. Please add GEMINI_API_KEY or GROQ_API_KEY to your .env file to proceed.")
    
    st.markdown("### Ask a Question")
    
    # Co-equal audio input methods: Mic vs Upload
    col_input1, col_input2 = st.columns(2)
    
    with col_input1:
        st.markdown("**Option A: Voice Input (Microphone)**")
        from streamlit_mic_recorder import mic_recorder
        audio = mic_recorder(
            start_prompt="Start Recording Microphone",
            stop_prompt="Stop and Process Audio",
            key="mic_audio_recorder"
        )
        if audio:
            try:
                with st.spinner("Transcribing recording..."):
                    transcription = speech_service.transcribe_mic_bytes(
                        audio_bytes=audio["bytes"],
                        audio_format=audio["format"],
                        api_key=st.session_state["api_key"]
                    )
                    if transcription:
                        st.session_state["transcription"] = transcription
                        st.success(f"Transcribed Text: '{transcription}'")
                    else:
                        st.warning("No speech detected.")
            except Exception as e:
                st.error(f"Transcription error: {e}")
                
    with col_input2:
        st.markdown("**Option B: Voice Input (File Upload)**")
        audio_file = st.file_uploader(
            "Upload Audio File (.wav, .mp3)", 
            type=["wav", "mp3", "m4a"]
        )
        if audio_file is not None:
            # Save file
            temp_audio_path = Config.UPLOADS_DIR / audio_file.name
            with open(temp_audio_path, "wb") as f:
                f.write(audio_file.getbuffer())
                
            if st.button("Transcribe Audio File", width="stretch"):
                try:
                    with st.spinner("Processing file..."):
                        transcription = speech_service.transcribe_audio_file(
                            temp_audio_path, 
                            api_key=st.session_state["api_key"]
                        )
                        if transcription:
                            st.session_state["transcription"] = transcription
                            st.success(f"Transcribed Text: '{transcription}'")
                        else:
                            st.warning("No speech transcribed.")
                except Exception as e:
                    st.error(f"Transcription error: {e}")
                finally:
                    if temp_audio_path.exists():
                        os.remove(temp_audio_path)

    st.markdown("**Option C: Text Input**")
    user_query = st.text_input(
        "Edit or write your question here",
        value=st.session_state["transcription"],
        placeholder="e.g., Which product generated the highest revenue?"
    )
    
    st.divider()

    # Process and Query execution
    if st.button("Run Query Analysis", type="primary", width="stretch"):
        if not st.session_state["api_key"] and not Config.GROQ_API_KEY:
            st.error("Cannot execute analysis: No API keys configured. Please add GEMINI_API_KEY or GROQ_API_KEY to your .env file and restart the application.")
        elif not user_query:
            st.error("Please provide a question first.")
        else:
            with st.spinner("Executing pipeline (RAG -> SQL Generation -> SQLite Execution)..."):
                start_pipeline_time = time.perf_counter()
                
                # 1. RAG step
                retrieved_tables, retrieved_docs = VectorStoreManager.retrieve_relevant_schemas(
                    query=user_query,
                    db_path=st.session_state["db_path"],
                    top_n=2
                )
                st.session_state["rag_context"] = retrieved_tables
                
                # 2. LLM SQL Generation
                sql, gen_ok, gen_error = sql_generator.generate_sql(
                    question=user_query,
                    retrieved_schemas=retrieved_docs,
                    api_key=st.session_state["api_key"]
                )
                
                st.session_state["generated_sql"] = sql
                
                if not gen_ok:
                    st.session_state["error_message"] = gen_error
                    st.session_state["last_query_results"] = None
                    st.session_state["ai_insight"] = ""
                else:
                    # 3. SQLite Execution
                    df, run_time, exec_error = DBManager.execute_query(sql, st.session_state["db_path"])
                    
                    if exec_error is not None:
                        # Attempt self-healing
                        logger.info("Query failed. Attempting self-healing correction silently...")
                        healed_sql, healed_ok, heal_error = sql_generator.self_heal_sql(
                            bad_sql=sql,
                            error_msg=exec_error,
                            retrieved_schemas=retrieved_docs,
                            api_key=st.session_state["api_key"]
                        )
                        
                        if healed_ok:
                            st.session_state["generated_sql"] = healed_sql
                            df, run_time, exec_error = DBManager.execute_query(healed_sql, st.session_state["db_path"])
                            
                    if exec_error is not None:
                        st.session_state["error_message"] = exec_error
                        st.session_state["last_query_results"] = None
                        st.session_state["ai_insight"] = ""
                    else:
                        st.session_state["error_message"] = None
                        st.session_state["last_query_results"] = df
                        
                        # 4. Generate Business Summary / Insights
                        insight = sql_generator.generate_insight_summary(
                            question=user_query,
                            sql=st.session_state["generated_sql"],
                            df=df,
                            api_key=st.session_state["api_key"]
                        )
                        st.session_state["ai_insight"] = insight
                
                # Save into Audit Logs History
                pipeline_elapsed = time.perf_counter() - start_pipeline_time
                status = "SUCCESS" if st.session_state["error_message"] is None else "FAILED"
                
                st.session_state["query_history"].append({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "question": user_query,
                    "sql": st.session_state["generated_sql"],
                    "status": status,
                    "execution_time": pipeline_elapsed,
                    "row_count": len(df) if st.session_state["last_query_results"] is not None else 0
                })

    # DISPLAY RESULTS
    st.markdown("### Results")
    
    if st.session_state["rag_context"]:
        st.markdown(f"**RAG Metadata Retrieval Table Matches:** " + ", ".join([f"`{t}`" for t in st.session_state["rag_context"]]))

    if st.session_state["generated_sql"]:
        with st.expander("View / Edit Generated SQL Query", expanded=False):
            # Editable SQL editor
            edited_sql = st.text_area("SQL Code", value=st.session_state["generated_sql"], height=100)
            if edited_sql != st.session_state["generated_sql"]:
                if st.button("Execute Modified Query", width="stretch"):
                    with st.spinner("Executing custom query..."):
                        is_ok, final_sql, val_err = SQLValidator.validate_and_format_query(edited_sql)
                        if not is_ok:
                            st.error(val_err)
                        else:
                            st.session_state["generated_sql"] = final_sql
                            df, run_time, exec_error = DBManager.execute_query(final_sql, st.session_state["db_path"])
                            if exec_error:
                                st.error(exec_error)
                            else:
                                st.session_state["last_query_results"] = df
                                st.success("Custom query executed successfully.")
                                st.session_state["ai_insight"] = sql_generator.generate_insight_summary(
                                    question="[Custom SQL Query]",
                                    sql=final_sql,
                                    df=df,
                                    api_key=st.session_state["api_key"]
                                )

    # Show Error details
    if st.session_state["error_message"]:
        st.error(f"Execution Error: {st.session_state['error_message']}")

    # Show Results Grid
    if st.session_state["last_query_results"] is not None:
        df_res = st.session_state["last_query_results"]
        
        # Display Metrics
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("Rows Returned", len(df_res))
        col_m2.metric("Active Database", Path(st.session_state["db_path"]).name)
        
        # Grid layout for Chart + Table
        col_plot, col_data = st.columns([3, 2])
        
        with col_plot:
            st.markdown("#### Graphical Chart")
            viz_output = VizService.generate_chart(df_res)
            if viz_output["fig"] is not None:
                st.plotly_chart(viz_output["fig"], width="stretch")
            else:
                st.info("Chart visualization is not available for this data shape.")
            st.caption(f"Reasoning: {viz_output['reason']}")
                
        with col_data:
            st.markdown("#### Data Grid")
            st.dataframe(df_res, width="stretch", height=300)
            
            # Download results CSV
            csv_data = df_res.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Results as CSV",
                data=csv_data,
                file_name="query_results.csv",
                mime="text/csv",
                width="stretch"
            )
            
        st.divider()
        
        # Display AI insight explanation
        if st.session_state["ai_insight"]:
            st.markdown("#### Business Insight Summary")
            st.info(st.session_state["ai_insight"])

# ==========================================
# TAB 2: DATABASE INSPECTOR
# ==========================================
with tab_inspector:
    st.subheader("Browse Database Records")
    try:
        tables = DBManager.get_table_names(st.session_state["db_path"])
        if not tables:
            st.warning("No tables found in active database.")
        else:
            selected_table = st.selectbox("Select table to inspect", options=tables)
            
            # Retrieve schema definition details
            from rag.schema_extractor import SchemaExtractor
            tbl_details = SchemaExtractor.get_table_details(st.session_state["db_path"], selected_table)
            
            # Columns metadata details
            st.markdown("#### Column Definitions")
            col_meta_df = pd.DataFrame(tbl_details["columns"])
            st.dataframe(col_meta_df, width="stretch", hide_index=True)
            
            # Print relationships info
            if tbl_details["foreign_keys"]:
                st.markdown("#### Foreign Key Constraints")
                for fk in tbl_details["foreign_keys"]:
                    st.write(f"Column `{fk['from']}` references table `{fk['to_table']}` column `{fk['to_column']}`")
            
            # Print row sample
            st.markdown(f"#### Table Records: `{selected_table}`")
            table_df, _, _ = DBManager.execute_query(f"SELECT * FROM {selected_table}", st.session_state["db_path"])
            st.dataframe(table_df, width="stretch")
    except Exception as e:
        st.error(f"Inspector error: {e}")

# ==========================================
# TAB 4: AUDIT LOGS
# ==========================================
with tab_history:
    st.subheader("Session Log Metrics")
    st.markdown("Execution log database queries and duration statistics.")
    
    if not st.session_state["query_history"]:
        st.info("No query logs recorded in this session.")
    else:
        history_df = pd.DataFrame(st.session_state["query_history"])
        st.dataframe(history_df.sort_index(ascending=False), width="stretch", hide_index=True)
        
        if st.button("Clear Logs", width="stretch"):
            st.session_state["query_history"] = []
            st.toast("Logs cleared.")
            st.rerun()
            
    # Tail the app.log file contents for inspection inside a collapsed expander
    try:
        if Config.LOG_FILE_PATH.exists():
            with open(Config.LOG_FILE_PATH, "r", encoding="utf-8") as lf:
                log_lines = lf.readlines()
                tail_logs = "".join(log_lines[-25:])
                with st.expander("View Developer Diagnostics & System Logs", expanded=False):
                    st.code(tail_logs, language="text")
        else:
            with st.expander("View Developer Diagnostics & System Logs", expanded=False):
                st.info("System log file is empty.")
    except Exception as le:
        st.error(f"Failed to read log file: {le}")
