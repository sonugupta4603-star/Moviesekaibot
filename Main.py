import os
import base64
import threading
from flask import Flask
import telebot
from openai import OpenAI

# 1. Environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN")
PORT = int(os.environ.get("PORT", 8080))
MODEL_NAME = "deepseek-ai/DeepSeek-V4.1-Flash:novita"

# 2. Flask web server for Render.com port binding and health checks
app = Flask(__name__)

@app.route("/")
def index():
    return "Telegram Bot is running and healthy!"

@app.route("/health")
def health():
    return {"status": "ok", "bot_configured": bool(BOT_TOKEN and HF_TOKEN)}

# 3. Initialize OpenAI client with Hugging Face Router
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN or "dummy_key",
)

# 4. Initialize Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None


def send_long_message(chat_id, text, reply_to_message_id=None):
    """Splits messages exceeding Telegram's 4096 character limit into chunks."""
    max_len = 4000
    for i in range(0, len(text), max_len):
        chunk = text[i:i + max_len]
        bot.send_message(
            chat_id,
            chunk,
            reply_to_message_id=reply_to_message_id if i == 0 else None,
        )


if bot:
    @bot.message_handler(commands=["start", "help"])
    def handle_start(message):
        welcome_text = (
            "👋 Hello! I am your AI chatting bot powered by Hugging Face.\n\n"
            "💬 Send me any text message to chat.\n"
            "📷 Send me an image/photo (with optional caption) to analyze it!"
        )
        bot.reply_to(message, welcome_text)

    @bot.message_handler(content_types=["text"])
    def handle_text(message):
        if not HF_TOKEN:
            bot.reply_to(message, "⚠️ HF_TOKEN is not configured in environment variables.")
            return

        try:
            bot.send_chat_action(message.chat.id, "typing")

            chat_completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": message.text,
                    }
                ],
            )

            reply = chat_completion.choices[0].message.content
            if reply:
                send_long_message(message.chat.id, reply, message.message_id)
            else:
                bot.reply_to(message, "Received an empty response from the AI model.")
        except Exception as e:
            print(f"Error processing text message: {e}")
            bot.reply_to(message, f"⚠️ Error: {str(e)}")

    @bot.message_handler(content_types=["photo"])
    def handle_photo(message):
        if not HF_TOKEN:
            bot.reply_to(message, "⚠️ HF_TOKEN is not configured in environment variables.")
            return

        try:
            bot.send_chat_action(message.chat.id, "typing")

            # Fetch the highest resolution photo
            photo = message.photo[-1]
            file_info = bot.get_file(photo.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            # Convert to Base64 data URL
            base64_image = base64.b64encode(downloaded_file).decode("utf-8")
            image_data_url = f"data:image/jpeg;base64,{base64_image}"

            caption = message.caption if message.caption else "Describe this image in detail."

            chat_completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": caption,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url,
                                },
                            },
                        ],
                    }
                ],
            )

            reply = chat_completion.choices[0].message.content
            if reply:
                send_long_message(message.chat.id, reply, message.message_id)
            else:
                bot.reply_to(message, "Received an empty response from the AI model.")
        except Exception as e:
            print(f"Error processing image message: {e}")
            bot.reply_to(message, f"⚠️ Error: {str(e)}")


def run_flask():
    """Runs the Flask web server to satisfy Render.com's port check."""
    print(f"Starting Flask server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    # Start Flask in a background thread for Render port binding and health check pings
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    if not BOT_TOKEN:
        print("⚠️ Warning: BOT_TOKEN is missing. Please set BOT_TOKEN in environment variables.")
        flask_thread.join()
    else:
        print("🤖 Telegram Bot polling started...")
        bot.infinity_polling(skip_pending=True)
