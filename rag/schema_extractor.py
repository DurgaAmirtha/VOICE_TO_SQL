import sqlite3
import pandas as pd
from typing import Dict, Any, List
from pathlib import Path
from database.db_manager import DBManager
from utils.common import logger

class SchemaExtractor:
    @staticmethod
    def get_table_details(db_path: str | Path, table_name: str) -> Dict[str, Any]:
        """
        Retrieves detailed schema info for a specific table:
        columns, data types, primary keys, foreign keys, and sample data.
        """
        conn = DBManager.get_connection(db_path)
        cursor = conn.cursor()
        
        # 1. Get Columns and Types
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns_raw = cursor.fetchall()
        # Columns format: (cid, name, type, notnull, dflt_value, pk)
        columns = []
        primary_keys = []
        for col in columns_raw:
            col_info = {
                "name": col[1],
                "type": col[2],
                "notnull": bool(col[3]),
                "default_value": col[4],
                "is_pk": bool(col[5])
            }
            columns.append(col_info)
            if col[5]:
                primary_keys.append(col[1])
                
        # 2. Get Foreign Keys
        cursor.execute(f"PRAGMA foreign_key_list({table_name});")
        fkeys_raw = cursor.fetchall()
        # FKeys format: (id, seq, table, from, to, on_update, on_delete, match)
        foreign_keys = []
        for fk in fkeys_raw:
            fk_info = {
                "from": fk[3],
                "to_table": fk[2],
                "to_column": fk[4]
            }
            foreign_keys.append(fk_info)
            
        # 3. Get Sample Data (up to 3 rows)
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
        sample_rows_raw = cursor.fetchall()
        
        # Extract column names for display
        col_names = [col["name"] for col in columns]
        sample_rows = []
        for row in sample_rows_raw:
            sample_rows.append(dict(zip(col_names, row)))
            
        conn.close()
        
        return {
            "table_name": table_name,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "sample_rows": sample_rows
        }

    @classmethod
    def get_database_schema_summary(cls, db_path: str | Path) -> Dict[str, Dict[str, Any]]:
        """Extracts schema details for all tables in the database."""
        logger.info(f"Extracting schema details from database: {db_path}")
        tables = DBManager.get_table_names(db_path)
        schema_summary = {}
        for table in tables:
            schema_summary[table] = cls.get_table_details(db_path, table)
        return schema_summary

    @staticmethod
    def generate_schema_document(table_meta: Dict[str, Any]) -> str:
        """
        Converts extracted metadata for a single table into a text document
        ready to be stored in ChromaDB and fed to the LLM.
        """
        table_name = table_meta["table_name"]
        
        doc_lines = []
        doc_lines.append(f"TABLE: {table_name}")
        
        # Columns
        doc_lines.append("COLUMNS:")
        for col in table_meta["columns"]:
            pk_str = " (PRIMARY KEY)" if col["is_pk"] else ""
            notnull_str = " (NOT NULL)" if col["notnull"] else ""
            doc_lines.append(f"  - {col['name']} ({col['type']}){pk_str}{notnull_str}")
            
        # Relationships / FKs
        if table_meta["foreign_keys"]:
            doc_lines.append("RELATIONSHIPS:")
            for fk in table_meta["foreign_keys"]:
                doc_lines.append(f"  - Column '{fk['from']}' references table '{fk['to_table']}' column '{fk['to_column']}'")
                
        # Sample Data
        if table_meta["sample_rows"]:
            doc_lines.append("SAMPLE DATA:")
            for idx, row in enumerate(table_meta["sample_rows"]):
                doc_lines.append(f"  Row {idx+1}: {row}")
                
        return "\n".join(doc_lines)
