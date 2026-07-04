import re
import pandas as pd
from typing import Tuple, Optional, List
from config import Config
from llm.gemini_client import GeminiClient
from utils.common import logger

class SQLValidator:
    # Compile regex to match forbidden keywords at word boundaries
    FORBIDDEN_PATTERN = re.compile(
        r"\b(insert|update|delete|drop|alter|create|replace|truncate|pragma|attach|detach|grant|revoke|union\s+all\s+select\s+sqlite_version)\b",
        re.IGNORECASE
    )

    @classmethod
    def validate_and_format_query(cls, sql_query: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validates the SQL query against safety guidelines:
        - Must be a SELECT query.
        - Must not contain modifying keywords (INSERT, DROP, etc.).
        - Limits the number of returned rows.
        
        Returns:
            - is_valid: bool
            - formatted_query: str
            - error_message: Optional[str]
        """
        # 1. Clean SQL code (strip comments and whitespace)
        cleaned = cls.remove_comments(sql_query).strip()
        
        if not cleaned:
            return False, sql_query, "SQL query is empty."

        # 2. Enforce strictly SELECT statements
        if not cleaned.lower().startswith("select") and not cleaned.lower().startswith("with"):
            return False, sql_query, "Dangerous Query Blocked: Only SELECT queries are permitted."

        # 3. Check for modifying or hazardous keywords
        matches = cls.FORBIDDEN_PATTERN.findall(cleaned)
        if matches:
            forbidden_words = ", ".join(set(matches))
            return False, sql_query, f"Dangerous Query Blocked: Found forbidden operations ({forbidden_words})."

        # 4. Enforce Row Limits (Safety Cap)
        # Search for a LIMIT clause in the query
        has_limit = re.search(r"\blimit\s+\d+", cleaned, re.IGNORECASE)
        if not has_limit:
            # Check if query ends with a semicolon and strip it to append LIMIT
            if cleaned.endswith(";"):
                cleaned = cleaned[:-1].strip()
            cleaned = f"{cleaned} LIMIT {Config.MAX_ROW_LIMIT};"
            logger.info(f"Validator appended safety limit: {Config.MAX_ROW_LIMIT}")
        else:
            # Parse existing limit to make sure it doesn't exceed Config.MAX_ROW_LIMIT
            limit_val_match = re.search(r"\blimit\s+(\d+)", cleaned, re.IGNORECASE)
            if limit_val_match:
                limit_val = int(limit_val_match.group(1))
                if limit_val > Config.MAX_ROW_LIMIT:
                    # Replace large limit with Config.MAX_ROW_LIMIT
                    cleaned = re.sub(r"\blimit\s+\d+", f"LIMIT {Config.MAX_ROW_LIMIT}", cleaned, flags=re.IGNORECASE)
                    logger.info(f"Validator capped user-defined limit to {Config.MAX_ROW_LIMIT}")

        return True, cleaned, None

    @staticmethod
    def remove_comments(sql: str) -> str:
        """Removes single-line and multi-line comments from SQL text."""
        # Remove single-line comments starting with --
        sql = re.sub(r"--.*?\n", "\n", sql)
        # Remove multi-line comments /* ... */
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        return sql


class SQLGenerator:
    def __init__(self, gemini_client: GeminiClient):
        self.client = gemini_client

    def _clean_sql_output(self, raw_llm_output: str) -> str:
        """Removes markdown code blocks (```sql ... ```) from LLM output."""
        cleaned = raw_llm_output.strip()
        # Remove standard markdown wrap
        cleaned = re.sub(r"^```sql\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()

    def generate_sql(self, question: str, retrieved_schemas: List[str], api_key: Optional[str] = None) -> Tuple[str, bool, Optional[str]]:
        """
        Generates and validates an SQL query for a question given schema context.
        Returns:
            - Generated SQL query string
            - Success status (bool)
            - Error message (if any)
        """
        schema_context = "\n\n".join(retrieved_schemas)
        
        system_instruction = (
            "You are an expert SQLite developer. Your job is to output a single, correct, and optimized SQLite SELECT statement "
            "based on the user's question and the provided table schemas. "
            "IMPORTANT RULES:\n"
            "1. ONLY generate SELECT queries. Never generate modifying actions (INSERT, UPDATE, DELETE, CREATE, DROP, ALTER).\n"
            "2. Return ONLY the raw SQL code. DO NOT wrap the code in markdown (like ```sql ... ```). DO NOT explain the query. "
            "DO NOT write comments. Output nothing but the query itself.\n"
            "3. Use only the tables, column names, and relationships provided in the schema context. Do not assume or invent schemas.\n"
            "4. Match string values using LIKE (case-insensitive) where appropriate for user queries.\n"
            "5. To aggregate dates (by month/year), use SQLite's strftime function (e.g. strftime('%Y-%m', order_date)).\n"
            "6. Prioritize readability for non-SQL business users: When joining tables (e.g., sales and products), always select human-readable descriptive columns (like product_name, customer_name) instead of raw numeric IDs (like product_id, customer_id) in the final SELECT fields, unless the user explicitly requests the ID."
        )
        
        prompt = f"""DATABASE SCHEMA CONTEXT:
{schema_context}

USER QUESTION:
{question}

Please generate the SQL query matching this question. Follow the rules strictly and return ONLY raw SQL."""

        try:
            raw_output = self.client.generate_text(
                prompt=prompt,
                system_instruction=system_instruction,
                api_key=api_key
            )
            
            sql_query = self._clean_sql_output(raw_output)
            logger.info(f"Raw SQL generated by LLM:\n{sql_query}")
            
            # Run query through Validator
            is_valid, validated_sql, val_error = SQLValidator.validate_and_format_query(sql_query)
            if not is_valid:
                logger.warning(f"SQL validation failed: {val_error}")
                return sql_query, False, val_error
                
            return validated_sql, True, None
            
        except Exception as e:
            logger.error(f"Failed to generate SQL: {e}")
            return "", False, str(e)

    def self_heal_sql(
        self, 
        bad_sql: str, 
        error_msg: str, 
        retrieved_schemas: List[str], 
        api_key: Optional[str] = None
    ) -> Tuple[str, bool, Optional[str]]:
        """
        Self-healing flow: Takes a query that failed execution along with the SQLite error message,
        and prompts Gemini to rewrite it correctly.
        """
        schema_context = "\n\n".join(retrieved_schemas)
        
        system_instruction = (
            "You are an expert SQLite developer. You are correcting a query that failed to execute. "
            "Return ONLY the corrected SQLite SELECT statement. "
            "DO NOT wrap in markdown blocks, DO NOT explain, DO NOT comment. Output ONLY corrected SQL."
        )
        
        prompt = f"""DATABASE SCHEMA CONTEXT:
{schema_context}

FAILED SQL QUERY:
{bad_sql}

SQLITE EXECUTION ERROR:
{error_msg}

Please correct the query above to fix the error while still answering the user's intent. Return ONLY the corrected SQL query."""

        try:
            logger.info(f"Initiating SQL Self-Healing. Error: {error_msg}")
            raw_output = self.client.generate_text(
                prompt=prompt,
                system_instruction=system_instruction,
                api_key=api_key
            )
            
            corrected_sql = self._clean_sql_output(raw_output)
            logger.info(f"Self-healed SQL generated:\n{corrected_sql}")
            
            # Validate healed SQL
            is_valid, validated_sql, val_error = SQLValidator.validate_and_format_query(corrected_sql)
            if not is_valid:
                return corrected_sql, False, val_error
                
            return validated_sql, True, None
            
        except Exception as e:
            logger.error(f"SQL Self-Healing failed: {e}")
            return bad_sql, False, f"Self-healing failed: {str(e)}"

    def generate_insight_summary(
        self, 
        question: str, 
        sql: str, 
        df: pd.DataFrame, 
        api_key: Optional[str] = None
    ) -> str:
        """
        Reads query execution results (dataframe) and generates a plain-English,
        bulleted business insight summary.
        """
        if df.empty:
            return "No data retrieved for this question."
            
        # Format a summary of the dataframe (don't send huge dataframes to save context tokens)
        df_len = len(df)
        if df_len > 15:
            # Send sample and structural outline
            df_str = f"DataFrame has {df_len} rows total. Here is the top sample:\n" + df.head(10).to_string()
        else:
            df_str = df.to_string()
            
        system_instruction = (
            "You are an expert business intelligence analyst. Your task is to explain the results of a database query "
            "to a business manager in simple, natural English. "
            "RULES:\n"
            "1. Output exactly 2 to 4 concise bullet points summarizing key findings (e.g. top performing categories, trends, counts).\n"
            "2. Focus entirely on business insights. Do not discuss SQL tables, schemas, Joins, or database structures.\n"
            "3. Be specific, quoting figures and names from the data where applicable.\n"
            "4. Keep explanations short, clear, and professional."
        )
        
        prompt = f"""USER QUESTION: {question}
EXECUTED SQL: {sql}

QUERY EXECUTION DATA:
{df_str}

Please generate the business insight bullets."""

        try:
            logger.info("Generating Business Insights summary via Gemini...")
            summary = self.client.generate_text(
                prompt=prompt,
                system_instruction=system_instruction,
                api_key=api_key,
                temperature=0.3
            )
            return summary
        except Exception as e:
            logger.error(f"Failed to generate insight summary: {e}")
            return "Unable to generate business summary at this time."
