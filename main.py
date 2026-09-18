import sys
from src.fetcher import fetch_exchange_rates
from src.transformer import transform_rate_payload
from src.storage import save_record

def run():
    try:
        print("Starting data pipeline execution...")
        raw_data = fetch_exchange_rates()
        processed_record = transform_rate_payload(raw_data)
        save_record(processed_record)
        print("Pipeline execution completed successfully.")
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run()