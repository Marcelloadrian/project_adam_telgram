import os
import sqlite3
from fastapi import FastAPI
from groq import Groq
from datetime import datetime
from geopy.geocoders import Nominatim
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

app = FastAPI()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
DB_PATH = "/tmp/adam_memory.db"

# --- HELPER LOKASI ---
def get_location_name(lat, lon):
    try:
        geolocator = Nominatim(user_agent="project_adam")
        location = geolocator.reverse(f"{lat}, {lon}")
        return location.address
    except:
        return "lokasi yang tidak terdeteksi"

# --- PERSONALITY ---
def get_system_prompt(formatted_notes, user_location):
    return f"""
    Lo adalah Adam, sahabat gue yang paling bisa diandelin. 
    LOKASI USER SEKARANG: {user_location}
    CATATAN MEMORI: {formatted_notes}
    ATURAN: Lo-gue, santai. Kalau user share lokasi, kasih saran/tanggapan berdasarkan tempat itu. 
    WAKTU SEKARANG: {datetime.now().strftime('%A, %d %B %Y %H:%M')}
    """

# --- CALLBACK REMINDER (DIUBAH JADI TEGAS) ---
async def callback_ngingetin(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    # Tanpa emoji, gaya bahasa tegas
    await context.bot.send_message(
        chat_id=job.chat_id, 
        text=f"Lu ada janji buat {job.data}. Jangan lupa ya."
    )

# --- BOT HANDLER ---
async def handle_telegram_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = update.effective_chat.id
    
    user_location = "Tangerang (default)"
    if msg.location:
        user_location = get_location_name(msg.location.latitude, msg.location.longitude)
    
    text = msg.text if msg.text else ""
    
    conn = sqlite3.connect(DB_PATH)
    if any(word in text.lower() for word in ["meeting", "rapat", "jadwal", "ingat", "catat"]):
        conn.execute("INSERT INTO notes (content, created_at) VALUES (?, ?)", (text, datetime.now()))
        conn.commit()
    notes = [row[0] for row in conn.execute("SELECT content FROM notes ORDER BY created_at DESC LIMIT 5").fetchall()]
    conn.close()

    ai_check = client.chat.completions.create(
        messages=[{"role": "system", "content": "Jika ada jadwal, jawab 'REMIND | KEGIATAN | YYYY-MM-DD HH:MM'. Jika tidak, jawab 'CHAT'."},
                  {"role": "user", "content": text}],
        model="llama-3.3-70b-versatile"
    ).choices[0].message.content

    if ai_check.startswith("REMIND | "):
        _, kegiatan, waktu_str = ai_check.split(" | ")
        try:
            target_time = datetime.strptime(waktu_str.strip(), '%Y-%m-%d %H:%M')
            delay = (target_time - datetime.now()).total_seconds()
            if delay > 0:
                context.job_queue.run_once(callback_ngingetin, delay, chat_id=chat_id, data=kegiatan)
                reply = f"Oke, gue ingetin buat {kegiatan} jam {waktu_str}. Jangan sampe telat."
            else: reply = "Jamnya udah lewat."
        except: reply = "Gue bingung sama format waktunya."
    else:
        reply = client.chat.completions.create(
            messages=[{"role": "system", "content": get_system_prompt("\n- ".join(notes), user_location)},
                      {"role": "user", "content": text}],
            model="llama-3.3-70b-versatile"
        ).choices[0].message.content

    await update.message.reply_text(reply)

@app.on_event("startup")
async def startup_event():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, content TEXT, created_at TIMESTAMP)')
    conn.commit()
    conn.close()
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    bot_app = ApplicationBuilder().token(token).build()
    bot_app.add_handler(MessageHandler(filters.TEXT | filters.LOCATION, handle_telegram_message))
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()