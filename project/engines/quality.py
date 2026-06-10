import os
import re
import json
import sqlite3
import pandas as pd
import numpy as np

# Email regex
EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'
# Date regex - matches standard ISO, YYYY/MM/DD, DD-MM-YYYY, etc.
DATE_REGEX = r'^\d{4}[-/]\d{2}[-/]\d{2}(?:\s\d{2}:\d{2}:\d{2})?$|^\d{2}[-/]\d{2}[-/]\d{4}$'

def check_invalid_formats(series, col_name, data_type):
    """
    Scans a series for format violations based on column names or data types
    """
    col_lower = col_name.lower()
    invalid_count = 0
    non_null_series = series.dropna().astype(str)
    
    if len(non_null_series) == 0:
        return 0
        
    if "email" in col_lower:
        for val in non_null_series:
            if not re.match(EMAIL_REGEX, val):
                invalid_count += 1
                
    elif "date" in col_lower or data_type == "DATETIME":
        for val in non_null_series:
            if not re.match(DATE_REGEX, val):
                # Try parsing with pandas just in case
                try:
                    pd.to_datetime(val, errors='raise')
                except Exception:
                    invalid_count += 1
                    
    return invalid_count

def detect_outliers_iqr(series):
    """
    Detects outlier counts in numeric columns using the Interquartile Range (IQR) method.
    """
    # Force conversion to numeric
    numeric_series = pd.to_numeric(series, errors='coerce').dropna()
    if len(numeric_series) < 5:
        return 0
        
    q1 = numeric_series.quantile(0.25)
    q3 = numeric_series.quantile(0.75)
    iqr = q3 - q1
    
    if iqr == 0:
        return 0
        
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    outliers = numeric_series[(numeric_series < lower_bound) | (numeric_series > upper_bound)]
    return len(outliers)

def scan_table_quality(df, table_name, data_type_map=None):
    """
    Performs data quality profiling on a Pandas DataFrame.
    """
    row_count = len(df)
    if row_count == 0:
        return {
            "table_name": table_name,
            "health_score": 0.0,
            "missing_count": 0,
            "duplicate_count": 0,
            "outlier_count": 0,
            "invalid_format_count": 0,
            "details": {"error": "Table is empty"},
            "recommendations": ["Upload valid data to this table."]
        }
        
    missing_count = int(df.isna().sum().sum())
    
    # Duplicate rows check
    duplicate_count = int(df.duplicated().sum())
    
    outlier_count = 0
    invalid_format_count = 0
    
    column_details = {}
    
    for col in df.columns:
        series = df[col]
        col_type = data_type_map.get(col, "TEXT") if data_type_map else "TEXT"
        
        # Outliers for numerical
        col_outliers = 0
        if pd.api.types.is_numeric_dtype(series):
            col_outliers = detect_outliers_iqr(series)
            outlier_count += col_outliers
            
        # Format checks
        col_invalid = check_invalid_formats(series, col, col_type)
        invalid_format_count += col_invalid
        
        col_missing = int(series.isna().sum())
        
        column_details[col] = {
            "missing": col_missing,
            "missing_percentage": round((col_missing / row_count * 100), 2) if row_count > 0 else 0,
            "outliers": col_outliers,
            "invalid_formats": col_invalid
        }
        
    # Health score calculation
    # Deductions:
    # - Missing values: 0.1% deduction per missing field (max 30 points)
    # - Duplicates: 1% deduction per duplicate row percentage (max 20 points)
    # - Outliers: 0.5% deduction per outlier (max 15 points)
    # - Invalid formats: 2% deduction per invalid entry (max 15 points)
    
    missing_ratio = missing_count / (row_count * len(df.columns)) if row_count > 0 else 0
    duplicate_ratio = duplicate_count / row_count if row_count > 0 else 0
    outlier_ratio = outlier_count / (row_count * len(df.columns)) if row_count > 0 else 0
    invalid_ratio = invalid_format_count / (row_count * len(df.columns)) if row_count > 0 else 0
    
    missing_deduction = min(missing_ratio * 100 * 0.5, 30.0)
    duplicate_deduction = min(duplicate_ratio * 100 * 1.5, 20.0)
    outlier_deduction = min(outlier_ratio * 100 * 2.0, 15.0)
    invalid_deduction = min(invalid_ratio * 100 * 3.0, 15.0)
    
    health_score = 100.0 - (missing_deduction + duplicate_deduction + outlier_deduction + invalid_deduction)
    health_score = round(max(min(health_score, 100.0), 0.0), 1)
    
    # Generate business impact and recommendations
    recommendations = []
    impacts = []
    
    if duplicate_count > 0:
        recommendations.append(f"Remove duplicate rows in table '{table_name}'. Found {duplicate_count} duplicates.")
        impacts.append("Duplicate records may artificially inflate metric computations and report totals.")
        
    for col, metrics in column_details.items():
        if metrics["missing_percentage"] > 20.0:
            recommendations.append(f"Impute or investigate high null values in column '{col}' ({metrics['missing_percentage']}% null).")
            impacts.append(f"Missing attributes in '{col}' prevent complete user segment profiling.")
        if metrics["invalid_formats"] > 0:
            recommendations.append(f"Enforce validation constraints or clean '{col}' (found {metrics['invalid_formats']} invalid records).")
            impacts.append(f"Mismatched formats in '{col}' cause failures in downstream database loads or scheduling APIs.")
        if metrics["outliers"] > 5:
            recommendations.append(f"Review numeric outliers in '{col}' ({metrics['outliers']} records fall outside 1.5*IQR).")
            impacts.append(f"Extreme outliers in '{col}' distort average aggregate analyses and machine learning predictions.")
            
    if not recommendations:
        recommendations.append("No critical issues found. Maintain current data load protocols.")
        impacts.append("Operational analytics present no immediate business warning flags.")
        
    return {
        "table_name": table_name,
        "health_score": health_score,
        "missing_count": missing_count,
        "duplicate_count": duplicate_count,
        "outlier_count": outlier_count,
        "invalid_format_count": invalid_format_count,
        "details": column_details,
        "business_impact": impacts,
        "recommendations": recommendations
    }

def scan_orphan_records(ds_type, ds_path, relationships):
    """
    Scans child tables for foreign keys that don't exist in the parent table.
    Enforces local scanning.
    """
    orphans_report = []
    if not ds_path or not os.path.exists(ds_path) or not relationships:
        return orphans_report
        
    for rel in relationships:
        src_tbl = rel["source_table"]
        src_col = rel["source_column"] # Parent table PK
        tgt_tbl = rel["target_table"]
        tgt_col = rel["target_column"] # Child table FK
        
        # Load tables
        parent_set = set()
        child_series = []
        
        try:
            if ds_type.upper() == 'SQLITE':
                conn = sqlite3.connect(ds_path)
                try:
                    df_parent = pd.read_sql_query(f"SELECT DISTINCT `{src_col}` FROM `{src_tbl}`", conn)
                    df_child = pd.read_sql_query(f"SELECT `{tgt_col}` FROM `{tgt_tbl}`", conn)
                    parent_set = set(df_parent[src_col].dropna().tolist())
                    child_series = df_child[tgt_col].dropna().tolist()
                finally:
                    conn.close()
                    
            elif ds_type.upper() == 'CSV' and os.path.isdir(ds_path):
                parent_path = os.path.join(ds_path, f"{src_tbl}.csv")
                child_path = os.path.join(ds_path, f"{tgt_tbl}.csv")
                if os.path.exists(parent_path) and os.path.exists(child_path):
                    df_parent = pd.read_csv(parent_path, usecols=[src_col])
                    df_child = pd.read_csv(child_path, usecols=[tgt_col])
                    parent_set = set(df_parent[src_col].dropna().unique().tolist())
                    child_series = df_child[tgt_col].dropna().tolist()
                    
            elif ds_type.upper() == 'JSON' and os.path.isdir(ds_path):
                parent_path = os.path.join(ds_path, f"{src_tbl}.json")
                child_path = os.path.join(ds_path, f"{tgt_tbl}.json")
                if os.path.exists(parent_path) and os.path.exists(child_path):
                    df_parent = pd.json_normalize(json.load(open(parent_path)))
                    df_child = pd.json_normalize(json.load(open(child_path)))
                    if src_col in df_parent.columns and tgt_col in df_child.columns:
                        parent_set = set(df_parent[src_col].dropna().unique().tolist())
                        child_series = df_child[tgt_col].dropna().tolist()
                        
            if len(child_series) > 0 and len(parent_set) > 0:
                orphans = [val for val in child_series if val not in parent_set]
                orphan_count = len(orphans)
                orphan_pct = round((orphan_count / len(child_series) * 100), 2)
                
                if orphan_count > 0:
                    orphans_report.append({
                        "parent_table": src_tbl,
                        "parent_column": src_col,
                        "child_table": tgt_tbl,
                        "child_column": tgt_col,
                        "orphan_count": orphan_count,
                        "orphan_percentage": orphan_pct,
                        "sample_orphans": list(set(orphans))[:5]
                    })
        except Exception as e:
            # Silence exception for robustness, return what we have
            pass
            
    return orphans_report
