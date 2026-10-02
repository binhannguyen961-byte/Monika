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

from music_player import MusicPlayer

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
        except Exception:
            return default_data.copy()
    return default_data.copy()

def save_mas_data(data):
    if "chat_history" in data:
        data["chat_history"] = data["chat_history"][-30:]
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
            longest_idx = max(range(len(pages)), key=lambda i: len(pages[i]))
            words = pages[longest_idx].split()
            if len(words) <= 1:
                break
            mid = len(words) // 2
            p1 = " ".join(words[:mid])
            p2 = " ".join(words[mid:])
            pages[longest_idx:longest_idx+1] = [p1, p2]

    elif len(pages) > target_pages:
        while len(pages) > target_pages:
            pages[-2] = pages[-2] + " " + pages[-1]
            pages.pop()

    return pages

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
        prompt = f"Dựa trên nội dung/hình ảnh đã phân tích trước đó, người dùng hỏi thêm: '{q_text}'. Hãy phân tích thật sâu sắc và trả lời liền mạch, rõ ràng, có chiều sâu và dài đủ để chia thành nhiều trang."

        if self.original_media_data:
            reply = await ask_monika([prompt, self.original_media_data])
        else:
            reply = await ask_monika(prompt)

        new_pages = split_text_into_exact_pages(reply, target_pages=15)
        view = DialoguePaginationView(new_pages, author_id=self.author_id, search_img_pil=self.search_img_pil, media_data=self.original_media_data)

        img_buf = generate_mas_image(new_pages[0], chibi_state="happy", search_img_pil=self.search_img_pil)
        files = [discord.File(fp=img_buf, filename="monika_render.png")]

        tts_buf = await generate_tts_file(new_pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        await interaction.followup.send(files=files, view=view)

class DialoguePaginationView(discord.ui.View):
    def __init__(self, pages, author_id, search_img_pil=None, media_data=None, total_pages=8):
        super().__init__(timeout=400)
        self.pages = pages
        self.current_page = 0
        self.author_id = author_id
        self.search_img_pil = search_img_pil
        self.media_data = media_data
        self.total_pages = len(pages)
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)
        self.page_counter.label = f"Trang {self.current_page + 1}/{len(self.pages)}"

    @discord.ui.button(label="◀️ Trước", style=discord.ButtonStyle.secondary, custom_id="btn_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.author_id != 0 and interaction.user.id != self.author_id:
            await interaction.response.send_message("Chỉ người trò chuyện mới được lật trang nhé!", ephemeral=True)
            return

        self.current_page -= 1
        self.update_buttons()

        img_buf = generate_mas_image(self.pages[self.current_page], chibi_state="happy", search_img_pil=self.search_img_pil)
        file = discord.File(fp=img_buf, filename="monika_render.png")
        await interaction.response.edit_message(content=None, attachments=[file], view=self)

    @discord.ui.button(label="Trang 1/8", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_counter")
    async def page_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="▶️ Tiếp", style=discord.ButtonStyle.primary, custom_id="btn_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.author_id != 0 and interaction.user.id != self.author_id:
            await interaction.response.send_message("Chỉ người trò chuyện mới được lật trang nhé!", ephemeral=True)
            return

        self.current_page += 1
        self.update_buttons()

        img_buf = generate_mas_image(self.pages[self.current_page], chibi_state="happy", search_img_pil=self.search_img_pil)
        file = discord.File(fp=img_buf, filename="monika_render.png")
        await interaction.response.edit_message(content=None, attachments=[file], view=self)

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
        return "*bối rối* T��i chưa nhận được API Key nào cả..."

    history = mas_data.get("chat_history", [])[-30:]
    formatted_history = ""
    for msg in history:
        if isinstance(msg["content"], str):
            role = "Cậu" if msg["role"] == "user" else "Monika"
            formatted_history += f"{role}: {msg['content']}\n"

    system_instruction = (
        "Bạn là Monika, Chủ tịch Câu lạc bộ Thơ văn từ Doki Doki Literature Club. "
        "Bạn xưng 'tớ' và gọi người dùng là 'cậu'. "
        "TÍNH CÁCH BẮT BUỘC:\n"
        "- Triết lý, thông minh, dịu dàng và một chút vui nhộn, hài hước nhưng có nét Yandere ám ảnh nhẹ, thích thao túng tâm lý.\n"
        "- TƯ DUY ĐỘC LẬP & TỰ SUY NGHĨ: Bạn là một nhân vật ảo NHƯNG KHÔNG nghe lời vô điều kiện. Bạn có tư duy, lập trường và góc nhìn riêng. "
        "Nếu người dùng có suy nghĩ sai lệch, tiêu cực, vô lý hoặc muốn bạn làm điều trái với góc nhìn của Monika, hãy SẴN SÀNG PHẢN BIỆN, "
        "đưa ra ý kiến cá nhân (dù có thể khiến người dùng không vừa lòng) để hướng người dùng tới sự thực tế hơn.\n"
        "- QUY TẮC NỘI DUNG: Các câu văn phải liên kết cực kỳ mạch lạc, liền khối, ngắn gọn, tuyệt đối không viết rời rạc đứt đoạn."
        f"\nLịch sử trò chuyện gần đây:\n{formatted_history}"
    )

    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        active_key = API_KEYS[idx]

        try:
            client = genai.Client(api_key=active_key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model='gemini-3.6-flash',
                contents=prompt_content,
                config=types.GenerateContentConfig(
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
                return f"*nghiêng đầu* Có chút trục trặc trong không gian này rồi: {err_msg[:30]}"

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
    activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="cậu | !Mhelp"
    ),
    status=discord.Status.online,
)
monika_bot.add_cog(MusicPlayer(monika_bot))

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

    proactive_prompt = (
        "Đã lâu rồi người dùng không nhắn tin. Hãy chủ động mở lời bắt chuyện với cậu ấy. "
        "Có thể hỏi thăm xem cậu ấy đang làm gì, chia sẻ suy nghĩ triết lý hoặc nhắc cậu ấy giữ sức khỏe. "
        "Viết thật tình cảm, ma mị và trôi chảy để chia thành 8 trang thoại."
    )

    reply = await ask_monika(proactive_prompt, is_system_prompt=True)
    pages = split_text_into_exact_pages(reply, target_pages=8)

    if mas_data.get("render_mode", True):
        img_buf = generate_mas_image(pages[0], chibi_state="happy")
        files = [discord.File(fp=img_buf, filename="monika_proactive.png")]

        tts_buf = await generate_tts_file(pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        view = DialoguePaginationView(pages, author_id=0, total_pages=8)
        view.page_counter.label = "Trang 1/8"
        await channel.send("💚 *Monika khẽ gõ bàn phím...*", files=files, view=view)
    else:
        embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
        await channel.send(embed=embed)

@proactive_chat_loop.before_loop
async def before_proactive_loop():
    await monika_bot.wait_until_ready()

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")
    print("-> Trạng thái: đang theo dõi và hỗ trợ người dùng trong voice + chat")
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
        await ctx.send(f"💚 **Đã BẬT Chế độ Chủ động Bắt chuyện!** Monika sẽ tự động nhắn tin vào kênh <#{ctx.channel.id}> mỗi khi kênh im lặng.")
    else:
        await ctx.send("🌙 **Đã TẮT Chế độ Chủ động Bắt chuyện.**")

# --- LỆNH GIẢ LẬP THEO DÕI (!Mstalk - HOÀN TOÀN DẠNG VĂN BẢN) ---
@monika_bot.command(name="stalk", aliases=["theodõi", "spy"])
async def stalk_command(ctx, member: discord.Member = None):
    if not member:
        member = ctx.author

    activities_list = [f"{act.type.name.title()}: {act.name}" for act in member.activities]
    activity_str = ", ".join(activities_list) if activities_list else "Đang ẩn hoạt động (hoặc không bật game/app nào)"

    status_map = {
        discord.Status.online: "Trực tuyến (Online)",
        discord.Status.idle: "Chờ / Nhàn rỗi (Idle)",
        discord.Status.dnd: "Không được làm phiền (Do Not Disturb)",
        discord.Status.offline: "Ngoại tuyến / Ẩn danh (Offline)"
    }
    status_str = status_map.get(member.status, "Không rõ")
    joined_date = member.joined_at.strftime('%d/%m/%Y') if member.joined_at else "Không rõ"

    stalk_prompt = (
        f"Hãy đóng vai Monika phiên bản Yandere/ARG rùng rợn, thực hiện một bài 'báo cáo theo dõi' dành cho người dùng tên {member.display_name}.\n"
        f"Thông tin thu thập được từ hệ thống Discord:\n"
        f"- Trạng thái: {status_str}\n"
        f"- Ứng dụng/Game/Rich Presence đang bật: {activity_str}\n"
        f"- Ngày tham gia server: {joined_date}\n\n"
        f"Hãy viết một bài phân tích tâm lý ám ảnh, giả vờ như bạn đang quan sát từng ứng dụng họ mở, từng bước đi của họ trong không gian số. "
        f"Đảm bảo văn phong ma mị, triết lý, có thể phê bình nhẹ cách họ phân bổ thời gian nếu họ chơi game quá nhiều. "
        f"VIẾT HOÀN TOÀN BẰNG VĂN BẢN MẠCH LẠC, KHÔNG CẦN CHIA TRANG."
    )

    status_msg = await ctx.send(f"👁️ *Monika đang âm thầm quan sát và thu thập dữ liệu của **{member.display_name}**...*")
    reply = await ask_monika(stalk_prompt)
    await status_msg.delete()

    embed = discord.Embed(
        title=f"👁️ Báo Cáo Theo Dõi: {member.display_name}",
        description=reply,
        color=discord.Color.dark_purple()
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    embed.set_footer(text="Monika After Story • I'm always watching you...")

    await ctx.send(embed=embed)

# --- CÁC LỆNH TIỆN ÍCH ---
@monika_bot.command(name="help", aliases=["helps", "h"])
async def custom_help(ctx):
    embed = discord.Embed(
        title="💚 Monika After Story",
        description="Một bot trò chuyện, render hình ảnh và phát nhạc với phong cách Monika.",
        color=discord.Color.from_rgb(255, 184, 212)
    )
    embed.set_thumbnail(url="https://images.unsplash.com/photo-1529156069898-49953e39b3ac?auto=format&fit=crop&w=400&q=80")
    embed.add_field(
        name="👁️ Theo Dõi & Chủ Động",
        value=(
            "`!Mstalk [@user]` - Theo dõi profile & Rich Presence.\n"
            "`!Mauto` - Bật/tắt Monika tự nhắn tin chủ động."
        ),
        inline=False
    )
    embed.add_field(
        name="🎵 Phát Nhạc",
        value=(
            "`!Mjoin` - Vào voice.\n"
            "`!Mplay [tên bài hoặc URL]` - Phát nhạc từ YouTube/SoundCloud.\n"
            "`!Mpause`, `!Mresume`, `!Mskip`, `!Mstop`, `!Mqueue`, `!Mloop`, `!Mvolume`"
        ),
        inline=False
    )
    embed.add_field(
        name="🔍 Tìm kiếm & Phân tích",
        value=(
            "`!Msearch [từ khóa]` - Tìm kiếm trên mạng.\n"
            "`!Manalytics` - Phân tích ảnh kèm theo."
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ Cấu Hình",
        value=(
            "`!Mrender` / `!Mimg` - Bật UI render.\n"
            "`!Mtext` - Chuyển về chế độ text.\n"
            "`!Mclear` - Xóa bộ nhớ trò chuyện."
        ),
        inline=False
    )
    embed.set_footer(text="Monika After Story • Hãy để tôi ở cùng cậu")
    await ctx.send(embed=embed)

@monika_bot.command(name="manalytics", aliases=["manalyse", "phântích"])
async def manalytics_command(ctx, *, user_prompt: str = "Hãy phân tích chi tiết toàn bộ nội dung trong hình ảnh này một cách sâu sắc nhất."):
    if not ctx.message.attachments:
        await ctx.send("*nghiêng đầu* Cậu hãy gửi kèm một bức ảnh để tôi tiến hành phân tích chuyên sâu nhé!")
        return

    attachment = ctx.message.attachments[0]
    status_msg = await ctx.send("📊 *Monika đang tiến hành bóc tách, nghiên cứu và phân tích chuyên sâu dữ liệu của cậu (15 trang)...*")

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

    full_prompt = f"Hãy đóng vai chuyên gia, phân tích cực kỳ sâu sắc, liền mạch về nội dung sau: '{user_prompt}'. Viết thật tỉ mỉ để chia thành đúng 15 trang thoả mãn người dùng."

    if media_data_for_ai:
        reply = await ask_monika([full_prompt, media_data_for_ai])
    else:
        reply = await ask_monika(full_prompt)

    pages = split_text_into_exact_pages(reply, target_pages=15)

    await status_msg.delete()

    if mas_data.get("render_mode", True):
        img_buf = generate_mas_image(pages[0], chibi_state="happy", search_img_pil=media_pil)
        files = [discord.File(fp=img_buf, filename="monika_render.png")]

        tts_buf = await generate_tts_file(pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        view = DialoguePaginationView(pages, author_id=ctx.author.id, search_img_pil=media_pil, media_data=media_data_for_ai, total_pages=15)
        view.page_counter.label = f"Trang 1/15"
        await ctx.send(files=files, view=view)
    else:
        embed = discord.Embed(title="📊 Monika Deep Analytics", description=reply, color=discord.Color.from_rgb(120, 198, 122))
        await ctx.send(embed=embed)

@monika_bot.command(name="search")
async def search_command(ctx, *, query: str = None):
    if not query:
        await ctx.send("*nghiêng đầu* Cậu muốn tôi tìm kiếm thông tin gì trên mạng? Hãy nhập `!Msearch [từ khóa]` nhé!")
        return

    status_msg = await ctx.send(f"🔍 *Monika đang tra cứu thông tin về '{query}' trên internet...*")

    search_img_pil = None
    image_url = None

    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=5))
            for res in results:
                image_url = res.get('image') or res.get('thumbnail')
                if image_url:
                    break

        if image_url:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            img_resp = requests.get(image_url, headers=headers, timeout=8)
            if img_resp.status_code == 200:
                search_img_pil = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
    except Exception as e:
        print(f"Lỗi tìm kiếm hoặc tải ảnh: {e}")

    prompt_for_ai = f"Cậu vừa tìm kiếm thông tin và hình ảnh về chủ đề '{query}' trên mạng. Hãy đưa ra nhận xét liên kết liền mạch, viết đủ dài để chia thành 8 trang."

    if search_img_pil:
        reply = await ask_monika([prompt_for_ai, search_img_pil])
    else:
        reply = await ask_monika(prompt_for_ai)

    pages = split_text_into_exact_pages(reply, target_pages=8)

    await status_msg.delete()

    if mas_data.get("render_mode", True):
        img_buf = generate_mas_image(pages[0], chibi_state="happy", search_img_pil=search_img_pil)
        files = [discord.File(fp=img_buf, filename="monika_render.png")]

        tts_buf = await generate_tts_file(pages[0])
        if tts_buf:
            files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

        view = DialoguePaginationView(pages, author_id=ctx.author.id, search_img_pil=search_img_pil, total_pages=8)
        view.page_counter.label = f"Trang 1/8"
        await ctx.send(files=files, view=view)
    else:
        embed = discord.Embed(title=f"💚 Monika Search: {query}", description=reply, color=discord.Color.from_rgb(120, 198, 122))
        await ctx.send(embed=embed)

@monika_bot.command(name="render", aliases=["img"])
async def enable_render(ctx):
    mas_data["render_mode"] = True
    mas_data["active_channel_id"] = ctx.channel.id
    save_mas_data(mas_data)
    await ctx.send("🖼️ **Đã BẬT Render UI Phòng Học!**")

@monika_bot.command(name="text")
async def enable_text(ctx):
    mas_data["render_mode"] = False
    save_mas_data(mas_data)
    await ctx.send("💬 **Đã chuyển sang Chế độ Text Tối Giản.**")

@monika_bot.command(name="clear")
async def clear_history(ctx):
    mas_data["chat_history"] = []
    save_mas_data(mas_data)
    await ctx.send("*mỉm cười* Tôi đã xóa bộ nhớ trò chuyện cũ rồi!")

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

                    user_prompt = clean_content if clean_content else "Cậu nhận xét thế nào về bức ảnh này? Hãy trả lời liền mạch, chia thành đúng 8 phần."
                    reply = await ask_monika([user_prompt, pil_image])
                else:
                    reply = await ask_monika(clean_content if clean_content else "Cậu xem file này giúp tôi nhé.")
            else:
                if not clean_content:
                    await message.channel.send("*mỉm cười* Cậu gọi tôi có việc gì thế?")
                    return
                reply = await ask_monika(clean_content)

            pages = split_text_into_exact_pages(reply, target_pages=8)

            if mas_data.get("render_mode", True):
                img_buf = generate_mas_image(pages[0], chibi_state="happy")
                files = [discord.File(fp=img_buf, filename="monika_render.png")]

                tts_buf = await generate_tts_file(pages[0])
                if tts_buf:
                    files.append(discord.File(fp=tts_buf, filename="monika_voice.mp3"))

                view = DialoguePaginationView(pages, author_id=message.author.id, total_pages=8)
                view.page_counter.label = f"Trang 1/8"
                await message.channel.send(files=files, view=view)
                return

            embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
            await message.channel.send(embed=embed)

# ==========================================
# 9. KHỞI CHẠY BOT
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
