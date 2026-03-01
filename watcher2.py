import time
import json
import os
import requests
from datetime import datetime

#MAIN

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxn9o6bg3UaZn4Tovl2Df6rG5lJ9I9LxdvAZ40gOKtXofVe4f4o39uLGi2AkNhLKLO5Xw/exec"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_TO_WATCH = os.path.join(SCRIPT_DIR, "fridge2_5.json")

USERNAME = "admin"
PASSWORD = "password123"


# ---------------------
# CALCULATE STATUS
# ---------------------
def calc_status(expiry):
    if not expiry or expiry == "N/A":
        return "N/A", ""

    try:
        today = datetime.now().date()
        exp = datetime.strptime(expiry, "%Y/%m/%d").date()
        days_left = (exp - today).days

        if days_left < 0:
            return "Expired", days_left
        elif days_left <= 2:
            return "Expired Soon", days_left
        else:
            return "Good to Eat", days_left
    except:
        return "N/A", ""


# ---------------------
# PUSH TO GOOGLE SHEET
# ---------------------
def push_to_google_sheet(data):
    """Send flattened rows WITH STATUS"""

    flattened_items = []

    if isinstance(data, dict):
        for item_key, item_details in data.items():
            item_name = item_details.get("item_name", item_key)
            unit = item_details.get("unit", "")
            category = item_details.get("category", "")

            batches = item_details.get("batches", [])

            for batch in batches:
                expiry = batch.get("expiry", "")

                # --- Ensure status always updated ---
                status, days_left = calc_status(expiry)

                flattened_items.append({
                    "item_name": item_name,
                    "qty": batch.get("qty", 0),
                    "unit": unit,
                    "category": category,
                    "expiry": expiry,
                    "status": status,
                    "days_left": days_left
                })

    else:
        flattened_items = data

    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "items": flattened_items
    }

    try:
        print(">> Uploading to Google Sheets...")
        response = requests.post(WEB_APP_URL, json=payload)
        print(f">> Server Response: {response.text}")
    except Exception as e:
        print(f">> Error uploading: {e}")


# ---------------------
# WATCH FILE
# ---------------------
def main():
    print(f"*** Monitoring {FILE_TO_WATCH} for changes ***")
    print("Keep this terminal open. Press Ctrl+C to stop.")

    if not os.path.exists(FILE_TO_WATCH):
        print(f"Error: {FILE_TO_WATCH} not found!")
        return

    last_mod_time = os.path.getmtime(FILE_TO_WATCH)

    while True:
        try:
            time.sleep(1)
            current_mod_time = os.path.getmtime(FILE_TO_WATCH)

            if current_mod_time != last_mod_time:
                print(f"\n[Detected Change] {FILE_TO_WATCH} updated.")
                time.sleep(0.5)

                try:
                    with open(FILE_TO_WATCH, 'r') as f:
                        data = json.load(f)

                    push_to_google_sheet(data)
                    last_mod_time = current_mod_time

                except json.JSONDecodeError:
                    print(">> Error: Invalid JSON. Waiting...")
                except Exception as e:
                    print(f">> Error reading file: {e}")

        except KeyboardInterrupt:
            print("\nStopping watcher...")
            break
        except FileNotFoundError:
            print(f"File {FILE_TO_WATCH} not found. Waiting...")


if __name__ == "__main__":
    main()
