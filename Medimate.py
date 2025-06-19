import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import googlemaps
import random
from gtts import gTTS
import tempfile
import os
import re
import hashlib
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

genai.configure(api_key="YOUR_GEMINI_API_KEY")
model = genai.GenerativeModel("gemini-1.5-flash")
gmaps = googlemaps.Client(key="YOUR_GOOGLE_API_KEY")

CRITICAL_SYMPTOMS = ["chest pain", "shortness of breath", "severe bleeding", "loss of consciousness", "vision loss", "high fever", "fainting"]
EMERGENCY_MEDS = ["Paracetamol (for fever)", "ORS (dehydration)", "Antacid (e.g. Gelusil)", "Loperamide (diarrhea)", "Cetirizine (allergy)", "Disprin (headache)", "Dolo 650"]
JOKES = [
    "Lagta hai aapka metabolism Netflix dekh raha hai!",
    "Bukhar itna high ki thermometer resign de diya!",
    "Khansi ka season chal raha hai — virus ki Diwali!",
    "Chest pain? Love failure bhi ho sakta hai!",
    "Test results horror movie se kam nahi!"
]

if 'USERS' not in st.session_state:
    st.session_state.USERS = {}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    if username in st.session_state.USERS:
        return False, "Username already exists."
    st.session_state.USERS[username] = hash_password(password)
    return True, "Registration successful."

def login_user(username, password):
    hashed = hash_password(password)
    if st.session_state.USERS.get(username) == hashed:
        return True, "Login successful."
    return False, "Invalid username or password."

def scrape_disease_data(keyword):
    try:
        url = f"https://www.webmd.com/search/search_results/default.aspx?query={keyword}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(resp.text, "html.parser")
        p = soup.find_all("p")[:3]
        return " ".join(x.get_text(strip=True) for x in p) or "No reliable data found."
    except Exception as e:
        return f"Error scraping WebMD: {e}"

def ask_ai(symptoms, data, img_summary=""):
    prompt = (
        f"👨‍⚕ Symptoms: '{symptoms}'\n📚 WebMD Data: {data}\n"
        f"🖼 Image Diagnosis: {img_summary}\n\n"
        "✅ Answer in Hinglish:\n"
        "1. Possible Diagnosis\n2. Precautions\n3. OTC medicine suggestion\n4. Hospital visit advice\n5. Add a witty dark joke"
    )
    r = model.generate_content(prompt)
    return r.text

def is_critical(symptoms):
    return any(x in symptoms.lower() for x in CRITICAL_SYMPTOMS)

def fetch_hospitals(city, state):
    try:
        geocode = gmaps.geocode(f"{city}, {state}, India")
        if not geocode:
            return ["❌ Location not found."]
        loc = geocode[0]["geometry"]["location"]
        places = gmaps.places_nearby(location=(loc["lat"], loc["lng"]), radius=5000, type="hospital")["results"][:5]
        hospitals = []
        for p in places:
            name = p.get("name", "Unknown")
            addr = p.get("vicinity", "No address")
            rating = p.get("rating", "No rating")
            hospitals.append(f"{name} | {rating}⭐ | {addr}")
        return hospitals if hospitals else ["❌ No hospitals found."]
    except Exception as e:
        return [f"❌ Hospital fetch error: {e}"]

def clean_text_for_tts(text):
    return re.sub(r"[^\w\s.,?!']", "", text.encode("ascii", "ignore").decode())

def speak_hinglish(text):
    clean_text = clean_text_for_tts(text)
    tts = gTTS(text=clean_text, lang='hi')
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tts.save(temp.name)
    return temp.name

def diagnose_image(image_file):
    if image_file:
        try:
            img = Image.open(image_file)
            response = model.generate_content(["What does this image look like medically?", img])
            return response.text
        except Exception as e:
            return f"❌ Image diagnosis failed: {e}"
    return "No image provided."

st.set_page_config(page_title="MediMate | AI Doctor", page_icon="🩺", layout="centered")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🩺 MediMate Login")
    choice = st.radio("Choose an option:", ["Login", "Register"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Submit"):
        if choice == "Register":
            success, msg = register_user(username, password)
        else:
            success, msg = login_user(username, password)
            if success:
                st.session_state.logged_in = True
                st.session_state.username = username
        st.info(msg)
else:
    st.markdown("<h1 style='text-align:center;'>🩺 MediMate: Your AI Doctor Assistant 👨‍⚕️</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;'>Describe your symptoms & location to get instant advice, hospital info & memes!</p>", unsafe_allow_html=True)

    with st.form("health_form"):
        symptoms = st.text_input("📝 Symptoms", placeholder="E.g. chest pain, fever...")
        city = st.text_input("🌆 City", placeholder="E.g. Jaipur")
        state = st.text_input("🗺 State", placeholder="E.g. Rajasthan")
        uploaded_image = st.file_uploader("🖼 Upload affected area image", type=["jpg", "jpeg", "png"])
        submit = st.form_submit_button("Diagnose Me 🔍")

    if submit:
        with st.spinner("Analyzing your symptoms..."):
            with ThreadPoolExecutor() as executor:
                future_disease = executor.submit(scrape_disease_data, symptoms)
                future_img = executor.submit(diagnose_image, uploaded_image)
                disease_info = future_disease.result()
                img_summary = future_img.result()

            ai_out = ask_ai(symptoms, disease_info, img_summary)

            med_tip = f"\n\n💊 Emergency Med Tip: {random.choice(EMERGENCY_MEDS)}"
            joke = f"\n\n😜 Joke: {random.choice(JOKES)}"
            critical = "\n\n⚠ This seems serious—please go to a hospital immediately! 🏥" if is_critical(symptoms) else ""

            hospitals = fetch_hospitals(city, state)
            hospital_block = f"\n\n🚑 Nearby Hospitals in {city}, {state}:\n" + "\n".join([f"- {h}" for h in hospitals])

            final_output = ai_out + med_tip + joke + critical + hospital_block

            st.markdown("---")
            st.markdown("#### 🧾 Diagnosis Result")
            st.markdown(final_output)

            st.markdown("#### 🔊 Voice Output")
            audio_path = speak_hinglish(ai_out)
            st.audio(audio_path, format="audio/mp3")

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown("---")
    st.markdown("<p style='text-align:center;'>MADE WITH ❤️ BY TEAM LUNCH BREAK 🐉</p>", unsafe_allow_html=True)
