import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "transactions.db")

def create():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        amount REAL,
        payment_method TEXT,
        status TEXT,
        timestamp TEXT
    )
    """)
    
    # Populate sample rows
    samples = [
        (201, 250.50, "CREDIT_CARD", "SUCCESS", "2026-06-01T14:30:00"),
        (202, 120.00, "UPI", "SUCCESS", "2026-06-02T10:15:00"),
        (203, 45.00, "NET_BANKING", "PENDING", "2026-06-03T18:45:00"),
        (204, 85.00, "CREDIT_CARD", "FAILED", "2026-06-04T09:00:00")
    ]
    
    cursor.executemany(
        "INSERT INTO transactions (order_id, amount, payment_method, status, timestamp) VALUES (?, ?, ?, ?, ?)",
        samples
    )
    
    conn.commit()
    conn.close()
    print(f"Sample SQLite DB created successfully at: {db_path}")

if __name__ == "__main__":
    create()
