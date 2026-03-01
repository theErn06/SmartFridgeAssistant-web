"""
Smart voice fridge assistant (self-contained).
File: fridge_assistant.py
"""

# FIXED: Now detects both DIGITS (1, 2, 5) and NUMBER WORDS (one, two, five). MAIN

import os
import json
import re
import requests
import pyttsx3
import speech_recognition as sr
import time
import serial
import threading
from typing import List, Dict, Any
from datetime import datetime, timedelta

# =========================
# GLOBAL STATES
# =========================
jarvis_awake = False
door_open = False
door_open_time = None
conversation_ended_time = None

# =========================
# Arduino Serial
# =========================
try:
    arduino = serial.Serial("COM5", 9600, timeout=1)
    time.sleep(2)
except Exception as e:
    print("⚠️ Arduino not connected:", e)
    arduino = None


def send_to_lcd(text: str):
    if arduino:
        try:
            arduino.write((text.strip() + "\n").encode())
        except Exception:
            pass


# =========================
# Door Listener (FLAGS ONLY)
# =========================
def listen_door_events():
    global jarvis_awake, door_open, door_open_time

    while True:
        try:
            if arduino and arduino.in_waiting:
                msg = arduino.readline().decode(errors="ignore").strip()

                if msg == "DOOR_OPEN":
                    door_open = True
                    door_open_time = time.time()
                    jarvis_awake = True
                    send_to_lcd("JARVIS: Door opened")

                elif msg == "DOOR_CLOSED":
                    door_open = False
                    door_open_time = None

        except Exception:
            pass

        time.sleep(0.1)


# =========================
# Door Reminder Watchdog
# =========================
def door_reminder_watchdog():
    global door_open_time

    while True:
        if (
            door_open
            and not jarvis_awake                      
            and conversation_ended_time is not None   
            and time.time() - conversation_ended_time >= 30
        ):
            speak("Please close the fridge door.")
            time.sleep(30)

        time.sleep(1)


# =========================
# Config
# =========================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(SCRIPT_DIR, "fridge2_5.json") 
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "jarvis"
STT_LANGUAGE = "en-US"

# =========================
# Shelf Life Rules
# =========================
SHELF_LIFE_RULES = {
    "protein": 4,
    "seafood": 7,
    "dairy": 10,
    "vegetables": 7,
    "fruits": 7,
    "grains": 14,
    "pantry": 365,
    "processed": 7,
    "non-food": 0
}

# =========================
# Persistent fridge memory
# =========================
def load_fridge() -> Dict[str, Any]:
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_fridge(fridge: Dict[str, Any]):
    with open(MEMORY_FILE, "w") as f:
        json.dump(fridge, f, indent=2)


def calculate_expiry(category: str) -> str:
    days = SHELF_LIFE_RULES.get(category.lower(), 7)
    if days == 0:
        return "N/A"
    expiry_date = datetime.now() + timedelta(days=days)
    return expiry_date.strftime("%Y/%m/%d")


def get_batch_status(expiry: str) -> str:
    if not expiry or expiry == "N/A":
        return "N/A"
    try:
        today = datetime.now().date()
        exp = datetime.strptime(expiry, "%Y/%m/%d").date()
        days_left = (exp - today).days

        if days_left < 0:
            return "Expired"
        elif days_left <= 2:
            return "Expired Soon"
        else:
            return "Good to Eat"
    except:
        return "N/A"


def update_fridge(item: str, delta: int, unit="pieces", category="fruits"):
    try:
        fridge = load_fridge()
        item = item.lower().strip()

        if item not in fridge:
            fridge[item] = {
                "item_name": item,
                "unit": unit,
                "category": category,
                "batches": []
            }

        entry = fridge[item]

        # ================= ADD =================
        if delta > 0:
            new_expiry = calculate_expiry(category)
            new_status = get_batch_status(new_expiry)

            merged = False
            for batch in entry["batches"]:
                if batch.get("expiry") == new_expiry:
                    batch["qty"] += delta
                    batch["status"] = get_batch_status(batch.get("expiry"))
                    merged = True
                    break

            if not merged:
                entry["batches"].append({
                    "qty": delta,
                    "expiry": new_expiry,
                    "status": new_status
                })

        # ================= REMOVE =================
        elif delta < 0:
            remove_qty = -delta

            def expiry_key(b):
                try:
                    return datetime.strptime(b["expiry"], "%Y/%m/%d") if b["expiry"] != "N/A" else datetime.max
                except:
                    return datetime.max

            entry["batches"].sort(key=expiry_key)

            i = 0
            while remove_qty > 0 and i < len(entry["batches"]):
                batch = entry["batches"][i]

                if batch["qty"] <= remove_qty:
                    remove_qty -= batch["qty"]
                    batch["qty"] = 0
                else:
                    batch["qty"] -= remove_qty
                    remove_qty = 0

                batch["status"] = get_batch_status(batch.get("expiry"))
                i += 1

            entry["batches"] = [b for b in entry["batches"] if b["qty"] > 0]

            if not entry["batches"]:
                fridge.pop(item, None)

        # ===== UPDATE STATUS FOR ALL BATCHES =====
        for b in entry.get("batches", []):
            b["status"] = get_batch_status(b.get("expiry"))

        save_fridge(fridge)

    except Exception as e:
        print("⚠️ update_fridge error:", e)



def get_fridge_contents_text() -> str:
    fridge = load_fridge()
    if not fridge: return "The fridge is empty."
    lines = []
    for item, data in fridge.items():
        total = sum(b.get("qty", 0) for b in data.get("batches", []))
        lines.append(f"{data['item_name']} | {total} {data['unit']}")
    return "; ".join(lines)


def get_item_count_text(item: str) -> str:
    fridge = load_fridge()
    item = item.lower().strip()
    if item in fridge:
        total = sum(b.get("qty", 0) for b in fridge[item].get("batches", []))
        return f"You have {total} {fridge[item]['unit']} of {item}."
    return f"You don't have any {item}."


# =========================
# STT & TTS
# =========================
recognizer = sr.Recognizer()

def get_voice_input() -> str:
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
            audio = recognizer.listen(source, timeout=6, phrase_time_limit=8)
        text = recognizer.recognize_google(audio, language=STT_LANGUAGE).lower().strip()
        send_to_lcd(f"YOU: {text}")
        return text
    except Exception: return ""

engine = pyttsx3.init()
engine.setProperty("rate", 150)
tts_lock = threading.Lock()

def speak(text: str):
    with tts_lock:
        send_to_lcd(f"JARVIS: {text}")
        engine.stop()
        engine.say(text)
        engine.runAndWait()


# =========================
# LLM & Execution
# =========================
def ask_llm_json_actions(user_input: str, fridge_context: str) -> str:
    prompt = f"""
You are Jarvis. Return a JSON list of actions.
Fridge: {fridge_context}
User: "{user_input}"
"""
    try:
        resp = requests.post(OLLAMA_URL, json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}]}, stream=True, timeout=60)
        collected = ""
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                j = json.loads(line)
                collected += j["message"]["content"]
        m = re.search(r"(\[.*\])", collected, re.DOTALL)
        return m.group(1) if m else "[]"
    except Exception: return "[]"


def get_quantity_from_speech(text: str) -> int:
    """Extracts quantity from speech, handling both '5' and 'five'."""
    text = text.lower()
    
    # 1. Check for digits (e.g., "5")
    digits = re.findall(r"\b(\d+)\b", text)
    if digits:
        return int(digits[0])

    # 2. Check for number words (e.g., "five")
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30
    }
    
    for word, num in word_to_num.items():
        if f" {word} " in f" {text} ":  # Ensure it matches whole word
            return num
            
    return 1 # Default if nothing found


def execute_actions(actions: List[Dict[str, Any]], user_text_backup: str = ""):
    
    # Force check speech for the real number
    forced_qty = get_quantity_from_speech(user_text_backup)

    for a in actions:
        action = a.get("action")
        item = a.get("item")
        
        # Get what the AI thinks
        ai_val = a.get("count") or a.get("qty") or 1
        
        # LOGIC: If AI says 1, but we heard a different number > 1, TRUST OUR EARS.
        if ai_val == 1 and forced_qty > 1:
            val = forced_qty
        else:
            val = ai_val

        if action == "add" or action == "at":
            update_fridge(item, val)
            speak(f"Added {val} {item}.")

        elif action == "remove":
            update_fridge(item, -val)
            speak(f"Removed {val} {item}.")

        elif action == "lookup":
            speak(get_item_count_text(item))

        elif action == "list":
            speak(get_fridge_contents_text())

        else:
            speak("I'm here.")


# =========================
# MAIN LOOP
# =========================
def start_session():
    global jarvis_awake, conversation_ended_time
    threading.Thread(target=listen_door_events, daemon=True).start()
    threading.Thread(target=door_reminder_watchdog, daemon=True).start()
    speak("Jarvis 5 is ready.")

    while True:
        user_text = get_voice_input()
        if not user_text: continue

        if not jarvis_awake:
            wake_phrases = ["hey jarvis", "play jar", "hey joe", "play jarvis", "hey jar"]
            if any(phrase in user_text for phrase in wake_phrases):
                jarvis_awake = True
                conversation_ended_time = None
                speak("Yes?")
            continue

        if user_text in ("goodbye", "exit", "go to sleep"):
            speak("Thank you. Have a nice day.")
            jarvis_awake = False
            conversation_ended_time = time.time()
            continue

        fridge_ctx = get_fridge_contents_text()
        raw = ask_llm_json_actions(user_text, fridge_ctx)
        try:
            actions = json.loads(raw)
            # Pass user_text to force fix numbers
            execute_actions(actions, user_text_backup=user_text)
        except Exception: pass

if __name__ == "__main__":
    start_session()