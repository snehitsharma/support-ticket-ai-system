from datetime import datetime, timedelta

import pandas as pd

from db import get_db

STALE_HOURS = 24
HIGH_PRIORITY = ("High", "Critical")
Z_SCORE_THRESHOLD = 2.0


def _load_tickets() -> pd.DataFrame:
    conn = get_db()
    try:
        df = pd.read_sql("SELECT * FROM support_tickets", conn, parse_dates=["created_at"])
    finally:
        conn.close()
    return df


def stale_high_priority_tickets(df: pd.DataFrame) -> list[dict]:

    now = datetime.now()
    unresolved = df[df["status"] != "Resolved"]
    stale = unresolved[
        unresolved["priority"].isin(HIGH_PRIORITY)
        & ((now - unresolved["created_at"]) > timedelta(hours=STALE_HOURS))
    ]
    results = []
    for _, row in stale.iterrows():
        age_hrs = (now - row["created_at"]).total_seconds() / 3600
        results.append({
            "ticket_id": row["ticket_id"],
            "reason": (
                f"{row['priority']} priority, status={row['status']}, "
                f"open for {age_hrs:.1f}h (> {STALE_HOURS}h threshold)"
            ),
        })
    return results


def resolution_time_outliers(df: pd.DataFrame) -> list[dict]:
    
    resolved = df[df["resolution_time_hrs"].notna()].copy()
    results = []
    for category, group in resolved.groupby("category"):
        if len(group) < 2:
            continue
        mean = group["resolution_time_hrs"].mean()
        std = group["resolution_time_hrs"].std()
        if not std or pd.isna(std):
            continue
        threshold = mean + Z_SCORE_THRESHOLD * std
        flagged = group[group["resolution_time_hrs"] > threshold]
        for _, row in flagged.iterrows():
            z = (row["resolution_time_hrs"] - mean) / std
            results.append({
                "ticket_id": row["ticket_id"],
                "reason": (
                    f"resolution_time_hrs={row['resolution_time_hrs']:.1f}h in category "
                    f"'{category}' (mean={mean:.1f}h, std={std:.1f}h, z={z:.2f}, "
                    f"threshold={threshold:.1f}h)"
                ),
            })
    return results


def detect_anomalies() -> dict:
    df = _load_tickets()
    return {
        "stale_high_priority": stale_high_priority_tickets(df),
        "long_resolution_times": resolution_time_outliers(df),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(detect_anomalies(), indent=2, default=str))
