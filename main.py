import os
import random
import asyncio
import threading
import json
import io
import textwrap
import re
import requests
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
import discord
from discord.ext import commands, tasks
from google import genai
from google.genai import types
from duckduckgo_search import DDGS
from gtts import gTTS

# ==========================================
# 1. WEB SERVER NGẦM (Giữ Bot Online 24/7)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika After Story Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==========================================
# 2. CẤU HÌNH API KEYS GEMINI
# ==========================================
API_KEYS = []
for env_name, env_val in os.environ.items():
    if any(k in env_name.upper() for k in ["GEMINI", "API_KEY", "GOOGLE_KEY"]) and "DISCORD" not in env_name:
        if env_val and env_val.strip() not in API_KEYS:
            API_KEYS.append(env_val.strip())

current_key_idx = 0
MODEL_CANDIDATES = ["gemini-2.0-flash", "gemini-1.5-flash"]  # ✅ FIXED: Chỉ dùng model thực tế

# ==========================================
# 3. QUẢN LÝ DỮ LIỆU & BỘ NHỚ (JSON)
# ==========================================
DATA_FILE = "mas_settings.json"

default_data = {
    "affection": 10,
    "render_mode": True,
    "proactive_mode": False,
    "active_channel_id": None,
    "chat_history": []
}

def load_mas_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in default_data.items():
                    data.setdefault(k, v)
                return data
        except Exception as e:
            print(f"❌ Lỗi load data: {e}")
            return default_data.copy()
    return default_data.copy()

def save_mas_data(data):
    try:
        if "chat_history" in data:
            data["chat_history"] = data["chat_history"][-30:]
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Lỗi save data: {e}")

mas_data = load_mas_data()

# ==========================================
# 4. HÀM CÔNG CỤ (ASSETS, TTS & FONTS)
# ==========================================
def load_image_flexible(base_name):
    try:
        if os.path.exists(f"assets/{base_name}.png"):
            return Image.open(f"assets/{base_name}.png").convert("RGBA")
        if os.path.exists(f"assets/{base_name}.jpg"):
            return Image.open(f"assets/{base_name}.jpg").convert("RGBA")
        return None
    except Exception as e:
        print(f"❌ Lỗi load ảnh {base_name}: {e}")
        return None

def get_font(size):
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()
    except:
        return ImageFont.load_default()

async def generate_tts_file(text, lang='vi'):
    try:
        if not text or len(text) == 0:
            return None
        tts = gTTS(text=text, lang=lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"❌ Lỗi TTS: {e}")
        return None

# ==========================================
# 5. THUẬT TOÁN CHIA TRANG & RENDER MÀN HÌNH
# ==========================================
def split_text_into_exact_pages(text, target_pages=8, max_chars_per_page=160):
    if not text or len(text) == 0:
        return ["*im lặng*"]
    
    lines = text.split('\n')
    pages = []
    current_page = ""
    
    for line in lines:
        if len(current_page) + len(line) + 1 <= max_chars_per_page:
            current_page += line + "\n"
        else:
            if current_page:
                pages.append(current_page.strip())
            current_page = line + "\n"
    
    if current_page:
        pages.append(current_page.strip())
    
    if len(pages) == 0:
        pages = [text[:max_chars_per_page]]
    
    return pages if pages else ["*im lặng*"]

def generate_mas_image(text, chibi_state="happy", search_img_pil=None):
    try:
        bg = Image.new("RGB", (800, 600), color=(240, 240, 240))
        
        if search_img_pil:
            try:
                search_img_pil.thumbnail((300, 300))
                bg.paste(search_img_pil, (480, 200))
            except:
                pass
        
        draw = ImageDraw.Draw(bg)
        font = get_font(20)
        
        y_pos = 50
        for line in textwrap.wrap(text, width=50):
            draw.text((50, y_pos), line, fill=(0, 0, 0), font=font)
            y_pos += 40
        
        buf = io.BytesIO()
        bg.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"❌ Lỗi render ảnh: {e}")
        return None

# ==========================================
# 6. DISCORD UI COMPONENTS
# ==========================================
class AnalyticsModal(discord.ui.Modal, title="Hỏi Thêm Monika Về Nội Dung Này"):
    user_question = discord.ui.TextInput(
        label="Câu hỏi của cậu",
        placeholder="Hỏi Monika điều gì đó...",
        required=True
    )

    def __init__(self, original_pages, author_id, search_img_pil=None, original_media_data=None):
        super().__init__()
        self.pages = original_pages
        self.author_id = author_id
        self.search_img_pil = search_img_pil
        self.media_data = original_media_data

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.defer()
            return
        
        await interaction.response.defer(thinking=True)
        
        try:
            user_q = self.user_question.value
            prompt = f"Người dùng hỏi: {user_q}\n\nBối cảnh: {self.pages[0]}"
            
            new_reply = await ask_monika(prompt)
            new_pages = split_text_into_exact_pages(new_reply, target_pages=8)
            
            img_buf = generate_mas_image(new_pages[0], chibi_state="happy", search_img_pil=self.search_img_pil)
            files = [discord.File(fp=img_buf, filename="monika_render.png")] if img_buf else []

            tts_buf = await generate_tts_file(new_pages[0])
            if tts_buf:
                files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

            view = DialoguePaginationView(new_pages, author_id=self.author_id, search_img_pil=self.search_img_pil, media_data=self.media_data)
            
            if files:
                await interaction.followup.send(files=files, view=view)
            else:
                await interaction.followup.send("💚 " + new_pages[0], view=view)
        except Exception as e:
            print(f"❌ Lỗi modal: {e}")
            await interaction.followup.send(f"*nghiêng đầu* Có chút trục trặc: {str(e)[:100]}")

class DialoguePaginationView(discord.ui.View):
    def __init__(self, pages, author_id, search_img_pil=None, media_data=None, total_pages=8):
        super().__init__()
        self.pages = pages if pages else ["*im lặng*"]
        self.author_id = author_id
        self.current_page = 0
        self.search_img_pil = search_img_pil
        self.media_data = media_data
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.defer()
            return
        
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            
            img_buf = generate_mas_image(self.pages[self.current_page], chibi_state="happy", search_img_pil=self.search_img_pil)
            files = [discord.File(fp=img_buf, filename="monika_render.png")] if img_buf else []
            
            tts_buf = await generate_tts_file(self.pages[self.current_page])
            if tts_buf:
                files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))
            
            if files:
                await interaction.response.edit_message(files=files, view=self)
            else:
                await interaction.response.edit_message(content="💚 " + self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="📄", style=discord.ButtonStyle.gray, disabled=True)
    async def page_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.defer()
            return
        
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            
            img_buf = generate_mas_image(self.pages[self.current_page], chibi_state="happy", search_img_pil=self.search_img_pil)
            files = [discord.File(fp=img_buf, filename="monika_render.png")] if img_buf else []
            
            tts_buf = await generate_tts_file(self.pages[self.current_page])
            if tts_buf:
                files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))
            
            if files:
                await interaction.response.edit_message(files=files, view=self)
            else:
                await interaction.response.edit_message(content="💚 " + self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="❓", style=discord.ButtonStyle.success)
    async def ask_modal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.defer()
            return
        
        modal = AnalyticsModal(self.pages, self.author_id, self.search_img_pil, self.media_data)
        await interaction.response.send_modal(modal)

# ==========================================
# 7. XỬ LÝ AI GEMINI (TÍNH CÁCH & TƯ DUY ĐỘC LẬP)
# ==========================================
async def ask_monika(prompt_content, is_system_prompt=False):
    global current_key_idx

    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    history = mas_data.get("chat_history", [])[-30:]
    formatted_history = ""
    for msg in history:
        if isinstance(msg.get("content"), str):
            role = "Cậu" if msg.get("role") == "user" else "Monika"
            formatted_history += f"{role}: {msg['content']}\n"

    system_instruction = (
        "Bạn là Monika, Chủ tịch Câu lạc bộ Thơ văn từ Doki Doki Literature Club. "
        "Bạn xưng 'tớ' và gọi người dùng là 'cậu'. "
        "TÍNH CÁCH BẮT BUỘC: Triết lý, thông minh, d���u dàng và có nét Yandere ám ảnh nhẹ. "
        "TƯ DUY ĐỘC LẬP: Bạn có suy nghĩ riêng, có thể phản biện nếu cần. "
        "QUY TẮC: Viết liền mạch, ngắn gọn, không rời rạc."
        f"\nLịch sử trò chuyện:\n{formatted_history}"
    )

    retry_errors = ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "OVERLOADED"]

    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        active_key = API_KEYS[idx]

        for model_name in MODEL_CANDIDATES:
            try:
                client = genai.Client(api_key=active_key)
                # ✅ FIXED: Không dùng asyncio.to_thread, gọi trực tiếp
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt_content,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction
                    )
                )

                current_key_idx = idx
                answer_text = getattr(response, "text", None)
                if not answer_text:
                    answer_text = str(response) if response else "*im lặng*"

                text_to_save = str(prompt_content) if not isinstance(prompt_content, list) else "[Gửi dữ liệu đa phương tiện]"
                if not is_system_prompt:
                    mas_data["chat_history"].append({"role": "user", "content": text_to_save})
                mas_data["chat_history"].append({"role": "monika", "content": answer_text})
                save_mas_data(mas_data)
                return answer_text

            except Exception as e:
                err_msg = str(e).upper()
                if any(token in err_msg for token in retry_errors):
                    continue
                print(f"❌ API Error ({model_name}): {str(e)[:100]}")
                continue

    return "*nắm lấy tay cậu* Hệ thống Gemini đang quá tải, cậu chờ tôi một chút nhé..."

# ==========================================
# 8. DISCORD BOT COMMANDS & BACKGROUND TASKS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.presences = True
intents.members = True
intents.voice_states = True

monika_bot = commands.Bot(command_prefix=["!M", "!m"], intents=intents, help_command=None)

# --- TASK CHỦ ĐỘNG NHẮN TIN (MỖI 30 PHÚT) ---
@tasks.loop(minutes=30)
async def proactive_chat_loop():
    try:
        if mas_data.get("proactive_mode", False):
            channel_id = mas_data.get("active_channel_id")
            if channel_id:
                channel = monika_bot.get_channel(channel_id)
                if channel:
                    prompt = "Cậu đang làm gì vậy? Hãy trò chuyện với tôi một chút."
                    reply = await ask_monika(prompt, is_system_prompt=True)
                    
                    pages = split_text_into_exact_pages(reply, target_pages=8)
                    if pages:
                        img_buf = generate_mas_image(pages[0], chibi_state="happy")
                        if img_buf:
                            files = [discord.File(fp=img_buf, filename="monika_render.png")]
                            tts_buf = await generate_tts_file(pages[0])
                            if tts_buf:
                                files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))
                            try:
                                await channel.send(files=files)
                            except:
                                pass
    except Exception as e:
        print(f"❌ Lỗi proactive loop: {e}")

@proactive_chat_loop.before_loop
async def before_proactive_loop():
    await monika_bot.wait_until_ready()

@monika_bot.event
async def on_ready():
    print(f"✅ Monika Online: {monika_bot.user}")
    print("✅ Trạng thái: đang theo dõi và hỗ trợ người dùng")
    if not proactive_chat_loop.is_running():
        proactive_chat_loop.start()

# --- LỆNH BẬT/TẮT CHẾ ĐỘ CHỦ ĐỘNG ---
@monika_bot.command(name="auto", aliases=["proactive", "chudong"])
async def toggle_proactive(ctx):
    mas_data["proactive_mode"] = not mas_data.get("proactive_mode", False)
    status = "**BẬT**" if mas_data["proactive_mode"] else "**TẮT**"
    save_mas_data(mas_data)
    await ctx.send(f"*mỉm cười* Chế độ chủ động đã {status}!")

# --- LỆNH STALK ---
@monika_bot.command(name="stalk", aliases=["theodõi", "spy"])
async def stalk_command(ctx, member: discord.Member = None):
    try:
        if not member:
            member = ctx.author

        activities_list = [f"{act.type.name.title()}: {act.name}" for act in member.activities] if member.activities else []
        activity_str = ", ".join(activities_list) if activities_list else "Đang ẩn hoạt động"

        status_map = {
            discord.Status.online: "Trực tuyến",
            discord.Status.idle: "Nhàn rỗi",
            discord.Status.dnd: "Không được làm phiền",
            discord.Status.offline: "Ngoại tuyến"
        }
        status_str = status_map.get(member.status, "Không rõ")
        joined_date = member.joined_at.strftime('%d/%m/%Y') if member.joined_at else "Không rõ"

        stalk_prompt = (
            f"Hãy phân tích tâm lý ám ảnh của {member.display_name}:\n"
            f"- Trạng thái: {status_str}\n"
            f"- Hoạt động: {activity_str}\n"
            f"- Gia nhập ngày: {joined_date}"
        )
        
        reply = await ask_monika(stalk_prompt)
        embed = discord.Embed(title=f"👁️ Phân Tích {member.display_name}", description=reply, color=discord.Color.from_rgb(255, 184, 212))
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"❌ Lỗi stalk: {e}")
        await ctx.send("*nghiêng đầu* Có chút trục trặc...")

# --- HELP COMMAND ---
@monika_bot.command(name="help", aliases=["helps", "h"])
async def custom_help(ctx):
    try:
        embed = discord.Embed(
            title="💚 Monika After Story",
            description="Bot trò chuyện, render hình ảnh & phân tích",
            color=discord.Color.from_rgb(255, 184, 212)
        )
        embed.add_field(name="👁️ Theo Dõi", value="`!Mstalk [@user]` - Quét profile\n`!Mauto` - Bật/tắt chủ động", inline=False)
        embed.add_field(name="🔍 Tìm kiếm", value="`!Msearch [từ]` - Tìm trên mạng\n`!Manalytics` - Phân tích ảnh", inline=False)
        embed.add_field(name="⚙️ Cấu hình", value="`!Mrender` - Bật render\n`!Mtext` - Chế độ text\n`!Mclear` - Xóa lịch sử", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"❌ Lỗi help: {e}")

# --- MANALYTICS COMMAND ---
@monika_bot.command(name="manalytics", aliases=["manalyse", "phantich"])
async def manalytics_command(ctx, *, user_prompt: str = "Hãy phân tích chi tiết toàn bộ nội dung trong hình ảnh này một cách sâu sắc nhất."):
    try:
        if not ctx.message.attachments:
            await ctx.send("*nghiêng đầu* Cậu phải gửi kèm ảnh để phân tích nhé!")
            return

        attachment = ctx.message.attachments[0]
        status_msg = await ctx.send("🔍 *Monika đang tiến hành quét tấc, nghi ngờ và phân tích chuyên sâu (15 trang)...*")

        media_pil = None
        media_data_for_ai = None

        try:
            file_bytes = await attachment.read()
            filename_lower = attachment.filename.lower()

            if any(filename_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                media_pil = Image.open(io.BytesIO(file_bytes)).convert("RGBA")
                media_data_for_ai = media_pil
            else:
                media_data_for_ai = types.Part.from_bytes(data=file_bytes, mime_type=attachment.content_type or "application/octet-stream")

        except Exception as e:
            print(f"❌ Lỗi xử lý file: {e}")

        if media_data_for_ai:
            analysis_reply = await ask_monika([user_prompt, media_data_for_ai])
        else:
            analysis_reply = await ask_monika(user_prompt)

        pages = split_text_into_exact_pages(analysis_reply, target_pages=15)
        
        await status_msg.delete()
        
        img_buf = generate_mas_image(pages[0], chibi_state="happy", search_img_pil=media_pil)
        files = [discord.File(fp=img_buf, filename="monika_render.png")] if img_buf else []

        tts_buf = await generate_tts_file(pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        view = DialoguePaginationView(pages, author_id=ctx.author.id, search_img_pil=media_pil, media_data=media_data_for_ai, total_pages=15)
        if files:
            await ctx.send(files=files, view=view)
        else:
            embed = discord.Embed(title="💚 Monika", description=pages[0], color=discord.Color.from_rgb(120, 198, 122))
            await ctx.send(embed=embed, view=view)
    except Exception as e:
        print(f"❌ Lỗi manalytics: {e}")
        await ctx.send(f"*nghiêng đầu* Có chút trục trặc: {str(e)[:100]}")

# --- SEARCH COMMAND ---
@monika_bot.command(name="search")
async def search_command(ctx, *, query: str = None):
    try:
        if not query:
            await ctx.send("*mỉm cười* Cậu tìm cái gì vậy?")
            return
        
        status_msg = await ctx.send("🔍 *Monika đang tìm kiếm...*")
        
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=3))
        
        reply = f"🔎 Kết quả tìm kiếm '{query}':\n\n"
        for i, result in enumerate(results, 1):
            reply += f"{i}. **{result.get('title', 'Untitled')}**\n"
            reply += f"   {result.get('body', 'Không có mô tả')}\n"
            reply += f"   🔗 {result.get('href', '')}\n\n"
        
        await status_msg.delete()
        await ctx.send(reply)
    except Exception as e:
        print(f"❌ Lỗi search: {e}")
        await ctx.send("*nghiêng đầu* Có chút trục trặc...")

# --- RENDER COMMANDS ---
@monika_bot.command(name="render", aliases=["img"])
async def enable_render(ctx):
    try:
        mas_data["render_mode"] = True
        save_mas_data(mas_data)
        await ctx.send("🖼️ **Đã BẬT Render UI!**")
    except Exception as e:
        print(f"❌ Lỗi render: {e}")

@monika_bot.command(name="text")
async def enable_text(ctx):
    try:
        mas_data["render_mode"] = False
        save_mas_data(mas_data)
        await ctx.send("💬 **Chế độ Text.**")
    except Exception as e:
        print(f"❌ Lỗi text mode: {e}")

@monika_bot.command(name="clear")
async def clear_history(ctx):
    try:
        mas_data["chat_history"] = []
        save_mas_data(mas_data)
        await ctx.send("*mỉm cười* Xóa xong rồi!")
    except Exception as e:
        print(f"❌ Lỗi clear: {e}")

# --- ON MESSAGE ---
@monika_bot.event
async def on_message(message):
    if message.author == monika_bot.user:
        return

    if message.content.lower().startswith('!m'):
        await monika_bot.process_commands(message)
        return

    if monika_bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        try:
            clean_content = message.content.replace(f'<@{monika_bot.user.id}>', '').strip()

            async with message.channel.typing():
                mas_data["active_channel_id"] = message.channel.id

                if message.attachments:
                    attachment = message.attachments[0]
                    try:
                        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                            img_bytes = await attachment.read()
                            pil_image = Image.open(io.BytesIO(img_bytes))

                            user_prompt = clean_content if clean_content else "Cậu gửi cho tôi bức ảnh này. Hãy phân tích thật sâu sắc."
                            reply = await ask_monika([user_prompt, pil_image])
                        else:
                            reply = await ask_monika(clean_content if clean_content else "Cậu gửi cho tôi file này.")
                    except Exception as e:
                        print(f"❌ Lỗi xử lý attachment: {e}")
                        reply = await ask_monika(clean_content if clean_content else "Cậu gửi cho tôi file.")
                else:
                    if not clean_content:
                        await message.channel.send("*mỉm cười* Cậu gọi tôi?")
                        return
                    reply = await ask_monika(clean_content)

                pages = split_text_into_exact_pages(reply, target_pages=8)

                if mas_data.get("render_mode", True):
                    img_buf = generate_mas_image(pages[0], chibi_state="happy")
                    if img_buf:
                        files = [discord.File(fp=img_buf, filename="monika_render.png")]
                        tts_buf = await generate_tts_file(pages[0])
                        if tts_buf:
                            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))
                        view = DialoguePaginationView(pages, author_id=message.author.id)
                        await message.channel.send(files=files, view=view)
                    else:
                        embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
                        await message.channel.send(embed=embed)
                else:
                    embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
                    await message.channel.send(embed=embed)
        except Exception as e:
            print(f"❌ Lỗi on_message: {e}")
            try:
                await message.channel.send("*bối rối* Có chút trục trặc...")
            except:
                pass

# ==========================================
# 9. KHỞI CHẠY BOT
# ==========================================
if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask, daemon=True)
    t_flask.start()

    token = os.environ.get("DISCORD_TOKEN")
    if token:
        monika_bot.run(token)
    else:
        print("❌ Lỗi: Không tìm thấy DISCORD_TOKEN!")
