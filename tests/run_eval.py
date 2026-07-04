import os
import sys
import json
import argparse
from pathlib import Path

# Add project root to python path to ensure module loading
sys.path.append(os.getcwd())

from config import Config
from rag.vector_store import VectorStoreManager
from llm.gemini_client import GeminiClient
from llm.sql_generator import SQLGenerator
from database.db_manager import DBManager
from utils.common import logger

def run_evaluation(api_key: str):
    logger.info("Starting offline Voice-to-SQL RAG Pipeline Evaluation...")
    
    # 1. Load evaluation queries
    eval_file = Path("tests/eval_queries.json")
    if not eval_file.exists():
        print(f"Error: Evaluation queries file not found at {eval_file}")
        sys.exit(1)
        
    with open(eval_file, "r") as f:
        eval_cases = json.load(f)
        
    # 2. Re-index Demo DB to ensure Chroma index is fresh
    db_path = Config.DEMO_DB_PATH
    print(f"\n[Step 1] Indexing demo database at {db_path}...")
    VectorStoreManager.index_database_schema(db_path)
    
    # 3. Setup client and generator
    client = GeminiClient(api_key=api_key)
    generator = SQLGenerator(client)
    
    print("\n[Step 2] Processing Queries...")
    results = []
    success_count = 0
    
    for case in eval_cases:
        qid = case["id"]
        question = case["question"]
        category = case["category"]
        
        print(f"\n------------------------------------------------")
        print(f"Query #{qid} [{category}]")
        print(f"Question: '{question}'")
        
        # Retrieval
        retrieved_tables, retrieved_docs = VectorStoreManager.retrieve_relevant_schemas(
            query=question,
            db_path=db_path,
            top_n=2
        )
        
        # SQL Generation
        sql, is_generated, err_msg = generator.generate_sql(
            question=question,
            retrieved_schemas=retrieved_docs,
            api_key=api_key
        )
        
        row_count = 0
        execution_time = 0.0
        is_success = False
        exec_error = None
        
        if is_generated:
            # Execution
            df, execution_time, exec_error = DBManager.execute_query(sql, db_path)
            if exec_error is None:
                is_success = True
                row_count = len(df)
                success_count += 1
                print(f"Generated SQL: {sql}")
                print(f"Status: SUCCESS | Rows returned: {row_count} | Time: {execution_time:.4f}s")
            else:
                # Attempt self-healing
                print(f"Initial execution failed. Error: {exec_error}")
                print("Triggering Self-Healing...")
                healed_sql, healed_ok, heal_err = generator.self_heal_sql(
                    bad_sql=sql,
                    error_msg=exec_error,
                    retrieved_schemas=retrieved_docs,
                    api_key=api_key
                )
                
                if healed_ok:
                    df, execution_time, exec_error = DBManager.execute_query(healed_sql, db_path)
                    if exec_error is None:
                        is_success = True
                        row_count = len(df)
                        success_count += 1
                        sql = healed_sql
                        print(f"Healed SQL: {sql}")
                        print(f"Status: SUCCESS (HEALED) | Rows: {row_count} | Time: {execution_time:.4f}s")
                    else:
                        print(f"Healed query failed: {exec_error}")
                else:
                    print(f"Self-healing failed: {heal_err}")
        else:
            print(f"Generation failed. Error: {err_msg}")
            exec_error = err_msg

        results.append({
            "id": qid,
            "question": question,
            "sql": sql,
            "is_success": is_success,
            "row_count": row_count,
            "error": exec_error,
            "time": execution_time
        })
        
    # 4. Show Summary
    print("\n" + "="*50)
    print("EVALUATION RUN REPORT SUMMARY")
    print("="*50)
    print(f"{'ID':<3} | {'Status':<12} | {'Rows':<5} | {'Question':<50}")
    print("-"*80)
    for res in results:
        status = "SUCCESS" if res["is_success"] else "FAILED"
        print(f"{res['id']:<3} | {status:<12} | {res['row_count']:<5} | {res['question'][:50]}")
        
    accuracy = (success_count / len(eval_cases)) * 100
    print("-"*80)
    print(f"Overall Pipeline Accuracy: {success_count}/{len(eval_cases)} ({accuracy:.1f}%)")
    print("="*50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Voice-to-SQL RAG Pipeline")
    parser.add_argument(
        "--api-key", 
        type=str, 
        help="Google Gemini API key. If not provided, will read from environment/dotenv."
    )
    args = parser.parse_args()
    
    # Resolve API Key
    api_key = args.api_key or Config.GEMINI_API_KEY
    if not api_key or api_key == "your_gemini_api_key_here":
        print("Error: A valid GEMINI_API_KEY must be provided via the --api-key argument or in a .env file.")
        sys.exit(1)
        
    run_evaluation(api_key)
