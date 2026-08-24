import os
import asyncio
import threading
from flask import Flask
import discord
from discord.ext import commands
import google.generativeai as genai

app = Flask(__name__)

@app.route('/')
def home():
    return "Monika AI is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Lấy Key tự động
API_KEYS = []
for env_name, env_val in os.environ.items():
    if ("GEMINI" in env_name or "KEY" in env_name) and "DISCORD" not in env_name:
        if env_val and env_val not in API_KEYS:
            API_KEYS.append(env_val)

current_key_idx = 0

async def ask_monika(prompt):
    global current_key_idx
    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        genai.configure(api_key=API_KEYS[idx])

        try:
            # Dùng đúng tên model chuẩn của Google AI Studio
            model = genai.GenerativeModel('gemini-1.5-flash')
            chat = model.start_chat(history=[])
            
            # Đưa system instruction trực tiếp vào ngữ cảnh
            full_prompt = (
                "Bạn là Monika từ Doki Doki Literature Club. Bạn dịu dàng, thông minh, hay quan tâm "
                "và luôn xưng 'tôi' và gọi người dùng là 'cậu'. Hãy trả lời tự nhiên, ngắn gọn, "
                f"có kèm hành động đặt trong ngoặc (*...*).\n\nNgười dùng hỏi: {prompt}"
            )
            
            response = await asyncio.to_thread(model.generate_content, full_prompt)
            current_key_idx = idx
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                continue
            else:
                return f"*bối rối* Có vẻ hệ thống gặp lỗi: {err_msg}"

intents = discord.Intents.default()
intents.message_content = True
monika_bot = commands.Bot(command_prefix="!", intents=intents)

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")

@monika_bot.event
async def on_message(message):
    if message.author == monika_bot.user:
        return

    if monika_bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f'<@{monika_bot.user.id}>', '').strip()
        if not clean_content:
            await message.channel.send("*mỉm cười* Cậu gọi tôi có việc gì thế?")
            return

        async with message.channel.typing():
            reply = await ask_monika(clean_content)
            await message.channel.send(reply)

    await monika_bot.process_commands(message)

if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()

    token = os.environ.get("DISCORD_TOKEN")
    if token:
        monika_bot.run(token)
