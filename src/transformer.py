from datetime import datetime
from typing import Dict, Any

TARGET_CURRENCIES = ["EUR", "GBP", "CAD", "JPY", "ETB"]

def transform_rate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract target rates and format with consistent timestamps."""
    raw_rates = payload.get("rates", {})
    last_update_utc = payload.get("time_last_update_utc", "")
    
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    record = {
        "date": date_str,
        "api_updated_at": last_update_utc,
    }
    
    for curr in TARGET_CURRENCIES:
        record[curr] = round(raw_rates.get(curr, 0.0), 4)
        
    return record