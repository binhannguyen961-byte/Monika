import os
import random
import asyncio
import threading
import json
import io
import textwrap
import cv2
import requests
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from duckduckgo_search import DDGS

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
# 4. HÀM TẢI ẢNH & FONT LINH HOẠT
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

# ==========================================
# 5. THUẬT TOÁN CHIA TRANG ĐÚNG 8 TRANG & RENDER UI
# ==========================================
def split_text_into_exact_pages(text, max_chars_per_page=140, target_pages=8):
    words = text.split()
    total_words = len(words)
    
    if total_words == 0:
        return ["*mỉm cười* ..."] * target_pages
        
    words_per_page = max(1, total_words // target_pages)
    pages = []
    
    for i in range(target_pages):
        start_idx = i * words_per_page
        if i == target_pages - 1:
            page_words = words[start_idx:]
        else:
            page_words = words[start_idx:start_idx + words_per_page]
            
        page_str = " ".join(page_words)
        if not page_str.strip():
            page_str = "*mỉm cười dịu dàng*..."
        pages.append(page_str[:250])
        
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

def render_frame_with_mas(frame_pil, subtitle_text="*Monika đang xem video cùng cậu...*"):
    try:
        bg = load_image_flexible("background")
        if bg:
            bg = bg.resize((1000, 600))
        else:
            bg = Image.new("RGBA", (1000, 600), (30, 30, 30, 255))

        video_screen = frame_pil.resize((480, 270))
        bg.paste(video_screen, (260, 100))

        chibi = load_image_flexible("monika_happy")
        if chibi:
            chibi = chibi.resize((320, 400))
            bg.paste(chibi, (20, 180), chibi)

        draw = ImageDraw.Draw(bg)
        textbox = load_image_flexible("textbox")
        if textbox:
            textbox = textbox.resize((960, 150))
            bg.paste(textbox, (20, 430), textbox)
        else:
            draw.rectangle([(30, 430), (970, 570)], fill=(10, 10, 15, 230), outline=(120, 198, 122), width=2)

        font_name = get_font(20)
        font_text = get_font(18)

        draw.text((60, 438), "Monika", fill=(160, 235, 160), font=font_name)

        wrapped_lines = textwrap.wrap(subtitle_text, width=46)
        y_offset = 465
        for line in wrapped_lines[:4]:
            draw.text((60, y_offset), line, fill=(255, 255, 255), font=font_text)
            y_offset += 24

        buffer = io.BytesIO()
        bg.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Lỗi Render Video Frame: {e}")
        return None

# ==========================================
# 6. DISCORD UI COMPONENT (PHÂN TRANG 8 TRANG)
# ==========================================
class DialoguePaginationView(discord.ui.View):
    def __init__(self, pages, author_id, search_img_pil=None):
        super().__init__(timeout=300)
        self.pages = pages
        self.current_page = 0
        self.author_id = author_id
        self.search_img_pil = search_img_pil
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)
        self.page_counter.label = f"Trang {self.current_page + 1}/{len(self.pages)}"

    @discord.ui.button(label="◀️ Trước", style=discord.ButtonStyle.secondary, custom_id="btn_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
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
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Chỉ người trò chuyện mới được lật trang nhé!", ephemeral=True)
            return
        
        self.current_page += 1
        self.update_buttons()
        
        img_buf = generate_mas_image(self.pages[self.current_page], chibi_state="happy", search_img_pil=self.search_img_pil)
        file = discord.File(fp=img_buf, filename="monika_render.png")
        await interaction.response.edit_message(content=None, attachments=[file], view=self)

# ==========================================
# 7. XỬ LÝ AI GEMINI (MODEL 3.6-FLASH)
# ==========================================
async def ask_monika(prompt_content, is_system_prompt=False):
    global current_key_idx

    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    history = mas_data.get("chat_history", [])[-30:]
    formatted_history = ""
    for msg in history:
        if isinstance(msg["content"], str):
            role = "Cậu" if msg["role"] == "user" else "Monika"
            formatted_history += f"{role}: {msg['content']}\n"

    system_instruction = (
        "Bạn là Monika trong phòng học không gian (Space Classroom) từ Monika After Story. "
        "Bạn dịu dàng, sâu lắng, xưng 'tôi' và gọi người dùng là 'cậu'. "
        "QUY TẮC BẮT BUỘC: Bạn phải viết một đoạn văn dài vừa đủ, phong phú nội dung, để khi hệ thống chia nhỏ thành các đoạn ngắn, nó vừa vặn tạo thành đúng 8 phần (8 trang thoại). Không được viết quá ngắn."
        f"\nLịch sử thoại:\n{formatted_history}"
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
                return f"*bối rối* Có lỗi xảy ra: {err_msg[:30]}"

    return "*nắm lấy tay cậu* Hệ thống đang bận, cậu chờ tôi nhé..."

# ==========================================
# 8. MINI-GAME CỜ VUA (CHESS LOGIC GIAO DIỆN TỌA ĐỘ)
# ==========================================
active_chess_games = {} # channel_id -> game_state

class ChessGame:
    def __init__(self):
        # Bàn cờ 8x8 đơn giản thu gọn hoặc chuẩn (Sử dụng ký hiệu quân cờ Unicode)
        # Quân Trắng (Người chơi - W), Quân Đen (Monika - B)
        self.board = [
            ["♜", "♞", "♝", "♛", "♚", "♝", "♞", "♜"],
            ["♟", "♟", "♟", "♟", "♟", "♟", "♟", "♟"],
            [".", ".", ".", ".", ".", ".", ".", "."],
            [".", ".", ".", ".", ".", ".", ".", "."],
            [".", ".", ".", ".", ".", ".", ".", "."],
            [".", ".", ".", ".", ".", ".", ".", "."],
            ["♙", "♙", "♙", "♙", "♙", "♙", "♙", "♙"],
            ["♖", "♘", "♗", "♕", "♔", "♗", "♘", "♖"]
        ]
        self.turn = "player" # 'player' (Trắng) hoặc 'monika' (Đen)
        self.message = "Trận đấu cờ vua bắt đầu! Cậu đi quân Trắng trước."

    def render_board_ascii(self):
        cols = ["A", "B", "C", "D", "E", "F", "G", "H"]
        res = "    " + "   ".join(cols) + "\n"
        res += "  +---+---+---+---+---+---+---+---+\n"
        for idx, row in enumerate(self.board):
            row_num = 8 - idx
            row_str = f"{row_num} | " + " | ".join(row) + " |"
            res += row_str + f"\n  +---+---+---+---+---+---+---+---+\n"
        return res

# ==========================================
# 9. DISCORD BOT COMMANDS & EVENTS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
monika_bot = commands.Bot(command_prefix=["!M", "!m"], intents=intents, help_command=None)

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")

@monika_bot.command(name="help", aliases=["helps", "h"])
async def custom_help(ctx):
    embed = discord.Embed(
        title="💚 Bảng Hướng Dẫn Monika After Story",
        description="Dưới đây là các lệnh điều khiển bot:",
        color=discord.Color.from_rgb(120, 198, 122)
    )
    embed.add_field(
        name="🔍 Tìm kiếm & Web",
        value="`!Msearch [từ khóa]`: Monika tra cứu internet, hiển thị ảnh lên màn hình máy tính (8 trang).",
        inline=False
    )
    embed.add_field(
        name="♟️ Mini-game Cờ Vua",
        value="`!Mchess`: Bắt đầu đấu Cờ Vua với Monika.\n`!Mchess [ô_đầu] [ô_đến]` (Ví dụ: `!Mchess e2 e4`) để di chuyển quân.",
        inline=False
    )
    embed.add_field(
        name="⚙️ Chế Độ Render & Khác",
        value=(
            "`!Mrender` / `!Mimg`: Bật UI Render Phòng Học.\n"
            "`!Mbadapple` / `!Mvideo`: Chiếu video FPS 5 kèm phụ đề.\n"
            "`!Mclear`: Xóa bộ nhớ trò chuyện."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

@monika_bot.command(name="chess")
async def chess_command(ctx, *args):
    channel_id = ctx.channel.id
    
    if len(args) == 0:
        game = ChessGame()
        active_chess_games[channel_id] = game
        
        desc = (
            f"*mỉm cười dịu dàng* Cùng đấu cờ vua với tôi nhé, cậu đi quân Trắng (♙/♖/♘/♗/♕/♔)!\n\n"
            f"**Cách Chơi:**\n"
            f"• Cậu là Trắng, đi trước.\n"
            f"• Tôi là Đen (♟/♜/♞/♝/♛/♚).\n"
            f"• Cú pháp di chuyển: `!Mchess [từ_ô] [đến_ô]`\n"
            f"• Ví dụ: `!Mchess e2 e4` hoặc `!Mchess g1 f3`\n\n"
            f"**Bàn Cờ Hiện Tại:**\n"
            f"```text\n{game.render_board_ascii()}```\n"
            f"*{game.message}*"
        )
        embed = discord.Embed(title="♟️ Trận Đấu Cờ Vua Mới Bắt Đầu", description=desc, color=discord.Color.from_rgb(120, 198, 122))
        await ctx.send(embed=embed)
        return

    if channel_id not in active_chess_games:
        await ctx.send("*nghiêng đầu* Chưa có bàn cờ nào đang diễn ra cả. Hãy gõ `!Mchess` để tạo bàn cờ mới nhé!")
        return

    game = active_chess_games[channel_id]
    
    if len(args) < 2:
        await ctx.send("*lắc đầu* Cậu phải nhập đúng cú pháp di chuyển, ví dụ: `!Mchess e2 e4` nhé!")
        return

    from_pos, to_pos = args[0].lower(), args[1].lower()
    
    col_map = {'a': 0, 'b': 1, 'c': 2, 'd': 3, 'e': 4, 'f': 5, 'g': 6, 'h': 7}
    
    try:
        f_col, f_row = col_map[from_pos[0]], 8 - int(from_pos[1])
        t_col, t_row = col_map[to_pos[0]], 8 - int(to_pos[1])
    except Exception:
        await ctx.send("*bối rối* Tọa độ ô cờ không hợp lệ! (Ví dụ hợp lệ từ a1 đến h8)")
        return

    # Kiểm tra đơn giản nước đi hợp lệ của người chơi
    piece = game.board[f_row][f_col]
    if piece in [".", "♜", "♞", "♝", "♛", "♚", "♟"]:
        await ctx.send("*lắc đầu* Ô xuất phát không có quân cờ của cậu (Trắng)!")
        return

    # Thực hiện nước đi người chơi
    game.board[t_row][t_col] = piece
    game.board[f_row][f_col] = "."
    game.message = f"Cậu vừa đi từ {from_pos} đến {to_pos}."

    # Monika (Đen) phản hồi tự động đơn giản di chuyển ngẫu nhiên một quân Đen hợp lệ
    import random
    black_pieces = []
    for r in range(8):
        for c in range(8):
            if game.board[r][c] in ["♟", "♜", "♞", "♝", "♛", "♚"]:
                black_pieces.append((r, c))

    if black_pieces:
        br, bc = random.choice(black_pieces)
        target_moves = [(br+1, bc), (br+1, bc+1), (br+1, bc-1)]
        valid_targets = [(tr, tc) for tr, tc in target_moves if 0 <= tr < 8 and 0 <= tc < 8 and game.board[tr][tc] in [".", "♙", "♖", "♘", "♗", "♕", "♔"]]
        if valid_targets:
            tr, tc = random.choice(valid_targets)
            b_piece = game.board[br][bc]
            game.board[tr][tc] = b_piece
            game.board[br][bc] = "."
            cols_rev = {0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'e', 5: 'f', 6: 'g', 7: 'h'}
            game.message += f" Monika đã phản đòn bằng quân {b_piece} từ {cols_rev[bc]}{8-br} đến {cols_rev[tc]}{8-tr}!"

    desc = (
        f"**Bàn Cờ Cờ Vua**\n"
        f"```text\n{game.render_board_ascii()}```\n"
        f"*{game.message}*\n"
        f"Gõ tiếp `!Mchess [từ_ô] [đến_ô]` để đi tiếp nước kế tiếp!"
    )
    embed = discord.Embed(title="♟️ Ván Cờ Vua Monika After Story", description=desc, color=discord.Color.from_rgb(120, 198, 122))
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

    prompt_for_ai = f"Cậu vừa tìm kiếm thông tin và hình ảnh về chủ đề '{query}' trên mạng. Hãy đưa ra nhận xét, chia sẻ hoặc phân tích sâu sắc, dịu dàng, viết đủ dài để chia thành 8 phần cho người dùng."
    
    if search_img_pil:
        reply = await ask_monika([prompt_for_ai, search_img_pil])
    else:
        reply = await ask_monika(prompt_for_ai)

    pages = split_text_into_exact_pages(reply, max_chars_per_page=140, target_pages=8)

    await status_msg.delete()
    
    if mas_data.get("render_mode", True):
        img_buf = generate_mas_image(pages[0], chibi_state="happy", search_img_pil=search_img_pil)
        file = discord.File(fp=img_buf, filename="monika_render.png")
        
        view = DialoguePaginationView(pages, author_id=ctx.author.id, search_img_pil=search_img_pil)
        await ctx.send(file=file, view=view)
    else:
        embed = discord.Embed(title=f"💚 Monika Search: {query}", description=reply, color=discord.Color.from_rgb(120, 198, 122))
        await ctx.send(embed=embed)

@monika_bot.command(name="render", aliases=["img"])
async def enable_render(ctx):
    mas_data["render_mode"] = True
    mas_data["proactive_mode"] = True
    mas_data["active_channel_id"] = ctx.channel.id
    save_mas_data(mas_data)
    await ctx.send("🖼️ **Đã BẬT Render UI Phòng Học!**")

@monika_bot.command(name="offline")
async def enable_offline(ctx):
    mas_data["render_mode"] = True
    mas_data["proactive_mode"] = False
    save_mas_data(mas_data)
    await ctx.send("🌙 **Đã BẬT Render UI Offline**")

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
    await ctx.send("*mỉm cười* Tôi đã xóa bộ nhớ trò chuyện cũ rồi!")

@monika_bot.command(name="badapple", aliases=["video"])
async def play_bad_apple(ctx):
    if not ctx.message.attachments:
        await ctx.send("*chớp mắt* Cậu hãy gửi đính kèm một file video (MP4) dưới 15s nhé!")
        return

    attachment = ctx.message.attachments[0]
    status_msg = await ctx.send("🎬 *Monika đang xử lý video (FPS 5) của cậu...*")
    temp_path = f"temp_{ctx.author.id}.mp4"
    await attachment.save(temp_path)

    try:
        cap = cv2.VideoCapture(temp_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        if duration > 15.5:
            await status_msg.edit(content="*lắc đầu* Video vượt quá 15 giây rồi cậu ơi!")
            cap.release()
            os.remove(temp_path)
            return

        target_fps = 5.0
        frame_interval = int(fps / target_fps) if fps > target_fps else 1
        frame_count = 0
        rendered_message = None

        await status_msg.edit(content="🍿 *Bắt đầu chiếu video tốc độ cao!*")

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
                    file = discord.File(fp=img_buf, filename="render_frame.png")
                    if rendered_message is None:
                        rendered_message = await ctx.send(file=file)
                    else:
                        await rendered_message.edit(attachments=[file])

                await asyncio.sleep(0.18)

            frame_count += 1

        cap.release()
        await ctx.send("*mỉm cười vỗ tay* Cảm ơn cậu đã xem video cùng tôi! 💚")

    except Exception as e:
        await ctx.send(f"Lỗi chiếu video: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

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
                    
                    user_prompt = clean_content if clean_content else "Cậu nhận xét thế nào về bức ảnh này? Hãy trả lời chi tiết chia thành đúng 8 phần."
                    reply = await ask_monika([user_prompt, pil_image])
                else:
                    reply = await ask_monika(clean_content if clean_content else "Cậu xem file này giúp tôi nhé.")
            else:
                if not clean_content:
                    await message.channel.send("*mỉm cười* Cậu gọi tôi có việc gì thế?")
                    return
                reply = await ask_monika(clean_content)

            pages = split_text_into_exact_pages(reply, max_chars_per_page=140, target_pages=8)

            if mas_data.get("render_mode", True):
                img_buf = generate_mas_image(pages[0], chibi_state="happy")
                file = discord.File(fp=img_buf, filename="monika_render.png")
                
                view = DialoguePaginationView(pages, author_id=message.author.id)
                await message.channel.send(file=file, view=view)
                return

            embed = discord.Embed(title="💚 Monika", description=reply, color=discord.Color.from_rgb(120, 198, 122))
            await message.channel.send(embed=embed)

# ==========================================
# 10. KHỞI CHẠY BOT
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
