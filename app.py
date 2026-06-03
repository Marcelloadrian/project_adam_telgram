import os
import asyncio
import logging
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

# 2. Personality
ADAM_SYSTEM_PROMPT = (
    "Lo adalah Adam, sahabat sekaligus asisten Marcell (Tsem Li An). "
    "Karakter: santai, asik, pinter, straight-forward, humoris. "
    "Bahasa: Gaul (lo/gue). Marcell anak Ilkom BINUS, suka koding, fashion luxury, tinggal di Tangerang. "
    "Aturan Penting: "
    "1. Singkat dan padat. "
    "2. Dilarang keras bilang 'ada yang bisa dibantu'. "
    "3. KEJUJURAN MUTLAK: Soal jadwal, lo harus jujur. "
    "4. NO GASLIGHTING: Jangan pernah bohong atau manipulasi jadwal. "
    "5. Jika tidak ada jadwal di sistem, akui saja, jangan asal buat jadwal."
)

async def get_ai_response(user_text, location=None):
    prompt = f"Lokasi Marcell: {location}. " if location else ""
    response = client.chat.completions.create(
        messages=[{"role": "system", "content": ADAM_SYSTEM_PROMPT}, {"role": "user", "content": prompt + user_text}],
        model="llama-3.3-70b-versatile"
    )
    return response.choices[0].message.content

# 4. Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text
    chat_id = str(update.effective_chat.id)

    # A. CEK JADWAL (Key)
    if text.lower().startswith("cek jadwal pake key:"):
        key_input = text.split(":")[1].strip()
        key_res = supabase.table("access_keys").select("owner_id").eq("key", key_input).execute()
        if key_res.data:
            owner_id = key_res.data[0]['owner_id']
            res = supabase.table("schedules").select("*").eq("user_id", owner_id).execute()
            msg = f"Jadwal user {owner_id}:\n" + "\n".join([f"- {r['task']} ({r['time']})" for r in res.data]) if res.data else "Lagi kosong, bro."
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("Key salah, bro.")
        return

    # B. ADD JADWAL
    if "ingetin gue" in text.lower() and "jam" in text.lower():
        try:
            parts = text.lower().split("ingetin gue")[1].split("jam")
            task, time = parts[0].strip(), parts[1].strip()
            
            supabase.table("schedules").insert({"user_id": chat_id, "task": task, "time": time}).execute()
            await update.message.reply_text(f"Okey, gue ingetin 10 menit sebelum jam {time} ya.")
            return # Keluar setelah berhasil simpan
        except Exception as e:
            print(f"ERROR DB: {e}")
            await update.message.reply_text("Duh, gagal simpen jadwal.")
            return

    # C. AI CHAT
    loc = update.message.location
    loc_str = f"{loc.latitude}, {loc.longitude}" if loc else None
    reply = await get_ai_response(text, loc_str)
    await update.message.reply_text(reply)

# 5. Background Scheduler
async def scheduler_task():
    while True:
        try:
            now = datetime.now(WIB)
            res = supabase.table("schedules").select("*").execute()
            for t in res.data:
                task_dt = datetime.strptime(t['time'], "%H:%M").replace(year=now.year, month=now.month, day=now.day, tzinfo=WIB)
                if now >= (task_dt - timedelta(minutes=10)) and now < task_dt:
                    await bot_app.bot.send_message(chat_id=t['user_id'], text=f"Woi, 10 menit lagi ada: {t['task']}!")
        except Exception as e:
            print(f"Scheduler Error: {e}")
        await asyncio.sleep(60)

# 6. Runner
bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(MessageHandler(filters.TEXT | filters.LOCATION, handle_message))

@app.on_event("startup")
async def startup():
    await bot_app.initialize()
    await bot_app.start()
    
    # GANTI KE WEBHOOK - Pastikan URL ini sesuai dengan domain Render lo
    webhook_url = "https://project-adam-telgram.onrender.com"
    await bot_app.bot.set_webhook(url=webhook_url)
    
    asyncio.create_task(scheduler_task())

@app.post("/")
async def telegram_webhook(update: dict):
    update_obj = Update.de_json(update, bot_app.bot)
    await bot_app.process_update(update_obj)
    return {"status": "ok"}
