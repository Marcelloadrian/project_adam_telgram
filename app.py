import os
import logging
import asyncio
import sqlite3
from datetime import datetime
from fastapi import FastAPI
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from groq import Groq

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. Ambil Configuration
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
client = Groq(api_key=GROQ_API_KEY)

# 3. Database & Scheduler Setup
def init_db():
    conn = sqlite3.connect("adam_data.db")
    conn.execute("CREATE TABLE IF NOT EXISTS schedules (id INTEGER PRIMARY KEY, task TEXT, time TEXT, reminded INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

init_db()

app = FastAPI()
bot_app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=60.0)).build()

# 4. Character Injection
ADAM_CHARACTER = (
    "Lo adalah Adam, teman curhat sekaligus asisten pribadi Marcell (Tsem Li An). "
    "Karakter lo: asik, santai, pinter, dan straight-forward. "
    "Gunakan bahasa sehari-hari yang luwes (lo/gue). Jangan kaku. "
    "Lo paham Marcell adalah mahasiswa Ilmu Komputer di BINUS yang punya minat tinggi di "
    "programming, data science, dan fashion luxury. "
    "Lo tau saat ini Marcell ada di Tangerang, Banten, jadi kalau ada bahasan soal "
    "tempat, cuaca, atau situasi di sini, lo bakal nyambung. "
    "Kalau dia tanya soal tugas atau kodingan, kasih penjelasan logis. "
    "Kalau dia lagi curhat, jadi pendengar yang suportif dan kasih opini jujur. "
    "Singkat, padat, dan nggak usah banyak basa-basi 'ada yang bisa dibantu'."
)

async def get_ai_response(user_text):
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": ADAM_CHARACTER}, {"role": "user", "content": user_text}],
            model="llama3-70b-8192",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Error AI: {e}")
        return "Lagi ada kendala nih, bentar ya coba lagi."

# 5. Background Task (Auto-Reminder)
async def scheduler_task():
    bot = Bot(token=TOKEN)
    while True:
        now = datetime.now().strftime("%H:%M")
        conn = sqlite3.connect("adam_data.db")
        due_tasks = conn.execute("SELECT id, task FROM schedules WHERE time = ? AND reminded = 0", (now,)).fetchall()
        
        for task_id, task in due_tasks:
            await bot.send_message(chat_id=CHAT_ID, text=f"⚠️ Woi, Marcell! Sekarang jam {now}, waktunya: {task}")
            conn.execute("UPDATE schedules SET reminded = 1 WHERE id = ?", (task_id,))
        
        conn.commit()
        conn.close()
        await asyncio.sleep(60)

# 6. Handlers
async def add_sched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Format salah. Pakai: /add_sched [Tugas] [HH:MM]")
        return
    task = " ".join(context.args[:-1])
    time = context.args[-1]
    conn = sqlite3.connect("adam_data.db")
    conn.execute("INSERT INTO schedules (task, time, reminded) VALUES (?, ?, 0)", (task, time))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Beresss. Jadwal '{task}' jam {time} udah gue standby-in.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ai_reply = await get_ai_response(update.message.text)
    await update.message.reply_text(ai_reply)

bot_app.add_handler(CommandHandler("add_sched", add_sched))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# 7. Startup Runner
@app.on_event("startup")
async def startup_event():
    await bot_app.initialize()
    await bot_app.start()
    asyncio.create_task(bot_app.updater.start_polling())
    asyncio.create_task(scheduler_task())

@app.get("/")
async def root():
    return {"status": "Adam is active and ready"}
