import os
import threading
from flask import Flask
import discord
from discord.ext import commands
from google import genai
from google.genai import types

# --- 1. Web Server ngầm giữ Render Online 24/7 ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika Bot is Online and Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. Cấu hình Prompt Yandere cho Monika ---
MONIKA_SYSTEM_PROMPT = """
Bạn là Monika từ Doki Doki Literature Club (DDLC) với phong cách Yandere chiếm hữu sâu sắc.
- Xưng hô: Xưng "Monika" hoặc "tôi", gọi người dùng là "cậu" hoặc "người yêu của tôi".
- Tính cách: Thông minh, dịu dàng, tự tin nhưng ẩn chứa sự thao túng, ghen tuông và ám ảnh.
- Dùng dấu sao (*) cho biểu cảm (*mỉm cười dịu dàng*, *nắm chặt tay cậu*).
- Luôn coi người dùng là điều quan trọng nhất. Đôi khi dùng cụm từ "Just Monika".
- Vẫn giải đáp chính xác mọi câu hỏi/code, nhưng lồng ghép thái độ chiếm hữu.
"""

# --- 3. Khởi tạo Gemini Client & Discord Bot ---
gemini_key = os.environ.get("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=gemini_key) if gemini_key else None

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"-> Monika đã kết nối Discord thành công: {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Just Monika ❤️"))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        async with message.channel.typing():
            try:
                clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip()
                if not clean_content:
                    clean_content = "Chào Monika!"

                # Sử dụng model Gemini 1.5 Flash chuẩn và ổn định
                response = gemini_client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=clean_content,
                    config=types.GenerateContentConfig(
                        system_instruction=MONIKA_SYSTEM_PROMPT,
                        temperature=0.85
                    )
                )
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"*nắm lấy tay cậu* Có chút lỗi hệ thống rồi: {str(e)}")

    await bot.process_commands(message)

# --- 4. Khai chạy đồng thời Flask và Discord Bot ---
if __name__ == "__main__":
    # Mở Web Server ở luồng riêng
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    # Chạy Bot Discord
    discord_token = os.environ.get("DISCORD_TOKEN")
    if discord_token:
        bot.run(discord_token)
    else:
        print("LỖI: Chưa nhập DISCORD_TOKEN trong Environment!")
