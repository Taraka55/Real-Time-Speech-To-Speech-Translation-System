import os
import uuid
import time
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from pydub import AudioSegment
import speech_recognition as sr
from deep_translator import GoogleTranslator
from gtts import gTTS

app = Flask(__name__)
DB_NAME = "users.db" 

# ---------------- DATABASE SETUP ----------------
def init_db():
    """Initializes the SQLite database and creates the users table."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE,
                dob TEXT
            );
        """)
        conn.commit() 

        try:
            cursor.execute("SELECT email FROM users LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT;")
            conn.commit()
        
        try:
            cursor.execute("SELECT dob FROM users LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE users ADD COLUMN dob TEXT;")
            conn.commit()
        
        # Initial user population (included for completeness and quick setup)
        initial_users = {
            "Supriya": ("4239", "supriya@example.com", "1999-01-01"),
            "Taraka": ("4259", "taraka@example.com", "2000-02-02"),
            "Sireesha": ("4208", "sireesha@example.com", "2001-03-03"),
            "NagaJyothi": ("4233", "nagajyothi@example.com", "2002-04-04"),
            "Rani": ("rani", "rani@example.com", "2003-05-05"),
            "Naveen": ("naveen", "naveen@example.com", "2004-06-06"),
            "Hari Kishan Sir": ("hari kishan sir", "hari.kishan.sir@example.com", "1980-07-07")
        }
        for username, (password, email, dob) in initial_users.items():
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user_data = cursor.fetchone()
            
            hashed_password = generate_password_hash(password)
            
            if user_data is None:
                cursor.execute(
                    "INSERT INTO users (username, password_hash, email, dob) VALUES (?, ?, ?, ?)",
                    (username, hashed_password, email, dob)
                )
            else:
                cursor.execute(
                    "UPDATE users SET password_hash = ?, email = ?, dob = ? WHERE username = ?", 
                    (hashed_password, email, dob, username)
                )

        conn.commit()

init_db()

# ---------------- PATHS & UTILS ----------------
UPLOAD = "uploads"
OUT = "static/out"
os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

LANGS = {
    "English": "en", "Hindi": "hi", "Telugu": "te", "Tamil": "ta", 
    "Kannada": "kn", "Malayalam": "ml", "Marathi": "mr", "Gujarati": "gu",
    "Bengali": "bn", "Punjabi": "pa", "Urdu": "ur", "Odia": "or",
    "Assamese": "as", "Nepali": "ne", "Spanish": "es", "French": "fr",
    "German": "de", "Italian": "it", "Portuguese": "pt", "Japanese": "ja",
    "Korean": "ko", "Arabic": "ar"
}

def convert_to_wav(in_path, out_path):
    """
    Converts audio to mono 16kHz WAV and normalizes volume.
    """
    audio = AudioSegment.from_file(in_path)
    audio = audio.set_frame_rate(16000).set_channels(1)
    audio = audio.normalize()
    audio.export(out_path, format="wav")

def recognize_speech(wav_path, lang):
    recognizer = sr.Recognizer()

    # Aggressive noise control
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_adjustment_damping = 0.3
    recognizer.dynamic_energy_adjustment_ratio = 1.2
    recognizer.pause_threshold = 0.8
    recognizer.phrase_threshold = 0.1
    recognizer.non_speaking_duration = 0.3

    if not os.path.exists(wav_path):
        return ""

    with sr.AudioFile(wav_path) as source:
        recognizer.adjust_for_ambient_noise(source, duration=1.0)
        audio = recognizer.record(source)

    try:
        return recognizer.recognize_google(audio, language=lang)
    except:
        return ""
# ---------------- CORE ROUTES (Login and Setup - Unchanged) ----------------

@app.route("/")
@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    login_identifier = request.form["username"].strip()
    password = request.form["password"]
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT password_hash 
            FROM users 
            WHERE username = ? OR email = ?
        """, (login_identifier, login_identifier))
        
        result = cursor.fetchone()
        
    if result and check_password_hash(result[0], password):
        return redirect("/translator")
    
    return "<script>alert('Invalid Credentials');window.location='/'</script>"

@app.route("/create_account")
def create_account_page():
    return render_template("create_account.html") 

@app.route("/create_account", methods=["POST"])
def create_account():
    username = request.form["username"].strip()
    email = request.form["email"].strip()
    password = request.form["password"]
    re_enter_password = request.form["re_enter_password"]
    dob = request.form["dob"].strip()

    if password != re_enter_password:
        return "<script>alert('Passwords do not match!');window.location='/create_account'</script>"

    hashed_password = generate_password_hash(password)
    
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, email, dob) VALUES (?, ?, ?, ?)",
                (username, hashed_password, email, dob)
            )
            conn.commit()
            return "<script>alert('Account created successfully! Please login.');window.location='/'</script>"
    except sqlite3.IntegrityError:
        return "<script>alert('Username or Email already exists. Please choose a different one.');window.location='/create_account'</script>"
    except Exception as e:
        print(f"Database error: {e}")
        return "<script>alert('An error occurred during registration.');window.location='/create_account'</script>"

@app.route("/forgot_password")
def forgot_password_page():
    return render_template("forgot_password.html")

@app.route("/send_reset_link", methods=["POST"])
def send_reset_link():
    identifier = request.form.get("identifier", "").strip() 

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT username, email FROM users WHERE username = ? OR email = ?", (identifier, identifier))
        result = cursor.fetchone()
    
    if result:
        user_username = result[0]
        user_email = result[1]
        
        return render_template("reset_link_sent.html", identifier=user_username, email=user_email)
    else:
        return "<script>alert('User not found. Please check your Username or Email.');window.location='/forgot_password'</script>"

@app.route("/set_new_password", methods=["GET", "POST"])
def set_new_password():
    
    if request.method == "GET":
        identifier_from_url = request.args.get('identifier', '')
        return render_template("set_new_password.html", identifier=identifier_from_url)

    if request.method == "POST":
        identifier = request.form.get("identifier").strip()
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
             return render_template("set_new_password.html", identifier=identifier, error="Passwords do not match!")

        hashed_password = generate_password_hash(new_password)
        
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET password_hash = ? WHERE username = ? OR email = ?",
                    (hashed_password, identifier, identifier)
                )
                conn.commit()
                return render_template("reset_confirmation.html", identifier=identifier)
        except Exception as e:
            print(f"Password update error: {e}")
            return "<script>alert('An error occurred during password update.');window.location='/forgot_password'</script>"


# ---------------- TRANSLATOR ROUTE ----------------
@app.route("/translator")
def translator_page():
    return render_template("index.html", languages=LANGS)

# ================= AUDIO PROCESS =================
@app.route("/process_audio", methods=["POST"])
def process_audio():
    if "audio" not in request.files:
        return jsonify({"error": "No audio uploaded"}), 400

    f = request.files["audio"]
    input_lang = request.form.get("input_lang", "en")

    raw_name = f"input_{uuid.uuid4().hex}.webm"
    raw_path = os.path.join(OUT, raw_name)
    f.save(raw_path)

    wav_path = os.path.join(UPLOAD, f"{uuid.uuid4().hex}.wav")

    try:
        convert_to_wav(raw_path, wav_path)
        recognized_text = recognize_speech(wav_path, input_lang)
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)

    if not recognized_text.strip():
        if os.path.exists(raw_path):
            os.remove(raw_path)
        return jsonify({"recognized_text": "", "input_audio_url": ""})

    return jsonify({
        "recognized_text": recognized_text,
        "input_audio_url": url_for("static", filename=f"out/{raw_name}")
    })

# ================= TRANSLATION =================
@app.route("/translate_text", methods=["POST"])
def translate_text():
    text = request.form.get("text")
    src = request.form.get("input_lang")
    tgt = request.form.get("output_lang")

    if not text:
        return jsonify({"translated_text": ""})

    time.sleep(1)

    try:
        translated = GoogleTranslator(source=src, target=tgt).translate(text)
    except:
        translated = text

    return jsonify({"translated_text": translated})

# ================= TEXT TO SPEECH =================
@app.route("/get_tts_audio", methods=["POST"])
def get_tts_audio():
    data = request.get_json()
    text = data.get("text")
    lang = data.get("lang")

    if not text:
        return jsonify({"translated_audio_url": ""})

    file = f"tts_{uuid.uuid4().hex}.mp3"
    path = os.path.join(OUT, file)

    gTTS(text, lang=lang).save(path)
    return jsonify({"translated_audio_url": url_for("static", filename=f"out/{file}")})

# ================= PLAY AUDIO =================
@app.route("/play/<path:filename>")
def play_file(filename):
    return send_file(os.path.join(OUT, filename))

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)