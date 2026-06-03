import os
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from groq import Groq

# 1. Setup Logging
logging.basicConfig(level=logging.INFO)

# 2. Configuration
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") # Masukin ID dari @getmyid_bot
client = Groq(api_key=GROQ_API_KEY)
app = FastAPI()

# 3. Personality & AI Setup
ADAM_SYSTEM_PROMPT = (
    "Lo adalah Adam, asisten pribadi sekaligus sahabat Marcell (Tsem Li An). "
    "Karakter: santai, asik, pinter, straight-forward, dan punya selera humor. "
    "Bahasa: Gaul (lo/gue), nggak kaku. Marcell anak Ilkom BINUS, suka koding (Python/Data Science) "
    "dan fashion luxury. Marcell tinggal di Tangerang. "
    "Kalau dia tanya kodingan, kasih solusi logis. Kalau tanya makan, kasih rekomendasi di Tangerang. "
    "Aturan: Singkat, padat, jangan pernah bilang 'ada yang bisa dibantu'."
)

def init_db():
    conn = sqlite3.connect("adam_data.db")
    conn.execute("CREATE TABLE IF NOT EXISTS schedules (id INTEGER PRIMARY KEY, task TEXT, time TEXT, reminded INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

init_db()

async def get_ai_response(user_text, location=None):
    prompt = f"Lokasi Marcell: {location}. " if location else ""
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": ADAM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt + user_text}
        ],
        model="llama-3.3-70b-versatile"
    )
    return response.choices[0].message.content

# 4. Handlers
async def add_sched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Format: /add_sched [Tugas] [HH:MM]")
        return
    task, time = " ".join(context.args[:-1]), context.args[-1]
    conn = sqlite3.connect("adam_data.db")
    conn.execute("INSERT INTO schedules (task, time, reminded) VALUES (?, ?, 0)", (task, time))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Okey, gue ingetin 10 menit sebelum jam {time} ya.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc_str = None
    if update.message.location:
        loc_str = f"{update.message.location.latitude}, {update.message.location.longitude}"
    
    reply = await get_ai_response(update.message.text or "Yo", loc_str)
    await update.message.reply_text(reply)

# 5. Background Task (Scheduler)
async def scheduler_task():
    bot = bot_app.bot
    while True:
        now = datetime.now()
        conn = sqlite3.connect("adam_data.db")
        tasks = conn.execute("SELECT id, task, time FROM schedules WHERE reminded = 0").fetchall()
        
        for t_id, task, t_time in tasks:
            task_dt = datetime.strptime(t_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            if now >= (task_dt - timedelta(minutes=10)) and now < task_dt:
                await bot.send_message(chat_id=CHAT_ID, text=f"Woi, 10 menit lagi ada: {task}!")
                conn.execute("UPDATE schedules SET reminded = 1 WHERE id = ?", (t_id,))
        
        conn.commit()
        conn.close()
        await asyncio.sleep(60)

# 6. App Runner
bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(CommandHandler("add_sched", add_sched))
bot_app.add_handler(MessageHandler(filters.TEXT | filters.LOCATION, handle_message))

@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    asyncio.create_task(scheduler_task())

@app.get("/")
async def root():
    return {"status": "Adam is active"}
