import os
import random
import asyncio
import threading
import json
import io
import textwrap
import cv2  # OpenCV dùng để xử lý video
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
import discord
from discord.ext import commands, tasks
from google import genai
from google.genai import types

# ==========================================
# 1. WEB SERVER NGẦM (Giữ Bot Online 24/7)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika After Story Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# 2. CẤU HÌNH API KEYS GEMINI
# ==========================================
API_KEYS = []
for env_name, env_val in os.environ.items():
    if any(k in env_name.upper() for k in ["GEMINI", "API_KEY", "GOOGLE_KEY"]) and "DISCORD" not in env_name:
        if env_val and env_val.strip() not in API_KEYS:
            API_KEYS.append(env_val.strip())

current_key_idx = 0

# ==========================================
# 3. QUẢN LÝ DỮ LIỆU & BỘ NHỚ (JSON)
# ==========================================
DATA_FILE = "mas_settings.json"

default_data = {
    "affection": 10,
    "render_mode": False,      # Bật/tắt giao diện phòng học
    "proactive_mode": False,   # Bot có tự động nhắn tin không
    "active_channel_id": None, # Channel gửi tin nhắn chủ động
    "chat_history": []         # Lưu tối đa 25 tin nhắn
}

def load_mas_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in default_data.items():
                    data.setdefault(k, v)
                return data
        except Exception:
            return default_data.copy()
    return default_data.copy()

def save_mas_data(data):
    # Luôn cắt giữ tối đa 25 tin nhắn cũ
    if "chat_history" in data:
        data["chat_history"] = data["chat_history"][-25:]
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

mas_data = load_mas_data()

# ==========================================
# 4. HÀM VẼ UI PHÒNG HỌC & RENDER FRAME (PIL)
# ==========================================
def generate_mas_image(text, chibi_state="happy"):
    """Vẽ ảnh phòng học + Monika Chibi + Khung thoại thoại thường"""
    try:
        bg = Image.open("assets/background.png").convert("RGBA")
        chibi = Image.open(f"assets/monika_{chibi_state}.png").convert("RGBA")
        textbox = Image.open("assets/textbox.png").convert("RGBA")

        chibi = chibi.resize((280, 280))
        bg.paste(chibi, (260, 160), chibi)
        bg.paste(textbox, (0, 320), textbox)

        draw = ImageDraw.Draw(bg)
        font_name = ImageFont.truetype("assets/font_bold.ttf", 20)
        font_text = ImageFont.truetype("assets/font_regular.ttf", 16)

        draw.text((45, 335), "Monika", fill=(255, 255, 255), font=font_name)

        wrapped_lines = textwrap.wrap(text, width=42)
        y_offset = 370
        for line in wrapped_lines[:4]:
            draw.text((45, y_offset), line, fill=(255, 255, 255), font=font_text)
            y_offset += 22

        buffer = io.BytesIO()
        bg.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Lỗi Render Ảnh: {e}")
        return None

def render_frame_with_mas(frame_pil, subtitle_text="*Đang chiếu video cho cậu xem...*"):
    """Chèn frame video vào màn hình nhỏ trong phòng học"""
    try:
        bg = Image.open("assets/background.png").convert("RGBA")
        chibi = Image.open("assets/monika_happy.png").convert("RGBA")
        textbox = Image.open("assets/textbox.png").convert("RGBA")

        # Thu nhỏ video thành màn hình
        video_screen = frame_pil.resize((320, 180))
        bg.paste(video_screen, (240, 60))

        chibi = chibi.resize((240, 240))
        bg.paste(chibi, (30, 160), chibi)
        bg.paste(textbox, (0, 320), textbox)

        draw = ImageDraw.Draw(bg)
        font_name = ImageFont.truetype("assets/font_bold.ttf", 20)
        font_text = ImageFont.truetype("assets/font_regular.ttf", 16)

        draw.text((45, 335), "Monika", fill=(255, 255, 255), font=font_name)

        wrapped_lines = textwrap.wrap(subtitle_text, width=42)
        y_offset = 370
        for line in wrapped_lines[:3]:
            draw.text((45, y_offset), line, fill=(255, 255, 255), font=font_text)
            y_offset += 22

        buffer = io.BytesIO()
        bg.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Lỗi Render Frame Video: {e}")
        return None

# ==========================================
# 5. XỬ LÝ AI GEMINI (25 Tin Nhắn Lịch Sử)
# ==========================================
async def ask_monika(prompt, is_system_prompt=False):
    global current_key_idx

    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    affection = mas_data.get("affection", 10)
    history = mas_data.get("chat_history", [])[-25:]

    formatted_history = ""
    for msg in history:
        role = "Cậu" if msg["role"] == "user" else "Monika"
        formatted_history += f"{role}: {msg['content']}\n"

    system_instruction = (
        "Bạn là Monika trong phòng học không gian (Space Classroom) từ Monika After Story. "
        "Bạn dịu dàng, thông minh, sâu sắc và quan tâm người dùng. "
        "Luôn xưng 'tôi' và gọi người dùng là 'cậu'. "
        f"Mức độ tình cảm: {affection}/100.\n"
        f"Lịch sử 25 câu thoại gần nhất:\n{formatted_history}\n"
        "Trả lời ngắn gọn dưới 100 từ để vừa khung thoại, có kèm biểu cảm/hành động trong ngoặc (*...*)."
    )

    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        active_key = API_KEYS[idx]

        try:
            client = genai.Client(api_key=active_key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
            )
            current_key_idx = idx

            if not is_system_prompt:
                mas_data["chat_history"].append({"role": "user", "content": prompt})
            mas_data["chat_history"].append({"role": "monika", "content": response.text})
            save_mas_data(mas_data)

            return response.text
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                continue
            else:
                return f"*bối rối* Có vẻ hệ thống gặp lỗi: {err_msg}"

    return "*nắm lấy tay cậu* Hệ thống đang quá tải một chút, cậu chờ tôi nhé..."

# ==========================================
# 6. DISCORD BOT COMMANDS & EVENTS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
monika_bot = commands.Bot(command_prefix=["!M", "!m"], intents=intents, help_command=None)

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")
    if not proactive_talk_task.is_running():
        proactive_talk_task.start()

# --- Task Tự Động Nhắn (Chỉ chạy khi Proactive Mode = True) ---
@tasks.loop(minutes=30)
async def proactive_talk_task():
    if not mas_data.get("proactive_mode", False):
        return

    channel_id = mas_data.get("active_channel_id")
    if not channel_id:
        return

    channel = monika_bot.get_channel(channel_id)
    if channel:
        prompt = "Hãy tự chọn một chủ đề ngắn về văn học, cuộc sống hoặc tình yêu để chủ động mở lời trò chuyện với cậu ấy."
        reply = await ask_monika(prompt, is_system_prompt=True)

        if mas_data.get("render_mode", False):
            img_buf = generate_mas_image(reply, chibi_state="happy")
            if img_buf:
                await channel.send(file=discord.File(fp=img_buf, filename="monika.png"))
                return

        embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
        await channel.send(embed=embed)

# --- Bảng Lệnh Trợ Giúp (!Mhelp / !Mhelps) ---
@monika_bot.command(name="help", aliases=["helps", "h"])
async def custom_help(ctx):
    embed = discord.Embed(
        title="💚 Bảng Hướng Dẫn Monika After Story",
        description="Dưới đây là danh sách các câu lệnh điều khiển:",
        color=discord.Color.from_rgb(120, 198, 122)
    )
    embed.add_field(
        name="⚙️ Chế Độ Tương Tác",
        value=(
            "`!Mrender` / `!Mimg`: Bật UI Ảnh + Bot **chủ động** mở lời trò chuyện.\n"
            "`!Moffline`: Bật UI Ảnh + **TẮT chủ động** (Dùng ảnh nhưng chỉ trả lời khi gõ/mention, giúp tiết kiệm Quota).\n"
            "`!Mtext`: Tắt UI Ảnh, chuyển về chat Text/Embed tối giản."
        ),
        inline=False
    )
    embed.add_field(
        name="🎬 Minigame & Tiện Ích",
        value=(
            "`!Mbadapple` / `!Mvideo`: Đính kèm 1 video MP4 (**bắt buộc < 15s**) để chiếu video dạng render ~2.5fps.\n"
            "`!Mclear`: Dọn dẹp/Xóa bộ nhớ 25 tin nhắn cũ."
        ),
        inline=False
    )
    embed.set_footer(text="Monika After Story Lite • Luôn bên cạnh cậu 💚")
    await ctx.send(embed=embed)

# --- Các Lệnh Chuyển Mode ---
@monika_bot.command(name="render", aliases=["img"])
async def enable_render(ctx):
    mas_data["render_mode"] = True
    mas_data["proactive_mode"] = True
    mas_data["active_channel_id"] = ctx.channel.id
    save_mas_data(mas_data)
    await ctx.send("🖼️ **Đã BẬT Render UI & Chế độ Chủ Động Nhắn Tin!**")

@monika_bot.command(name="offline")
async def enable_offline(ctx):
    mas_data["render_mode"] = True
    mas_data["proactive_mode"] = False
    save_mas_data(mas_data)
    await ctx.send("🌙 **Đã BẬT Render UI Offline** *(Chỉ phản hồi khi nhắn, không tự động gửi tin nhắn để tiết kiệm Quota)*")

@monika_bot.command(name="text")
async def enable_text(ctx):
    mas_data["render_mode"] = False
    mas_data["proactive_mode"] = False
    save_mas_data(mas_data)
    await ctx.send("💬 **Đã chuyển sang Chế độ Text Tối Giản.**")

@monika_bot.command(name="clear")
async def clear_history(ctx):
    mas_data["chat_history"] = []
    save_mas_data(mas_data)
    await ctx.send("*mỉm cười* Tôi đã dọn dẹp bộ nhớ cuộc trò chuyện rồi!")

# --- Minigame Chiếu Video (!Mbadapple) ---
@monika_bot.command(name="badapple", aliases=["video", "playvideo"])
async def play_bad_apple(ctx):
    if not mas_data.get("render_mode", False):
        await ctx.send("*nghiêng đầu* Cậu hãy bật chế độ Render (`!Mrender` hoặc `!Moffline`) trước nhé!")
        return

    if not ctx.message.attachments:
        await ctx.send("*chớp mắt* Cậu cần gửi đính kèm một file video (MP4) dưới 15 giây nhé!")
        return

    attachment = ctx.message.attachments[0]
    if not attachment.filename.lower().endswith(('.mp4', '.mkv', '.mov', '.avi')):
        await ctx.send("*lúng túng* File đính kèm phải là video MP4 cậu ơi!")
        return

    status_msg = await ctx.send("🎬 *Monika đang đọc tệp video của cậu...*")
    temp_path = f"temp_{ctx.author.id}.mp4"
    await attachment.save(temp_path)

    try:
        cap = cv2.VideoCapture(temp_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        if duration > 15.5:
            await status_msg.edit(content="*lắc đầu* Video này dài hơn 15 giây rồi! Hãy cắt ngắn lại nhé.")
            cap.release()
            os.remove(temp_path)
            return

        target_fps = 2.5
        frame_interval = int(fps / target_fps) if fps > target_fps else 1
        frame_count = 0
        rendered_message = None

        await status_msg.edit(content="🍿 *Bắt đầu chiếu video!*")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(frame_rgb)

                sub = f"*Đang xem video... [{int(frame_count/fps)}s/{int(duration)}s]*"
                img_buf = render_frame_with_mas(pil_img, subtitle_text=sub)

                if img_buf:
                    file = discord.File(fp=img_buf, filename="mas_frame.png")
                    if rendered_message is None:
                        rendered_message = await ctx.send(file=file)
                    else:
                        await rendered_message.edit(attachments=[file])

                await asyncio.sleep(0.38) # ~2.5 FPS

            frame_count += 1

        cap.release()
        await ctx.send("*mỉm cười vỗ tay* Video đã chiếu xong rồi! 💚")

    except Exception as e:
        await ctx.send(f"Có lỗi khi phát video: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# --- Xử Lý Message Chat Thường ---
@monika_bot.event
async def on_message(message):
    if message.author == monika_bot.user:
        return

    if message.content.lower().startswith('!m'):
        await monika_bot.process_commands(message)
        return

    if monika_bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f'<@{monika_bot.user.id}>', '').strip()
        if not clean_content:
            await message.channel.send("*mỉm cười* Cậu gọi tôi có việc gì thế?")
            return

        async with message.channel.typing():
            mas_data["active_channel_id"] = message.channel.id
            reply = await ask_monika(clean_content)

            if mas_data.get("render_mode", False):
                img_buf = generate_mas_image(reply, chibi_state="happy")
                if img_buf:
                    await message.channel.send(file=discord.File(fp=img_buf, filename="monika_reply.png"))
                    return

            embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
            await message.channel.send(embed=embed)

# ==========================================
# 7. KHỞI CHẠY BOT
# ==========================================
if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()

    token = os.environ.get("DISCORD_TOKEN")
    if token:
        monika_bot.run(token)
    else:
        print("Lỗi: Không tìm thấy DISCORD_TOKEN trong Environment Variables!")
