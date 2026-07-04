import sqlite3
import time
import re
import pandas as pd
from typing import Tuple, List, Dict, Any, Optional
from pathlib import Path
from utils.common import logger

class DBManager:
    @staticmethod
    def get_connection(db_path: str | Path) -> sqlite3.Connection:
        """Establishes and returns a connection to the SQLite database."""
        conn = sqlite3.connect(db_path)
        # Enable foreign key support
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @staticmethod
    def execute_query(sql_query: str, db_path: str | Path) -> Tuple[pd.DataFrame, float, Optional[str]]:
        """
        Executes a SQL query on the specified database.
        Returns:
            - DataFrame of results
            - Execution time in seconds
            - Error message (if any, otherwise None)
        """
        start_time = time.perf_counter()
        logger.info(f"Executing SQL query on database {db_path}:\n{sql_query}")
        
        try:
            conn = DBManager.get_connection(db_path)
            # Execute query and load into Pandas
            df = pd.read_sql_query(sql_query, conn)
            conn.close()
            
            elapsed_time = time.perf_counter() - start_time
            logger.info(f"Query executed successfully in {elapsed_time:.4f}s. Rows returned: {len(df)}")
            return df, elapsed_time, None
            
        except Exception as e:
            elapsed_time = time.perf_counter() - start_time
            err_msg = str(e)
            logger.error(f"SQL execution error after {elapsed_time:.4f}s: {err_msg}")
            return pd.DataFrame(), elapsed_time, err_msg

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Sanitizes names for tables or columns to make them SQLite compatible."""
        # Lowercase, replace spaces/hyphens with underscores, remove non-alphanumeric except underscores
        clean = name.strip().lower()
        clean = re.sub(r'[\s\-]+', '_', clean)
        clean = re.sub(r'[^\w]', '', clean)
        # Ensure it starts with a letter or underscore
        if clean and not clean[0].isalpha() and clean[0] != '_':
            clean = '_' + clean
        return clean or "table"

    @classmethod
    def import_csv_to_sqlite(cls, csv_path: str | Path, db_path: str | Path, table_name: Optional[str] = None) -> str:
        """
        Imports a CSV file into the SQLite database.
        Returns the created table name.
        """
        csv_path = Path(csv_path)
        if not table_name:
            table_name = cls.sanitize_name(csv_path.stem)
        else:
            table_name = cls.sanitize_name(table_name)
            
        logger.info(f"Importing CSV {csv_path} to table '{table_name}' in SQLite database {db_path}...")
        
        df = pd.read_csv(csv_path)
        # Sanitize column names
        df.columns = [cls.sanitize_name(col) for col in df.columns]
        
        conn = cls.get_connection(db_path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()
        
        logger.info(f"Successfully imported {len(df)} rows into table '{table_name}'.")
        return table_name

    @classmethod
    def import_excel_to_sqlite(cls, excel_path: str | Path, db_path: str | Path) -> List[str]:
        """
        Imports all sheets of an Excel file into the SQLite database.
        Returns a list of created table names.
        """
        excel_path = Path(excel_path)
        logger.info(f"Importing Excel {excel_path} to SQLite database {db_path}...")
        
        excel_file = pd.ExcelFile(excel_path)
        created_tables = []
        
        conn = cls.get_connection(db_path)
        for sheet_name in excel_file.sheet_names:
            table_name = cls.sanitize_name(sheet_name)
            df = excel_file.parse(sheet_name)
            # Sanitize column names
            df.columns = [cls.sanitize_name(col) for col in df.columns]
            
            df.to_sql(table_name, conn, if_exists="replace", index=False)
            created_tables.append(table_name)
            logger.info(f"Successfully imported sheet '{sheet_name}' as table '{table_name}' ({len(df)} rows).")
            
        conn.close()
        return created_tables

    @staticmethod
    def get_table_names(db_path: str | Path) -> List[str]:
        """Returns a list of all user-defined tables in the SQLite database."""
        conn = DBManager.get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables
