import os
import csv
from typing import Dict, Any

DATA_FILE = "data/daily_rates.csv"
FIELDNAMES = ["date", "api_updated_at", "EUR", "GBP", "CAD", "JPY", "ETB"]

def save_record(record: Dict[str, Any], filepath: str = DATA_FILE) -> bool:
    """Append normalized record to CSV without duplicate date entries."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    file_exists = os.path.isfile(filepath)
    
    existing_dates = set()
    if file_exists:
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_dates.add(row["date"])
                
    if record["date"] in existing_dates:
        print(f"Record for {record['date']} already exists. Skipping write.")
        return False
        
    with open(filepath, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)
        
    print(f"Record for {record['date']} successfully stored.")
    return True