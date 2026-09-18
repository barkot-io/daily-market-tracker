import requests
from typing import Dict, Any

API_URL = "https://open.er-api.com/v6/latest/USD"

def fetch_exchange_rates() -> Dict[str, Any]:
    """Fetch current USD base exchange rates."""
    response = requests.get(API_URL, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    if data.get("result") != "success":
        raise ValueError(f"API call failed with status: {data.get('result')}")
    
    return data

if __name__ == "__main__":
    rates = fetch_exchange_rates()
    print(f"Fetched {len(rates.get('rates', {}))} currencies.")