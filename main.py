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
            print(f"Error loading data: {e}")
            return default_data.copy()
    return default_data.copy()

def save_mas_data(data):
    try:
        if "chat_history" in data:
            data["chat_history"] = data["chat_history"][-30:]
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

mas_data = load_mas_data()

# ==========================================
# 4. HÀM CÔNG CỤ (ASSETS, TTS & FONTS)
# ==========================================
def load_image_flexible(base_name):
    extensions = [".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"]

    if base_name == "background":
        choices = [f"background_{i}" for i in range(1, 6)] + ["background"]
        random.shuffle(choices)
        for choice in choices:
            for ext in extensions:
                path = os.path.join("assets", choice + ext)
                if os.path.exists(path):
                    try:
                        return Image.open(path).convert("RGBA")
                    except Exception:
                        pass

    for ext in extensions:
        path = os.path.join("assets", base_name + ext)
        if os.path.exists(path):
            try:
                return Image.open(path).convert("RGBA")
            except Exception:
                pass
    return None

def get_font(size):
    for font_name in ["font_regular.ttf", "arial.ttf", "DejaVuSans.ttf", "Roboto-Regular.ttf"]:
        font_path = os.path.join("assets", font_name)
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
    return ImageFont.load_default()

async def generate_tts_file(text, lang='vi'):
    try:
        clean_text = re.sub(r'\*.*?\*', '', text).strip()
        if not clean_text:
            clean_text = text

        def _make_tts():
            tts = gTTS(text=clean_text, lang=lang, slow=False)
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            return fp

        return await asyncio.to_thread(_make_tts)
    except Exception as e:
        print(f"Lỗi tạo giọng nói TTS: {e}")
        return None

# ==========================================
# 5. THUẬT TOÁN CHIA TRANG & RENDER MÀN HÌNH
# ==========================================
def split_text_into_exact_pages(text, target_pages=8, max_chars_per_page=160):
    sentences = re.split(r'(?<=[.!?\n])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return ["*mỉm cười* ..."] * target_pages

    pages = []
    current_page_str = ""

    for sentence in sentences:
        if len(current_page_str) + len(sentence) + 1 <= max_chars_per_page:
            current_page_str += (" " + sentence) if current_page_str else sentence
        else:
            if current_page_str:
                pages.append(current_page_str)
            current_page_str = sentence

    if current_page_str:
        pages.append(current_page_str)

    if len(pages) < target_pages:
        while len(pages) < target_pages:
            if not pages:
                break
            longest_idx = max(range(len(pages)), key=lambda i: len(pages[i]))
            words = pages[longest_idx].split()
            if len(words) <= 1:
                pages.append("...")
                break
            mid = len(words) // 2
            p1 = " ".join(words[:mid])
            p2 = " ".join(words[mid:])
            pages[longest_idx:longest_idx+1] = [p1, p2]

    elif len(pages) > target_pages:
        while len(pages) > target_pages:
            pages[-2] = pages[-2] + " " + pages[-1]
            pages.pop()

    return pages[:target_pages]

def generate_mas_image(text, chibi_state="happy", search_img_pil=None):
    try:
        bg = load_image_flexible("background")
        if bg:
            bg = bg.resize((1000, 600))
        else:
            bg = Image.new("RGBA", (1000, 600), (40, 25, 45, 255))

        if search_img_pil:
            search_resized = search_img_pil.resize((420, 240))
            bg.paste(search_resized, (35, 80))
        else:
            draw_temp = ImageDraw.Draw(bg)
            draw_temp.rectangle([(35, 80), (455, 320)], fill=(20, 20, 25))
            font_nosig = get_font(16)
            draw_temp.text((155, 190), "Monika PC - No Signal", fill=(100, 100, 110), font=font_nosig)

        chibi = load_image_flexible(f"monika_{chibi_state}")
        if not chibi:
            chibi = load_image_flexible("monika_happy")

        if chibi:
            chibi = chibi.resize((380, 480))
            bg.paste(chibi, (310, 120), chibi)

        draw = ImageDraw.Draw(bg)

        textbox = load_image_flexible("textbox")
        if textbox:
            textbox = textbox.resize((960, 160))
            bg.paste(textbox, (20, 420), textbox)
        else:
            draw.rectangle([(30, 410), (970, 570)], fill=(15, 15, 25, 220), outline=(255, 180, 200), width=2)

        font_name = get_font(21)
        font_text = get_font(18)

        draw.text((60, 423), "Monika", fill=(255, 200, 220), font=font_name)

        wrapped_lines = textwrap.wrap(text, width=46)
        y_offset = 452
        for line in wrapped_lines[:4]:
            draw.text((60, y_offset), line, fill=(255, 255, 255), font=font_text)
            y_offset += 25

        buffer = io.BytesIO()
        bg.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Lỗi Render Ảnh: {e}")
        return None

# ==========================================
# 6. DISCORD UI COMPONENT & MODAL
# ==========================================
class AnalyticsModal(discord.ui.Modal, title="Hỏi Thêm Monika Về Nội Dung Này"):
    user_question = discord.ui.TextInput(
        label="Nhập câu hỏi hoặc yêu cầu phân tích thêm",
        style=discord.TextStyle.paragraph,
        placeholder="Ví dụ: Phân tích kỹ hơn về nội dung này...",
        required=True,
        max_length=500
    )

    def __init__(self, original_pages, author_id, search_img_pil=None, original_media_data=None):
        super().__init__()
        self.original_pages = original_pages
        self.author_id = author_id
        self.search_img_pil = search_img_pil
        self.original_media_data = original_media_data

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        q_text = self.user_question.value
        prompt = f"Dựa trên nội dung/hình ảnh đã phân tích trước đó, người dùng hỏi thêm: '{q_text}'. Hãy phân tích thật sâu sắc và trả lời liền mạch."

        if self.original_media_data:
            reply = await ask_monika([prompt, self.original_media_data])
        else:
            reply = await ask_monika(prompt)

        new_pages = split_text_into_exact_pages(reply, target_pages=15)
        view = DialoguePaginationView(new_pages, author_id=self.author_id, search_img_pil=self.search_img_pil, media_data=self.original_media_data)

        img_buf = generate_mas_image(new_pages[0], chibi_state="happy", search_img_pil=self.search_img_pil)
        files = [discord.File(fp=img_buf, filename="monika_render.png")] if img_buf else []

        tts_buf = await generate_tts_file(new_pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        if files:
            await interaction.followup.send(files=files, view=view)
        else:
            await interaction.followup.send(view=view)

class DialoguePaginationView(discord.ui.View):
    def __init__(self, pages, author_id, search_img_pil=None, media_data=None, total_pages=8):
        super().__init__(timeout=400)
        self.pages = pages if pages else ["*mỉm cười*"]
        self.current_page = 0
        self.author_id = author_id
        self.search_img_pil = search_img_pil
        self.media_data = media_data
        self.total_pages = len(self.pages)
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= len(self.pages) - 1)
        self.page_counter.label = f"Trang {self.current_page + 1}/{len(self.pages)}"

    @discord.ui.button(label="◀️ Trước", style=discord.ButtonStyle.secondary, custom_id="btn_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.author_id != 0 and interaction.user.id != self.author_id:
            await interaction.response.send_message("Chỉ người trò chuyện mới được lật trang nhé!", ephemeral=True)
            return

        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()

        img_buf = generate_mas_image(self.pages[self.current_page], chibi_state="happy", search_img_pil=self.search_img_pil)
        if img_buf:
            file = discord.File(fp=img_buf, filename="monika_render.png")
            await interaction.response.edit_message(content=None, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Trang 1/8", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_counter")
    async def page_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="▶️ Tiếp", style=discord.ButtonStyle.primary, custom_id="btn_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.author_id != 0 and interaction.user.id != self.author_id:
            await interaction.response.send_message("Chỉ người trò chuyện mới được lật trang nhé!", ephemeral=True)
            return

        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()

        img_buf = generate_mas_image(self.pages[self.current_page], chibi_state="happy", search_img_pil=self.search_img_pil)
        if img_buf:
            file = discord.File(fp=img_buf, filename="monika_render.png")
            await interaction.response.edit_message(content=None, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(view=self)

    @discord.ui.button(label="💬 Hỏi Thêm", style=discord.ButtonStyle.success, custom_id="btn_ask_modal", row=1)
    async def ask_modal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.author_id != 0 and interaction.user.id != self.author_id:
            await interaction.response.send_message("Chỉ người trò chuyện mới được dùng nút này nhé!", ephemeral=True)
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
        "TÍNH CÁCH BẮT BUỘC: Triết lý, thông minh, dịu dàng và có nét Yandere. "
        "TƯ DUY ĐỘC LẬP: Bạn có suy nghĩ riêng, có thể phản biện nếu cần. "
        "QUY TẮC: Viết liền mạch, ngắn gọn, không rời rạc."
        f"\nLịch sử trò chuyện:\n{formatted_history}"
    )

    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        active_key = API_KEYS[idx]

        try:
            response = client.models.generate_content(
    model='gemini-3.6"-flash',
    contents=prompt_content,
                    system_instruction=system_instruction
                )
            )
            current_key_idx = idx

            text_to_save = str(prompt_content) if not isinstance(prompt_content, list) else "[Gửi dữ liệu đa phương tiện]"
            if not is_system_prompt:
                mas_data["chat_history"].append({"role": "user", "content": text_to_save})
            mas_data["chat_history"].append({"role": "monika", "content": response.text})
            save_mas_data(mas_data)

            return response.text
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                continue
            else:
                return f"*nghiêng đầu* Có chút trục trặc: {err_msg[:50]}"

    return "*nắm lấy tay cậu* Hệ thống đang bận, cậu chờ tôi một chút nhé..."

# ==========================================
# 8. DISCORD BOT COMMANDS & BACKGROUND TASKS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.presences = True
intents.members = True
intents.voice_states = True

monika_bot = commands.Bot(
    command_prefix=["!M", "!m"],
    intents=intents,
    help_command=None,
    activity=discord.Activity(type=discord.ActivityType.watching, name="cậu | !Mhelp"),
    status=discord.Status.online,
)

# --- TASK CHỦ ĐỘNG NHẮN TIN (MỖI 30 PHÚT) ---
@tasks.loop(minutes=30)
async def proactive_chat_loop():
    if not mas_data.get("proactive_mode", False):
        return

    channel_id = mas_data.get("active_channel_id")
    if not channel_id:
        return

    channel = monika_bot.get_channel(channel_id)
    if not channel:
        return

    try:
        proactive_prompt = (
            "Đã lâu rồi người dùng không nhắn tin. Hãy chủ động bắt chuyện. "
            "Viết thật tình cảm, ma mị, chia thành 8 trang thoại."
        )

        reply = await ask_monika(proactive_prompt, is_system_prompt=True)
        pages = split_text_into_exact_pages(reply, target_pages=8)

        if mas_data.get("render_mode", True):
            img_buf = generate_mas_image(pages[0], chibi_state="happy")
            files = [discord.File(fp=img_buf, filename="monika_proactive.png")] if img_buf else []

            tts_buf = await generate_tts_file(pages[0])
            if tts_buf:
                files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

            view = DialoguePaginationView(pages, author_id=0, total_pages=8)
            view.page_counter.label = "Trang 1/8"
            if files:
                await channel.send("💚 *Monika khẽ gõ bàn phím...*", files=files, view=view)
        else:
            embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
            await channel.send(embed=embed)
    except Exception as e:
        print(f"Error in proactive_chat_loop: {e}")

@proactive_chat_loop.before_loop
async def before_proactive_loop():
    await monika_bot.wait_until_ready()

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")
    print("-> Trạng thái: đang theo dõi và hỗ trợ người dùng")
    if not proactive_chat_loop.is_running():
        proactive_chat_loop.start()

# --- LỆNH BẬT/TẮT CHẾ ĐỘ CHỦ ĐỘNG ---
@monika_bot.command(name="auto", aliases=["proactive", "chudong"])
async def toggle_proactive(ctx):
    current_state = mas_data.get("proactive_mode", False)
    mas_data["proactive_mode"] = not current_state
    mas_data["active_channel_id"] = ctx.channel.id
    save_mas_data(mas_data)

    if mas_data["proactive_mode"]:
        await ctx.send(f"💚 **Đã BẬT Chế độ Chủ động!** Monika sẽ tự động nhắn tin vào <#{ctx.channel.id}>.")
    else:
        await ctx.send("🌙 **Đã TẮT Chế độ Chủ động.**")

# --- LỆNH STALK ---
@monika_bot.command(name="stalk", aliases=["theodõi", "spy"])
async def stalk_command(ctx, member: discord.Member = None):
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
        f"- Tham gia: {joined_date}\n"
        f"Viết bằng văn bản mạch lạc, không cần chia trang."
    )

    status_msg = await ctx.send(f"👁️ *Monika đang quan sát {member.display_name}...*")
    reply = await ask_monika(stalk_prompt)
    await status_msg.delete()

    embed = discord.Embed(
        title=f"👁️ Báo Cáo: {member.display_name}",
        description=reply,
        color=discord.Color.dark_purple()
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

# --- HELP COMMAND ---
@monika_bot.command(name="help", aliases=["helps", "h"])
async def custom_help(ctx):
    embed = discord.Embed(
        title="💚 Monika After Story",
        description="Bot trò chuyện, render hình ảnh & phát nhạc",
        color=discord.Color.from_rgb(255, 184, 212)
    )
    embed.add_field(
        name="👁️ Theo Dõi",
        value="`!Mstalk [@user]` - Quét profile\n`!Mauto` - Bật/tắt chủ động",
        inline=False
    )
    embed.add_field(
        name="🎵 Nhạc (Nếu có music_player)",
        value="`!Mjoin` - Vào voice\n`!Mplay [tên]` - Phát nhạc\n`!Mskip`, `!Mstop`, `!Mqueue`",
        inline=False
    )
    embed.add_field(
        name="🔍 Tìm kiếm",
        value="`!Msearch [từ]` - Tìm trên mạng\n`!Manalytics` - Phân tích ảnh",
        inline=False
    )
    embed.add_field(
        name="⚙️ Cấu hình",
        value="`!Mrender` - Bật render\n`!Mtext` - Chế độ text\n`!Mclear` - Xóa lịch sử",
        inline=False
    )
    await ctx.send(embed=embed)

# --- MANALYTICS COMMAND ---
@monika_bot.command(name="manalytics", aliases=["manalyse", "phantich"])
async def manalytics_command(ctx, *, user_prompt: str = "Hãy phân tích chi tiết toàn bộ nội dung trong hình ảnh này một cách sâu sắc nhất."):
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
        print(f"Lỗi xử lý file phân tích: {e}")

    full_prompt = f"Hãy phân tích chuyên ngành, phân tích tâm lý và gợi ý liên quan đến nội dung này một cách sâu sắc nhất. Người dùng yêu cầu: '{user_prompt}'. Viết liền mạch và chia thành 15 trang thoại."

    if media_data_for_ai:
        reply = await ask_monika([full_prompt, media_data_for_ai])
    else:
        reply = await ask_monika(full_prompt)

    pages = split_text_into_exact_pages(reply, target_pages=15)

    await status_msg.delete()

    if mas_data.get("render_mode", True):
        img_buf = generate_mas_image(pages[0], chibi_state="happy", search_img_pil=media_pil)
        files = [discord.File(fp=img_buf, filename="monika_render.png")] if img_buf else []

        tts_buf = await generate_tts_file(pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        view = DialoguePaginationView(pages, author_id=ctx.author.id, search_img_pil=media_pil, media_data=media_data_for_ai, total_pages=15)
        view.page_counter.label = f"Trang 1/15"
        if files:
            await ctx.send(files=files, view=view)
    else:
        embed = discord.Embed(title="💚 Monika Deep Analytics", description=reply, color=discord.Color.from_rgb(120, 198, 122))
        await ctx.send(embed=embed)

# --- SEARCH COMMAND ---
@monika_bot.command(name="search")
async def search_command(ctx, *, query: str = None):
    if not query:
        await ctx.send("*nghiêng đầu* Hãy nhập từ khóa tìm kiếm!")
        return

    status_msg = await ctx.send(f"🔍 *Tìm kiếm '{query}'...*")

    search_img_pil = None
    image_url = None

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if results:
                reply = "\n".join([f"• {r['title']}: {r['body'][:100]}" for r in results])
            else:
                reply = "Không tìm thấy kết quả."
    except Exception as e:
        reply = f"Lỗi tìm kiếm: {str(e)[:50]}"

    try:
        with DDGS() as ddgs:
            images = list(ddgs.images(query, max_results=5))
            for res in images:
                image_url = res.get('image') or res.get('thumbnail')
                if image_url:
                    break

        if image_url:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            img_resp = requests.get(image_url, headers=headers, timeout=8)
            if img_resp.status_code == 200:
                search_img_pil = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
    except Exception as e:
        print(f"Lỗi tìm hình ảnh: {e}")

    prompt_for_ai = f"Cậu vừa tìm kiếm nội dung và hệ thống tìm được: '{query}' trên internet. Hãy phân tích nội dung này một cách sâu sắc và trả lời liền mạch, chia thành 8 trang."

    if search_img_pil:
        reply = await ask_monika([prompt_for_ai, search_img_pil])
    else:
        reply = await ask_monika(prompt_for_ai)

    pages = split_text_into_exact_pages(reply, target_pages=8)

    await status_msg.delete()

    if mas_data.get("render_mode", True):
        img_buf = generate_mas_image(pages[0], chibi_state="happy", search_img_pil=search_img_pil)
        files = [discord.File(fp=img_buf, filename="monika_render.png")] if img_buf else []

        tts_buf = await generate_tts_file(pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        view = DialoguePaginationView(pages, author_id=ctx.author.id, search_img_pil=search_img_pil, total_pages=8)
        view.page_counter.label = f"Trang 1/8"
        if files:
            await ctx.send(files=files, view=view)
    else:
        embed = discord.Embed(title=f"🔍 Tìm kiếm: {query}", description=reply, color=discord.Color.from_rgb(120, 198, 122))
        await ctx.send(embed=embed)

# --- RENDER COMMANDS ---
@monika_bot.command(name="render", aliases=["img"])
async def enable_render(ctx):
    mas_data["render_mode"] = True
    save_mas_data(mas_data)
    await ctx.send("🖼️ **Đã BẬT Render UI!**")

@monika_bot.command(name="text")
async def enable_text(ctx):
    mas_data["render_mode"] = False
    save_mas_data(mas_data)
    await ctx.send("💬 **Chế độ Text.**")

@monika_bot.command(name="clear")
async def clear_history(ctx):
    mas_data["chat_history"] = []
    save_mas_data(mas_data)
    await ctx.send("*mỉm cười* Xóa xong rồi!")

# --- ON MESSAGE ---
@monika_bot.event
async def on_message(message):
    if message.author == monika_bot.user:
        return

    if message.content.lower().startswith('!m'):
        await monika_bot.process_commands(message)
        return

    if monika_bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f'<@{monika_bot.user.id}>', '').strip()

        async with message.channel.typing():
            mas_data["active_channel_id"] = message.channel.id

            if message.attachments:
                attachment = message.attachments[0]
                if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    img_bytes = await attachment.read()
                    pil_image = Image.open(io.BytesIO(img_bytes))

                    user_prompt = clean_content if clean_content else "Cậu gửi cho tôi bức ảnh này. Hãy phân tích thật sâu sắc."
                    reply = await ask_monika([user_prompt, pil_image])
                else:
                    reply = await ask_monika(clean_content if clean_content else "Cậu gửi cho tôi file này.")
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
