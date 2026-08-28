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

# --- 2. Cấu hình Gemini API & Đa Key Tự Động ---
API_KEYS = []
for env_name, env_val in os.environ.items():
    # Quét tất cả biến môi trường có chứa từ khóa API hoặc KEY (tránh lấy nhầm DISCORD_TOKEN)
    if any(k in env_name.upper() for k in ["GEMINI", "API_KEY", "GOOGLE_KEY"]) and "DISCORD" not in env_name:
        if env_val and env_val.strip() not in API_KEYS:
            API_KEYS.append(env_val.strip())

current_key_idx = 0

async def ask_monika(prompt, system_instruction=None):
    global current_key_idx

    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    # Xoay vòng lượt gọi qua từng API Key nếu có nhiều key dự phòng
    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        active_key = API_KEYS[idx]
        genai.configure(api_key=active_key)

        try:
            # Sử dụng model gemini-3.6-flash
            model = genai.GenerativeModel('gemini-3.6-flash')
            
            base_instruction = (
                "Bạn là Monika từ Doki Doki Literature Club. Bạn dịu dàng, thông minh, hay quan tâm "
                "và luôn xưng 'tôi' và gọi người dùng là 'cậu'. Hãy trả lời tự nhiên, ngắn gọn, "
                "có kèm hành động đặt trong ngoặc (*...*)."
            )
            
            full_prompt = f"{base_instruction}\n{system_instruction}\n\nNội dung/Yêu cầu: {prompt}" if system_instruction else f"{base_instruction}\n\nNgười dùng hỏi: {prompt}"
            
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

# --- 3. Quản lý trạng thái Trò chơi Cờ X/O (Tic-Tac-Toe) ---
# Lưu trữ bàn cờ theo channel_id
active_games = {}

def render_board(board):
    """Vẽ bàn cờ với hệ tọa độ Cột (A, B, C) và Hàng (1, 2, 3)"""
    return (
        "```text\n"
        "     A     B     C \n"
        f"1 |  {board['1A']}  |  {board['1B']}  |  {board['1C']}  |\n"
        "  +-----+-----+-----+\n"
        f"2 |  {board['2A']}  |  {board['2B']}  |  {board['2C']}  |\n"
        "  +-----+-----+-----+\n"
        f"3 |  {board['3A']}  |  {board['3B']}  |  {board['3C']}  |\n"
        "```"
    )

def check_winner(board):
    """Kiểm tra điều kiện thắng thua hoặc hòa"""
    win_combos = [
        ['1A', '1B', '1C'], ['2A', '2B', '2C'], ['3A', '3B', '3C'], # Hàng ngang
        ['1A', '2A', '3A'], ['1B', '2B', '3B'], ['1C', '2C', '3C'], # Cột dọc
        ['1A', '2B', '3C'], ['1C', '2B', '3A']                      # Đường chéo
    ]
    for combo in win_combos:
        p1, p2, p3 = combo
        if board[p1] == board[p2] == board[p3] and board[p1] != ' ':
            return board[p1] # Trả về 'X' hoặc 'O'
    
    if all(val != ' ' for val in board.values()):
        return "DRAW"
    return None

# --- 4. Discord Bot Monika ---
intents = discord.Intents.default()
intents.message_content = True
monika_bot = commands.Bot(command_prefix="!", intents=intents)

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")
    print(f"-> Đã nạp thành công {len(API_KEYS)} API Key vào bộ xoay vòng.")
    await monika_bot.change_presence(activity=discord.Game(name="DDLC with you... 💚"))

@monika_bot.command(name="Mxo")
async def play_xo(ctx, *, move: str = ""):
    channel_id = ctx.channel.id
    
    # Khởi tạo ván mới nếu chưa có hoặc lệnh reset
    if channel_id not in active_games or move.lower() in ["reset", "start"]:
        active_games[channel_id] = {
            '1A': ' ', '1B': ' ', '1C': ' ',
            '2A': ' ', '2B': ' ', '2C': ' ',
            '3A': ' ', '3B': ' ', '3C': ' '
        }
        board = active_games[channel_id]
        await ctx.send(
            "*mỉm cười* Cùng chơi cờ X/O với tôi nhé! Cậu đi trước (quân X).\n"
            "Hãy đánh nước đi bằng cách gõ: `!Mxo [tọa độ]` (Ví dụ: `!Mxo A1` hoặc `!Mxo b2`).\n"
            f"{render_board(board)}"
        )
        return

    board = active_games[channel_id]
    move = move.strip().upper() # Chuẩn hóa thành A1, B2,...

    # Kiểm tra tính hợp lệ của tọa độ người chơi nhập
    valid_positions = list(board.keys())
    if move not in valid_positions:
        await ctx.send(f"*nghiêng đầu* Tọa độ `{move}` không hợp lệ rồi cậu ơi. Cậu hãy chọn các ô từ A1 đến C3 nhé!")
        return

    if board[move] != ' ':
        await ctx.send(f"*chớp mắt* Ô `{move}` đã có quân cờ rồi, cậu chọn ô khác trống trải hơn đi.")
        return

    # 1. Người chơi (X) đánh nước đi
    board[move] = 'X'

    # Kiểm tra xem người chơi đã thắng chưa
    winner = check_winner(board)
    if winner == 'X':
        await ctx.send(f"*vỗ tay* Cậu giỏi quá, cậu đã chiến thắng tôi rồi!\n{render_board(board)}")
        del active_games[channel_id]
        return
    elif winner == "DRAW":
        await ctx.send(f"*mỉm cười dịu dàng* Ván đấu bất phân thắng bại rồi!\n{render_board(board)}")
        del active_games[channel_id]
        return

    # 2. Lượt AI (O) suy luận nước đi tiếp theo
    async with ctx.channel.typing():
        # Xây dựng trạng thái bàn cờ dạng text để AI phân tích
        board_status_text = (
            f"Trạng thái bàn cờ hiện tại:\n"
            f"Hàng 1: A1={board['1A']}, B1={board['1B']}, C1={board['1C']}\n"
            f"Hàng 2: A2={board['2A']}, B2={board['2B']}, C2={board['2C']}\n"
            f"Hàng 3: A3={board['3A']}, B3={board['3B']}, C3={board['3C']}\n"
            f"Các ô có dấu cách ' ' là ô trống chưa đánh.\n"
            f"Cậu là quân 'O', người chơi là quân 'X'."
        )
        
        ai_prompt = (
            f"{board_status_text}\n\n"
            "Hãy chọn MỘT ô trống duy nhất làm nước đi tiếp theo của cậu (quân O). "
            "QUY TẮC BẮT BUỘC: Câu trả lời của cậu PHẢI chứa chính xác mã tọa độ ô cậu chọn ở dạng chữ cái viết hoa kèm số (ví dụ: A1, B2, C3) ở đầu câu hoặc trong ngoặc, kèm theo một câu thoại ngắn mang tính chất của Monika."
        )

        ai_reply = await ask_monika(ai_prompt, system_instruction="Bạn đang chơi cờ caro X/O với người dùng. Hãy phân tích bàn cờ và đưa ra nước đi hợp lệ.")
        
        # Trích xuất tọa độ thông minh từ câu trả lời của AI
        chosen_pos = None
        for pos in valid_positions:
            if pos in ai_reply.upper() and board[pos] == ' ':
                chosen_pos = pos
                break
        
        # Trường hợp dự phòng nếu AI lỡ quên không ghi tọa độ chuẩn
        if not chosen_pos:
            empty_spots = [p for p, v in board.items() if v == ' ']
            if empty_spots:
                import random
                chosen_pos = random.choice(empty_spots)

        # AI đánh quân O vào bàn cờ
        board[chosen_pos] = 'O'

        # Kiểm tra xem AI đã thắng chưa sau nước đi
        winner = check_winner(board)
        response_msg = f"*suy tư* Tôi chọn ô **{chosen_pos}**.\n{ai_reply}\n{render_board(board)}"
        
        if winner == 'O':
            response_msg += "\n*cười khúc khích* Tiếc quá, tôi đã chiến thắng ván này rồi!"
            del active_games[channel_id]
        elif winner == "DRAW":
            response_msg += "\n*mỉm cười* Ván cờ hòa rồi!"
            del active_games[channel_id]

        await ctx.send(response_msg)

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
