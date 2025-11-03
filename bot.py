import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

# --- تنظیمات ---
TELEGRAM_TOKEN = "8104679047:AAHZkSfs3QEVuiKpn2gjDKytjMEYq5sjXJE"
OPENAI_API_KEY = "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"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)
MODEL = "gpt-4o-mini"
MAX_HISTORY_MESSAGES = 12
chat_histories = {}
hist_lock = threading.Lock()
SYSTEM_PROMPT = "You are a helpful, concise, and polite assistant that replies in Persian if the user writes Persian."

def ensure_history(chat_id):
    with hist_lock:
        if chat_id not in chat_histories:
            chat_histories[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        return chat_histories[chat_id]

def trim_history(history):
    if len(history) <= MAX_HISTORY_MESSAGES:
        return history
    return [history[0]] + history[-(MAX_HISTORY_MESSAGES - 1):]

def simulate_typing_and_delay(bot, chat_id: int, user_text: str, reply_text: str):
    try:
        bot.send_chat_action(chat_id=chat_id, action="typing")
    except:
        pass
    delay = min(max(len(reply_text) * 0.02, 0.3), 3.5) + min(len(user_text) * 0.005, 1.5)
    time.sleep(delay)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ensure_history(chat_id)
    await context.bot.send_message(chat_id=chat_id, text="سلام! خوش اومدی به چت وایپر 😎\nهر پیامی بفرستی پاسخ می‌دم.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with hist_lock:
        chat_histories.pop(chat_id, None)
    await context.bot.send_message(chat_id=chat_id, text="تاریخچهٔ شما پاک شد. تا بعد! 👋")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text or ""
    history = ensure_history(chat_id)

    with hist_lock:
        history.append({"role": "user", "content": user_text})
        chat_histories[chat_id] = trim_history(history)
        messages = chat_histories[chat_id].copy()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        reply_text = response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("خطا در تماس با OpenAI")
        reply_text = "متأسفانه مشکلی پیش آمد. دوباره تلاش کنید."

    try:
        simulate_typing_and_delay(context.bot, chat_id, user_text, reply_text)
        await context.bot.send_message(chat_id=chat_id, text=reply_text)
    except Exception:
        logger.exception("خطا در ارسال پاسخ")

    with hist_lock:
        if chat_id in chat_histories:
            chat_histories[chat_id].append({"role": "assistant", "content": reply_text})
            chat_histories[chat_id] = trim_history(chat_histories[chat_id])

# --- Health server برای keep-alive ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 8000)) + 1
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

async def main():
    import asyncio

    # راه‌اندازی health server در thread جداگانه
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # راه‌اندازی ربات با webhook
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", 8000))
    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:
        await app.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
        await app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES
        )
    else:
        await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())