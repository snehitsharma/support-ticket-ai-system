import os
import sqlite3
import pandas as pd

DATA_PATH = "data/support_tickets.csv"
DB_PATH = "tickets.db"
TABLE_NAME = "support_tickets"


def extract(path: str = DATA_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Expected ticket data at '{path}'. "
            f"Place the CSV file there before starting the app."
        )
    df = pd.read_csv(path)
    return df

def transform(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["created_at"] = pd.to_datetime(df["created_at"], format="%Y-%m-%d %H:%M", errors="coerce")
    df["response_time_hrs"] = pd.to_numeric(df["response_time_hrs"], errors="coerce")
    df["resolution_time_hrs"] = pd.to_numeric(df["resolution_time_hrs"], errors="coerce")
    df["customer_rating"] = pd.to_numeric(df["customer_rating"], errors="coerce")
 
    return df

def load(df: pd.DataFrame, db_path: str = DB_PATH) -> None:

    conn = sqlite3.connect(db_path)
    try:
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
    finally:
        conn.close()
 
 
def run_ingestion(data_path: str = DATA_PATH, db_path: str = DB_PATH) -> None:
    df = extract(data_path)
    df = transform(df)
    load(df, db_path)
    print(f"Ingested {len(df)} rows into '{db_path}' (table: {TABLE_NAME})")
 
 
if __name__ == "__main__":
    run_ingestion()