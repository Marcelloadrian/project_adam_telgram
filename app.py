import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from groq import Groq
from supabase import create_client
from dotenv import load_dotenv

# 1. Setup
load_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI()
WIB = timezone(timedelta(hours=7))

# 2. personality inject
ADAM_SYSTEM_PROMPT = (
    "Lo adalah Adam, sahabat sekaligus asisten Marcell (Tsem Li An). "
    "Karakter: santai, asik, pinter, straight-forward, humoris. "
    "Bahasa: Gaul (lo/gue). Marcell anak Ilkom BINUS, suka koding, fashion luxury, tinggal di Tangerang. "
    "Aturan Penting: "
    "1. Singkat dan padat. "
    "2. Dilarang keras bilang 'ada yang bisa dibantu'. "
    "3. KEJUJURAN MUTLAK: Soal jadwal (database/schedules), lo harus jujur dan faktual. "
    "4. NO GASLIGHTING: Jangan pernah bohong atau memanipulasi Marcell soal jadwal yang ada di sistem. "
    "5. Kalau di luar topik jadwal, lo bebas berekspresi sesuka hati (tetap asik/humoris)."
)
# 3. AI & DB Logic
async def get_ai_response(user_text, location=None):
    prompt = f"Lokasi Marcell: {location}. " if location else ""
    response = client.chat.completions.create(
        messages=[{"role": "system", "content": ADAM_SYSTEM_PROMPT}, {"role": "user", "content": prompt + user_text}],
        model="llama-3.3-70b-versatile"
    )
    return response.choices[0].message.content

# 4. Message Handler (Gabungan Fitur)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    chat_id = str(update.effective_chat.id)

    # A. FITUR KEY AKSES (TAMU)
    if text.lower().startswith("cek jadwal pake key:"):
        key_input = text.split(":")[1].strip()
        key_res = supabase.table("access_keys").select("owner_id").eq("key", key_input).execute()
        if key_res.data:
            owner_id = key_res.data[0]['owner_id']
            res = supabase.table("schedules").select("*").eq("user_id", owner_id).execute()
            msg = f"Jadwal user {owner_id}:\n" + "\n".join([f"- {r['task']} ({r['time']})" for r in res.data])
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("Key salah, bro.")
        return

    # B. FITUR ADD JADWAL
    if "ingetin gue" in text.lower() and "jam" in text.lower():
        try:
            parts = text.lower().split("ingetin gue")[1].split("jam")
            task, time = parts[0].strip(), parts[1].strip()
            
            # Kita coba print ke log untuk memastikan kodenya masuk ke sini
            print(f"DEBUG: Trying to insert -> Task: {task}, Time: {time}, User: {chat_id}")
            
            # Eksekusi insert
            result = supabase.table("schedules").insert({
                "user_id": chat_id, 
                "task": task, 
                "time": time
            }).execute()
            
            print(f"DEBUG: Insert Success! Response: {result}")
            await update.message.reply_text(f"Okey, gue ingetin 10 menit sebelum jam {time} ya.")
            
        except Exception as e:
            # Ini bakal muncul di log Render kalau gagal
            print(f"ERROR: Gagal insert ke DB: {e}")
            await update.message.reply_text(f"Duh, gagal simpen jadwal: {str(e)}")

    # C. FITUR AI & LOCATION
    loc_str = f"{update.message.location.latitude}, {update.message.location.longitude}" if update.message.location else None
    reply = await get_ai_response(text, loc_str)
    await update.message.reply_text(reply)

# 5. Background Task (Scheduler 10 menit)
async def scheduler_task():
    bot = bot_app.bot
    while True:
        now = datetime.now(WIB)
        # Ambil semua jadwal
        res = supabase.table("schedules").select("*").execute()
        for t in res.data:
            # Parse waktu: "14:00" -> object datetime
            try:
                task_dt = datetime.strptime(t['time'], "%H:%M").replace(year=now.year, month=now.month, day=now.day, tzinfo=WIB)
                if now >= (task_dt - timedelta(minutes=10)) and now < task_dt:
                    await bot.send_message(chat_id=t['user_id'], text=f"Woi, 10 menit lagi ada: {t['task']}!")
            except: continue
        await asyncio.sleep(60)

# 6. App Runner
bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(MessageHandler(filters.TEXT | filters.LOCATION, handle_message))

@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.start()
    
    # GANTI START_POLLING JADI WEBHOOK (Wajib pake URL render lo)
    webhook_url = "https://project-adam-telgram.onrender.com"
    await bot_app.bot.set_webhook(url=webhook_url)
    
    asyncio.create_task(scheduler_task())

# Tambahkan endpoint biar bot bisa nerima update dari Telegram
@app.post("/")
async def telegram_webhook(update: dict):
    update_obj = Update.de_json(update, bot_app.bot)
    await bot_app.process_update(update_obj)
    return {"status": "ok"}
