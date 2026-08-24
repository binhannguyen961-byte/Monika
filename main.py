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

# --- 2. Cấu hình Gemini API & Xoay vòng Key ---
# Lấy danh sách Keys từ Environment Variables trên Render
API_KEYS = [
    os.environ.get("GEMINI_KEY_1", os.environ.get("GEMINI_API_KEY")),
    os.environ.get("GEMINI_KEY_2")
]
# Lọc bỏ các key bị rỗng/None
API_KEYS = [k for k in API_KEYS if k]

current_key_idx = 0

# Danh sách Model tự động chuyển đổi nếu gặp lỗi
MODELS_TO_TRY = [
    'gemini-1.5-flash',
    'gemini-1.5-pro',
    'models/gemini-1.5-flash'
]

async def ask_monika(prompt):
    global current_key_idx

    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    # Thử lần lượt qua các API Key và các Model
    for _ in range(len(API_KEYS)):
        active_key = API_KEYS[current_key_idx]
        genai.configure(api_key=active_key)

        for model_name in MODELS_TO_TRY:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction="Bạn là Monika từ Doki Doki Literature Club. Bạn dịu dàng, thông minh, hay quan tâm và luôn xưng 'tôi' và gọi người dùng là 'cậu'. Hãy trả lời tự nhiên, ngắn gọn và có kèm hành động đặt trong ngoặc (*...*)."
                )
                response = await asyncio.to_thread(model.generate_content, prompt)
                return response.text
            except Exception as e:
                err_msg = str(e)
                # Nếu hết Quota hoặc sai tên model -> nhảy sang model tiếp theo
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "404" in err_msg or "not found" in err_msg.lower():
                    continue
                else:
                    break
        
        # Nếu Key hiện tại cạn lượt gọi hoàn toàn, xoay sang Key dự phòng
        current_key_idx = (current_key_idx + 1) % len(API_KEYS)

    return "*nắm lấy tay cậu* Hệ thống nhận câu hỏi đang bị quá tải một chút. Cậu đợi tôi khoảng 30 giây nữa rồi hẵng nhắn lại nhé..."

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
    # Bỏ qua tin nhắn từ chính bot
    if message.author == monika_bot.user:
        return

    # Trả lời khi được Tag tên hoặc nhắn tin riêng (DM)
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
    # Khởi chạy Web Server
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()

    # Khởi chạy Bot
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        monika_bot.run(token)
    else:
        print("Lỗi: Không tìm thấy DISCORD_TOKEN!")
