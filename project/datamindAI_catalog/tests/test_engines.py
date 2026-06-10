import os
import pytest
import pandas as pd
import numpy as np
import json
from engines.data_loader import is_column_pii, mask_sensitive_value, generate_df_metadata
from engines.quality import detect_outliers_iqr, scan_table_quality
from engines.relationship import discover_relationships

def test_pii_detection_and_masking():
    # Test PII Column Flagging
    assert is_column_pii("customer_email") is True
    assert is_column_pii("phone_number") is True
    assert is_column_pii("created_at") is False
    
    # Test Contact Masking
    masked_email = mask_sensitive_value("john.doe@gmail.com", "customer_email")
    assert masked_email.startswith("j")
    assert "@" in masked_email
    assert "john.doe" not in masked_email
    
    # Test Numeric card Masking
    masked_card = mask_sensitive_value("1234567812345678", "credit_card")
    assert masked_card == "****-****-****-5678"

def test_outlier_detection_iqr():
    # Symmetric data - no outliers
    clean_series = pd.Series([10, 12, 11, 13, 12, 11, 12, 10, 11, 12])
    assert detect_outliers_iqr(clean_series) == 0
    
    # Data with a clear outlier
    dirty_series = pd.Series([10, 12, 11, 13, 12, 11, 12, 10, 11, 120]) # 120 is an outlier
    assert detect_outliers_iqr(dirty_series) == 1

def test_data_quality_scoring():
    # Perfect Table
    df_clean = pd.DataFrame({
        "id": range(1, 10),
        "val": ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    })
    q_clean = scan_table_quality(df_clean, "clean_tbl")
    assert q_clean["health_score"] == 100.0
    assert q_clean["missing_count"] == 0
    assert q_clean["duplicate_count"] == 0
    
    # Missing values and Duplicates
    df_dirty = pd.DataFrame({
        "id": [1, 2, 2, 4, 5, 6, 7, 8, 9], # duplicate key '2'
        "val": ["A", None, None, "D", "E", "F", "G", "H", "I"] # exactly 2 missing, indices 1 & 2 are identical rows
    })
    q_dirty = scan_table_quality(df_dirty, "dirty_tbl")
    assert q_dirty["health_score"] < 100.0
    assert q_dirty["missing_count"] == 2
    assert q_dirty["duplicate_count"] == 1

def test_relationship_discovery_logic():
    # Mock schemas matching on naming
    tables_meta = [
        {
            "table_name": "customers",
            "columns": [
                {"column_name": "customer_id", "data_type": "INTEGER", "distinct_count": 50, "null_count": 0, "health_metrics": {"uniqueness_ratio": 1.0}},
                {"column_name": "name", "data_type": "TEXT", "distinct_count": 50, "null_count": 0, "health_metrics": {"uniqueness_ratio": 1.0}}
            ]
        },
        {
            "table_name": "orders",
            "columns": [
                {"column_name": "order_id", "data_type": "INTEGER", "distinct_count": 100, "null_count": 0, "health_metrics": {"uniqueness_ratio": 1.0}},
                {"column_name": "customer_id", "data_type": "INTEGER", "distinct_count": 30, "null_count": 5, "health_metrics": {"uniqueness_ratio": 0.3}}
            ]
        }
    ]
    
    # Discover relationships based on schemas (with no files)
    rels = discover_relationships("CSV", None, tables_meta)
    
    assert len(rels) == 1
    assert rels[0]["source_table"] == "customers"
    assert rels[0]["source_column"] == "customer_id"
    assert rels[0]["target_table"] == "orders"
    assert rels[0]["target_column"] == "customer_id"
    assert rels[0]["confidence"] > 0.5
    assert rels[0]["type"] == "one-to-many"
