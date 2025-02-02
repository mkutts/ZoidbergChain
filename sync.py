import requests

MAIN_NODE = "https://zoidbergcoin.com"  # Use HTTPS instead of HTTP

def fetch_latest_chain():
    """Fetch the latest blockchain state from the main node."""
    try:
        response = requests.get(f"{MAIN_NODE}/sync", verify=True)  # Enforce HTTPS
        if response.status_code == 200:
            blockchain_data = response.json()
            print("Blockchain synced successfully.")
            return blockchain_data
        else:
            print("Error syncing blockchain:", response.text)
    except Exception as e:
        print("Sync failed:", e)

fetch_latest_chain()
