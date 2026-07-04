import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, Any, Tuple, Optional, List
from utils.common import logger

class VizService:
    @staticmethod
    def inspect_dataframe(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str]]:
        """
        Analyzes a DataFrame and returns categorized columns:
        - temporal_cols: columns containing date/time information
        - numeric_cols: numeric data columns (excluding columns named like *_id or id)
        - categorical_cols: string/object columns representing labels/categories
        """
        temporal_cols = []
        numeric_cols = []
        categorical_cols = []
        
        for col in df.columns:
            # Check for temporal columns
            col_lower = col.lower()
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                temporal_cols.append(col)
                continue
                
            if "date" in col_lower or "month" in col_lower or "year" in col_lower or "quarter" in col_lower:
                # Double check if it looks parseable as dates or if it's string/int
                temporal_cols.append(col)
                continue

            # Check for numeric columns
            if pd.api.types.is_numeric_dtype(df[col]):
                # Skip ID columns for plotting
                if col_lower == "id" or col_lower.endswith("_id"):
                    categorical_cols.append(col)  # treat IDs as categories/labels if needed
                else:
                    numeric_cols.append(col)
                continue
                
            # Treat everything else as categorical
            categorical_cols.append(col)
            
        return temporal_cols, numeric_cols, categorical_cols

    @classmethod
    def generate_chart(cls, df: pd.DataFrame, title_suffix: str = "") -> Dict[str, Any]:
        """
        Heuristically determines the best chart type and builds a Plotly figure.
        Returns a dict:
            {
                "chart_type": str,
                "fig": plotly.graph_objects.Figure or None,
                "reason": str
            }
        """
        if df.empty:
            return {"chart_type": "Table", "fig": None, "reason": "No data available."}
            
        if len(df) == 1:
            return {"chart_type": "Table", "fig": None, "reason": "DataFrame has only 1 row. Table is best."}

        # Identify column types
        temporal_cols, numeric_cols, categorical_cols = cls.inspect_dataframe(df)
        logger.info(f"VizService inspection - Temporal: {temporal_cols}, Numeric: {numeric_cols}, Categorical: {categorical_cols}")

        fig = None
        chart_type = "Table"
        reason = "A standard tabular view is best suited for this dataset structure."
        
        # Professional color palette
        color_sequence = px.colors.qualitative.Prism

        # Heuristic 1: Time Series Trend (Temporal + Numeric)
        if temporal_cols and numeric_cols:
            x_col = temporal_cols[0]
            y_col = numeric_cols[0]
            chart_type = "Line"
            
            # Sort by date before plotting to keep lines connected sequentially
            try:
                df_sorted = df.copy()
                df_sorted[x_col] = pd.to_datetime(df_sorted[x_col], errors='coerce')
                df_sorted = df_sorted.dropna(subset=[x_col]).sort_values(x_col)
            except:
                df_sorted = df
                
            fig = px.line(
                df_sorted, 
                x=x_col, 
                y=y_col, 
                
                color_discrete_sequence=color_sequence,
                markers=True
            )
            reason = f"Line chart chosen because '{x_col}' represents date/time intervals showing trends in '{y_col}'."

        # Heuristic 2: Category Breakdown (Categorical + Numeric)
        elif categorical_cols and numeric_cols:
            cat_col = categorical_cols[0]
            val_col = numeric_cols[0]
            unique_cats = df[cat_col].nunique()
            
            # If categories are small, a Pie Chart is very clean
            if 1 < unique_cats <= 5:
                chart_type = "Pie"
                fig = px.pie(
                    df, 
                    names=cat_col, 
                    values=val_col, 
                    
                    color_discrete_sequence=color_sequence
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                reason = f"Pie chart chosen to display percentage share breakdown of '{val_col}' across '{cat_col}' categories."
            else:
                chart_type = "Bar"
                # If too many categories, horizontal bar is easier to read
                if unique_cats > 10:
                    fig = px.bar(
                        df.sort_values(by=val_col, ascending=True), 
                        x=val_col, 
                        y=cat_col, 
                        orientation='h',
                        
                        color_discrete_sequence=color_sequence
                    )
                    reason = f"Horizontal Bar chart selected to make numerous category labels along '{cat_col}' easier to read."
                else:
                    fig = px.bar(
                        df.sort_values(by=val_col, ascending=False), 
                        x=cat_col, 
                        y=val_col, 
                        
                        color_discrete_sequence=color_sequence
                    )
                    reason = f"Vertical Bar chart selected to compare values of '{val_col}' across different '{cat_col}' options."

        # Heuristic 3: Numeric Correlation (Multiple Numeric Columns)
        elif len(numeric_cols) >= 2:
            x_col = numeric_cols[0]
            y_col = numeric_cols[1]
            chart_type = "Scatter"
            
            # If we also have a category, color by it
            color_col = categorical_cols[0] if categorical_cols else None
            
            fig = px.scatter(
                df, 
                x=x_col, 
                y=y_col, 
                color=color_col,
                
                color_discrete_sequence=color_sequence
            )
            reason = f"Scatter plot generated to analyze correlation and distribution between numeric values '{x_col}' and '{y_col}'."

        # Final Formatting adjustments for Plotly Figures
        if fig is not None:
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter, system-ui", color="#E4E4E7", size=11),
                legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
                margin=dict(l=10, r=10, t=15, b=10),
            )
            # Add grid lines for line and bar chart axes matching dark theme
            if chart_type in ["Line", "Bar", "Scatter"]:
                fig.update_xaxes(showgrid=True, gridcolor="#27272A", linecolor="#3F3F46")
                fig.update_yaxes(showgrid=True, gridcolor="#27272A", linecolor="#3F3F46")

        return {
            "chart_type": chart_type,
            "fig": fig,
            "reason": reason
        }
