import os
import uuid
import logging
from datetime import datetime
from functools import lru_cache

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

import google.generativeai as genai
from gtts import gTTS
import requests

# ================= CONFIG =================

load_dotenv()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

chat_history = []

# ================= GEMINI =================

def init_model():
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        return genai.GenerativeModel("gemini-2.0-flash")
    except:
        return None

model = init_model()

# ================= AI =================

def get_ai_response(user_input):
    try:
        if model:
            response = model.generate_content(user_input)
            return response.text
        else:
            return "AI not configured."
    except Exception as e:
        return f"Error: {str(e)}"

# ================= TTS =================

def text_to_speech(text):
    try:
        filename = f"audio_{uuid.uuid4().hex}.mp3"
        tts = gTTS(text=text)
        tts.save(filename)
        return filename
    except Exception as e:
        logger.error(e)
        return None

# ================= WEATHER =================

@lru_cache(maxsize=50)
def get_weather(city):
    if not WEATHER_API_KEY:
        return "Weather API not configured"

    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        data = requests.get(url).json()

        if data.get("main"):
            return f"{city}: {data['main']['temp']}°C, {data['weather'][0]['description']}"
        else:
            return "City not found"
    except:
        return "Weather error"

# ================= ROUTES =================

@app.route("/")
def home():
    return "Voice Chatbot API Running 🚀"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    msg = data.get("message", "")

    if not msg:
        return jsonify({"error": "No message"}), 400

    if msg.lower().startswith("weather"):
        city = msg.split("weather")[-1].strip()
        reply = get_weather(city)
    else:
        reply = get_ai_response(msg)

    chat_history.append({"user": msg, "bot": reply})

    return jsonify({
        "response": reply,
        "time": datetime.now().isoformat()
    })

@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text", "")

    file = text_to_speech(text)

    if file:
        return jsonify({"audio": file})
    else:
        return jsonify({"error": "TTS failed"}), 500

@app.route("/history")
def history():
    return jsonify(chat_history)

# ================= MAIN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
