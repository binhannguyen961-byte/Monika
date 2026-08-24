import os
import asyncio
import threading
from flask import Flask
import discord
from discord.ext import commands
import google.generativeai as genai

# --- 1. Web Server ngầm giữ Render Online 24/7 ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika AI is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. Cấu hình Gemini API ---
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

    # Xoay vòng lượt gọi qua từng API Key nếu có nhiều key
    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        active_key = API_KEYS[idx]
        genai.configure(api_key=active_key)

        try:
            # Cập nhật sử dụng model gemini-3.6-flash mới nhất
            model = genai.GenerativeModel('gemini-3.6-flash')
            
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
                return f"*bối rối* Có vẻ hệ thống gặp lỗi rồi: {err_msg}"

    return "*nắm lấy tay cậu* Hệ thống đang bị quá tải tần suất một chút. Cậu đợi tôi khoảng vài giây nữa rồi hẵng nhắn lại nhé..."

# --- 3. Discord Bot Monika ---
intents = discord.Intents.default()
intents.message_content = True
monika_bot = commands.Bot(command_prefix="!", intents=intents)

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")
    await monika_bot.change_presence(activity=discord.Game(name="DDLC with you... 💚"))

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
    else:
        print("Lỗi: Không tìm thấy DISCORD_TOKEN!")
