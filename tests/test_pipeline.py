import pytest
from src.transformer import transform_rate_payload
from src.storage import save_record
import csv

def test_transform_rate_payload():
    mock_payload = {
        "time_last_update_utc": "Thu, 18 Sep 2026 00:00:01 +0000",
        "rates": {
            "EUR": 0.92345,
            "GBP": 0.79123,
            "CAD": 1.35411,
            "JPY": 155.234,
            "ETB": 120.450
        }
    }
    result = transform_rate_payload(mock_payload)
    assert result["EUR"] == 0.9235
    assert result["ETB"] == 120.45
    assert "date" in result

def test_storage_deduplication(tmp_path):
    test_csv = tmp_path / "test_rates.csv"
    record = {
        "date": "2026-09-18",
        "api_updated_at": "test_time",
        "EUR": 0.92,
        "GBP": 0.79,
        "CAD": 1.35,
        "JPY": 155.0,
        "ETB": 120.0
    }
    
    first_write = save_record(record, filepath=str(test_csv))
    second_write = save_record(record, filepath=str(test_csv))
    
    assert first_write is True
    assert second_write is False