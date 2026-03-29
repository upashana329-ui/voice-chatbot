import os
import sys
import json
import logging
import uuid
import tempfile
import threading
import time
import subprocess
from datetime import datetime
from functools import lru_cache

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Third-party imports
import speech_recognition as sr
from gtts import gTTS
import requests
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv

# AI Libraries
import google.generativeai as genai

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chatbot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# AI Configuration
AI_PROVIDER = os.getenv('AI_PROVIDER', 'gemini')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')

# In-memory chat history
chat_history = []

# ==================== TTS ENGINE INITIALIZATION ====================

def init_tts_engine():
    """Initialize text-to-speech engine with error handling"""
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 175)
        engine.setProperty('volume', 0.9)
        
        # Try to set a female voice
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'female' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break
        
        logger.info("TTS Engine initialized successfully")
        return engine
    except Exception as e:
        logger.error(f"TTS Engine initialization failed: {e}")
        return None

tts_engine = init_tts_engine()

# ==================== GEMINI MODEL INITIALIZATION ====================

def init_gemini_model():
    """Initialize Gemini model with proper error handling"""
    try:
        if not GEMINI_API_KEY:
            logger.error("Gemini API key not found in .env file")
            return None
        
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Updated model names for 2026
        model_names = [
            'gemini-2.5-flash',
            'gemini-2.5-pro',
            'gemini-2.0-flash',
            'gemini-pro-latest',
            'gemini-flash-latest',
        ]
        
        for model_name in model_names:
            try:
                logger.info(f"Trying model: {model_name}")
                model = genai.GenerativeModel(model_name)
                # Quick test to verify model works
                test_response = model.generate_content("Say 'OK' in one word")
                if test_response and test_response.text:
                    logger.info(f"Successfully connected to Gemini model: {model_name}")
                    return model
            except Exception as e:
                logger.debug(f"Model {model_name} failed: {e}")
                continue
        
        logger.error("No working Gemini model found")
        return None
        
    except Exception as e:
        logger.error(f"Gemini initialization error: {e}")
        return None

# Initialize Gemini model
model = init_gemini_model()

# ==================== VOICE RECOGNITION FUNCTIONS ====================

def recognize_speech():
    """Convert speech to text using microphone"""
    recognizer = sr.Recognizer()
    
    try:
        with sr.Microphone() as source:
            logger.info("Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            logger.info("Listening...")
            
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                logger.info("Processing speech...")
                
                text = recognizer.recognize_google(audio)
                logger.info(f"Recognized: {text}")
                return {"success": True, "text": text}
                
            except sr.UnknownValueError:
                logger.warning("Could not understand audio")
                return {"success": False, "error": "Could not understand audio"}
            except sr.RequestError as e:
                logger.error(f"Speech recognition service error: {e}")
                return {"success": False, "error": "Speech service unavailable"}
            except sr.WaitTimeoutError:
                logger.warning("Listening timeout")
                return {"success": False, "error": "No speech detected"}
                
    except Exception as e:
        logger.error(f"Microphone error: {e}")
        return {"success": False, "error": f"Microphone error: {str(e)}"}

# ==================== TEXT TO SPEECH FUNCTIONS ====================

def speak_text_online(text, lang='en'):
    """Text-to-speech using Google TTS with improved playback"""
    try:
        # Create a dedicated temp directory
        temp_dir = os.path.join(tempfile.gettempdir(), 'voice_chatbot')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Generate unique filename
        filename = os.path.join(temp_dir, f"speech_{uuid.uuid4().hex}.mp3")
        
        # Generate speech
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(filename)
        
        # Play audio based on operating system
        if sys.platform == 'win32':
            try:
                # Try using winsound (Windows native)
                import winsound
                winsound.PlaySound(filename, winsound.SND_FILENAME)
            except:
                try:
                    # Alternative: use os.startfile
                    os.startfile(filename)
                    # Wait approximately for audio to finish
                    time.sleep(len(text) * 0.1)
                except:
                    # Last resort: use subprocess
                    subprocess.run(['start', filename], shell=True)
        elif sys.platform == 'darwin':  # macOS
            subprocess.run(['afplay', filename])
        else:  # Linux
            subprocess.run(['aplay', filename])
        
        # Clean up after a short delay
        def cleanup():
            time.sleep(3)  # Wait for playback to finish
            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except:
                pass
        
        threading.Thread(target=cleanup, daemon=True).start()
        
        return True
        
    except Exception as e:
        logger.error(f"Online TTS error: {e}")
        return False

def speak_text_offline(text):
    """Offline TTS using pyttsx3 with improved error handling"""
    try:
        if tts_engine:
            # Try to end any existing loop
            try:
                tts_engine.endLoop()
            except:
                pass
            
            # Split long text into sentences for better flow
            sentences = text.replace('!', '.').replace('?', '.').split('. ')
            for sentence in sentences:
                if sentence.strip():
                    tts_engine.say(sentence.strip())
                    tts_engine.runAndWait()
            return True
    except Exception as e:
        logger.error(f"Offline TTS error: {e}")
    
    return False

def speak_text_windows(text):
    """Windows SAPI fallback for TTS"""
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(text)
        return True
    except:
        return False

def speak_text(text, mode='online'):
    """Wrapper for TTS with multiple fallbacks"""
    # Try online TTS first if selected
    if mode == 'online':
        if speak_text_online(text):
            return True
    
    # Try offline TTS
    if speak_text_offline(text):
        return True
    
    # Try Windows SAPI
    if speak_text_windows(text):
        return True
    
    # Last resort - just print to console
    print(f"\n🤖 [AI Response]: {text}\n")
    return False

# ==================== AI RESPONSE FUNCTIONS ====================

def get_ai_response_gemini(user_input):
    """Get response from Google Gemini AI"""
    try:
        if not model:
            return "AI service is not configured properly."
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        prompt = f"""You are a helpful, friendly, and professional voice assistant named "Voice Assistant".
Current date and time: {current_time}

User: {user_input}
Assistant: """
        
        # Generate response with safety settings
        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.7,
                'max_output_tokens': 500,
            }
        )
        
        if response and response.text:
            return response.text.strip()
        else:
            return "I received your message but couldn't generate a proper response."
        
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return f"I encountered an error: {str(e)}. Please try again."

def get_ai_response_fallback(user_input):
    """Fallback rule-based responses when AI is unavailable"""
    user_input = user_input.lower()
    
    # Time and date
    if any(word in user_input for word in ['time', 'clock']):
        current_time = datetime.now().strftime("%I:%M %p")
        return f"The current time is {current_time}."
    
    if any(word in user_input for word in ['date', 'day', 'today']):
        current_date = datetime.now().strftime("%B %d, %Y")
        return f"Today's date is {current_date}."
    
    # Greetings
    if any(word in user_input for word in ['hello', 'hi', 'hey']):
        return "Hello! How can I help you today?"
    
    if any(word in user_input for word in ['how are you', 'how do you do']):
        return "I'm doing great, thank you for asking! How about you?"
    
    # Identity
    if any(word in user_input for word in ['your name', 'who are you']):
        return "My name is Voice Assistant. You can call me VA for short!"
    
    # Farewell
    if any(word in user_input for word in ['bye', 'goodbye', 'see you']):
        return "Goodbye! Have a wonderful day!"
    
    # Help
    if any(word in user_input for word in ['help', 'what can you do']):
        return "I can tell you the time and date, answer questions, have conversations, and more! What would you like to know?"
    
    # Default response
    return "I'm not sure how to respond to that. Could you please rephrase or ask me something else?"

def get_ai_response(user_input):
    """Main function to get AI response"""
    global chat_history
    
    # Get response based on provider
    if model:
        response = get_ai_response_gemini(user_input)
    else:
        response = get_ai_response_fallback(user_input)
    
    # Store in chat history
    chat_history.append({"role": "user", "content": user_input, "timestamp": datetime.now().isoformat()})
    chat_history.append({"role": "assistant", "content": response, "timestamp": datetime.now().isoformat()})
    
    # Keep history manageable
    if len(chat_history) > 50:
        chat_history = chat_history[-50:]
    
    return response

# ==================== UTILITY FUNCTIONS ====================

@lru_cache(maxsize=100)
def get_cached_weather(city):
    """Get cached weather information"""
    if not WEATHER_API_KEY:
        return "Weather API key not configured."
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if response.status_code == 200:
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            desc = data['weather'][0]['description']
            humidity = data['main']['humidity']
            return f"Weather in {city.title()}: {temp}°C, {desc}. Feels like {feels_like}°C. Humidity: {humidity}%."
        else:
            return f"Could not fetch weather for {city}. Error: {data.get('message', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return "Weather service unavailable. Please check your internet connection."

@lru_cache(maxsize=50)
def get_cached_news(category='general'):
    """Get cached news headlines"""
    if not NEWS_API_KEY:
        return "News API key not configured."
    
    try:
        url = f"https://newsapi.org/v2/top-headlines?country=us&category={category}&apiKey={NEWS_API_KEY}"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if response.status_code == 200 and data.get('articles'):
            headlines = [f"• {article['title']}" for article in data['articles'][:5]]
            return "Top headlines:\n" + "\n".join(headlines)
        else:
            return "Could not fetch news at this moment."
    except Exception as e:
        logger.error(f"News error: {e}")
        return "News service unavailable."

# ==================== FLASK ROUTES ====================

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Chat endpoint"""
    try:
        data = request.json
        user_input = data.get('message', '').strip()
        
        if not user_input:
            return jsonify({'error': 'No message provided'}), 400
        
        # Check for special commands
        if user_input.lower().startswith('weather in '):
            city = user_input[11:].strip()
            response = get_cached_weather(city)
        elif user_input.lower().startswith('news'):
            parts = user_input.split()
            category = parts[1] if len(parts) > 1 else 'general'
            response = get_cached_news(category)
        else:
            response = get_ai_response(user_input)
        
        return jsonify({
            'success': True,
            'response': response,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/voice-input', methods=['POST'])
def voice_input():
    """Voice input endpoint"""
    result = recognize_speech()
    return jsonify(result)

@app.route('/api/voice-output', methods=['POST'])
def voice_output():
    """Voice output endpoint"""
    try:
        data = request.json
        text = data.get('text', '')
        mode = data.get('mode', 'online')
        
        # Run TTS in background thread to avoid blocking
        thread = threading.Thread(target=speak_text, args=(text, mode))
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Voice output error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get chat history"""
    return jsonify({
        'success': True,
        'history': chat_history
    })

@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    """Clear chat history"""
    global chat_history
    chat_history = []
    return jsonify({'success': True})

@app.route('/api/weather/<city>', methods=['GET'])
def weather(city):
    """Weather endpoint"""
    result = get_cached_weather(city)
    return jsonify({'success': True, 'response': result})

@app.route('/api/news/<category>', methods=['GET'])
def news(category):
    """News endpoint"""
    result = get_cached_news(category)
    return jsonify({'success': True, 'response': result})

@app.route('/api/status', methods=['GET'])
def status():
    """Check system status"""
    model_info = "None"
    if model:
        try:
            model_info = model.model_name
        except:
            model_info = "Connected (model unknown)"
    
    return jsonify({
        'success': True,
        'status': 'online',
        'ai_provider': AI_PROVIDER,
        'ai_configured': model is not None,
        'model_name': model_info,
        'tts_available': tts_engine is not None,
        'stt_available': True,
        'features': {
            'weather': bool(WEATHER_API_KEY),
            'news': bool(NEWS_API_KEY)
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update user settings"""
    try:
        data = request.json
        session['voice_mode'] = data.get('voice_mode', 'online')
        session['voice_speed'] = data.get('voice_speed', 175)
        
        if tts_engine and 'voice_speed' in data:
            tts_engine.setProperty('rate', int(data['voice_speed']))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🤖 ADVANCED VOICE CHATBOT")
    print("="*60)
    print(f"AI Provider: {AI_PROVIDER}")
    print(f"AI Status: {'✅ Connected' if model else '❌ Not Connected'}")
    print(f"TTS Engine: {'✅ Available' if tts_engine else '❌ Unavailable'}")
    print(f"Speech Recognition: ✅ Available")
    print(f"Weather API: {'✅ Configured' if WEATHER_API_KEY else '❌ Not Configured'}")
    print(f"News API: {'✅ Configured' if NEWS_API_KEY else '❌ Not Configured'}")
    print("="*60)
    print("Server starting on http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
