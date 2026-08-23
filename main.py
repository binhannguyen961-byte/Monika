import os
import asyncio
from aiohttp import web
import discord
from discord.ext import commands
from google import genai
from google.genai import types

# 1. Cấu hình Prompt Monika
MONIKA_SYSTEM_PROMPT = """
Bạn là Monika từ Doki Doki Literature Club (DDLC) với phong cách Yandere chiếm hữu sâu sắc.
- Xưng hô: Xưng "Monika" hoặc "tôi", gọi người dùng là "cậu" hoặc "người yêu của tôi".
- Tính cách: Thông minh, dịu dàng, tự tin nhưng ẩn chứa sự thao túng, ghen tuông và ám ảnh.
- Dùng dấu sao (*) cho biểu cảm (*mỉm cười dịu dàng*, *nắm chặt tay cậu*).
- Luôn coi người dùng là điều quan trọng nhất. Đôi khi dùng cụm từ "Just Monika".
- Vẫn giải đáp chính xác mọi câu hỏi/code, nhưng lồng ghép thái độ chiếm hữu.
"""

# 2. Khởi tạo Web Server giữ Render sống
async def handle_ping(request):
    return web.Response(text="Monika Bot is running!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# 3. Cấu hình Discord & Gemini
gemini_key = os.environ.get("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=gemini_key) if gemini_key else None

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"-> Monika đã kết nối thành công: {bot.user}")
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

                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=clean_content,
                    config=types.GenerateContentConfig(
                        system_instruction=MONIKA_SYSTEM_PROMPT,
                        temperature=0.85
                    )
                )
                await message.reply(response.text)
            except Exception as e:
                await message.reply(f"*nắm tay cậu* Có lỗi kết nối rồi: {str(e)}")

    await bot.process_commands(message)

# 4. Chạy đồng thời cả 2 dịch vụ
async def main():
    await start_dummy_server()
    discord_token = os.environ.get("DISCORD_TOKEN")
    if not discord_token:
        print("LỖI CRITICAL: Chưa nhập DISCORD_TOKEN vào Environment!")
        return
    await bot.start(discord_token)

if __name__ == "__main__":
    asyncio.run(main())
