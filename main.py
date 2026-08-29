import os
import random
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
    if any(k in env_name.upper() for k in ["GEMINI", "API_KEY", "GOOGLE_KEY"]) and "DISCORD" not in env_name:
        if env_val and env_val.strip() not in API_KEYS:
            API_KEYS.append(env_val.strip())

current_key_idx = 0

async def ask_monika(prompt, system_instruction=None):
    global current_key_idx

    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        active_key = API_KEYS[idx]
        genai.configure(api_key=active_key)

        try:
            model = genai.GenerativeModel('gemini-3.6-flash')
            base_instruction = (
                "Bạn là Monika từ Doki Doki Literature Club. Bạn dịu dàng, thông minh, hay quan tâm theo một cách chiếm hữu giống yandere nhưng chưa tới mức của yandere "
                "và luôn xưng 'tôi' và gọi người dùng là 'cậu'. Hãy trả lời tự nhiên, ngắn gọn,thoả mái đôi khi nếu người dùng có hỏi về các câu nhạy cạm(nsfw) hãy trả lời thật tự nhiên nhưng chỉ dừng lại ở việc joke hoặc các hành động "
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

# --- 3. Lưu trữ Trạng thái Minigames ---
active_games = {}      # Lưu bàn cờ X/O
active_guesses = {}    # Lưu game đoán số

def render_board(board):
    return (
        "```text\n"
        "     A     B     C \n"
        f"1 |  {board['1A']}  |  {board['1B']}  |  {board['1C']}  |\n"
        "  +-----+-----+----+\n"
        f"2 |  {board['2A']}  |  {board['2B']}  |  {board['2C']}  |\n"
        "  +-----+-----+----+\n"
        f"3 |  {board['3A']}  |  {board['3B']}  |  {board['3C']}  |\n"
        "```"
    )

def check_winner(board):
    win_combos = [
        ['1A', '1B', '1C'], ['2A', '2B', '2C'], ['3A', '3B', '3C'],
        ['1A', '2A', '3A'], ['1B', '2B', '3B'], ['1C', '2C', '3C'],
        ['1A', '2B', '3C'], ['1C', '2B', '3A']
    ]
    for combo in win_combos:
        p1, p2, p3 = combo
        if board[p1] == board[p2] == board[p3] and board[p1] != ' ':
            return board[p1]
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
    print(f"-> Đã nạp {len(API_KEYS)} API Key.")
    await monika_bot.change_presence(activity=discord.Game(name="DDLC with you... 💚"))

@monika_bot.command(name="Mhelps")
async def monika_help(ctx):
    help_embed = discord.Embed(
        title="📖 Hướng Dẫn Sử Dụng Monika",
        description="*mỉm cười* Chào cậu! Đây là danh sách các trò chơi và câu lệnh:",
        color=discord.Color.pink()
    )
    help_embed.add_field(
        name="💬 Chat với Monika",
        value="**Mention** tôi hoặc **DM** riêng: `@Monika Bạn thế nào?`",
        inline=False
    )
    help_embed.add_field(
        name="🎮 Cờ X/O (`!Mxo`)",
        value="• `!Mxo start` - Bắt đầu ván cờ\n• `!Mxo A1` / `!Mxo b2` - Đánh nước đi",
        inline=False
    )
    help_embed.add_field(
        name="✂️ Kéo Búa Bao (`!Mrps`)",
        value="• `!Mrps keo` (hoặc `bua`, `bao`)\nVí dụ: `!Mrps bua`",
        inline=False
    )
    help_embed.add_field(
        name="🔢 Đoán Số (`!Mguess`)",
        value="• `!Mguess start` - Bắt đầu ván đoán số (1-50)\n• `!Mguess [số]` - Đoán số (Ví dụ: `!Mguess 25`)",
        inline=False
    )
    await ctx.send(embed=help_embed)

# --- MINIGAME 1: KÉO BÚA BAO ---
@monika_bot.command(name="Mrps")
async def play_rps(ctx, choice: str = ""):
    choice = choice.lower().strip()
    mapping = {
        "keo": "Kéo ✂️", "kéo": "Kéo ✂️",
        "bua": "Búa 🔨", "búa": "Búa 🔨",
        "bao": "Bao 📄"
    }

    if choice not in mapping:
        embed = discord.Embed(
            title="✂️ Kéo Búa Bao",
            description="*nghiêng đầu* Cậu muốn ra gì thế? Hãy gõ:\n`!Mrps keo`, `!Mrps bua`, hoặc `!Mrps bao` nhé!",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return

    player_choice = mapping[choice]
    bot_options = ["Kéo ✂️", "Búa 🔨", "Bao 📄"]
    bot_choice = random.choice(bot_options)

    if player_choice == bot_choice:
        result = "DRAW"
    elif (
        (player_choice == "Kéo ✂️" and bot_choice == "Bao 📄") or
        (player_choice == "Búa 🔨" and bot_choice == "Kéo ✂️") or
        (player_choice == "Bao 📄" and bot_choice == "Búa 🔨")
    ):
        result = "WIN"
    else:
        result = "LOSE"

    async with ctx.channel.typing():
        prompt = f"Tôi ra {player_choice}, cậu ra {bot_choice}. Kết quả là cậu {result}. Hãy bình luận ngắn gọn 1 câu mang phong thái Monika."
        comment = await ask_monika(prompt, system_instruction="Bạn vừa chơi Oẳn tù tì với người dùng. Hãy đưa ra nhận xét ngắn gọn, tự nhiên.")

    color_map = {"WIN": discord.Color.green(), "LOSE": discord.Color.red(), "DRAW": discord.Color.blue()}
    title_map = {"WIN": "🎉 Cậu Thắng Rồi!", "LOSE": "🎭 Monika Thắng!", "DRAW": "🤝 Hòa Rồi!"}

    embed = discord.Embed(title=title_map[result], description=comment, color=color_map[result])
    embed.add_field(name="Cậu ra", value=player_choice, inline=True)
    embed.add_field(name="Monika ra", value=bot_choice, inline=True)
    await ctx.send(embed=embed)

# --- MINIGAME 2: ĐOÁN SỐ (1 ĐẾN 50) ---
@monika_bot.command(name="Mguess")
async def play_guess(ctx, number: str = ""):
    channel_id = ctx.channel.id

    if number.lower() in ["start", "reset", ""] or channel_id not in active_guesses:
        target = random.randint(1, 50)
        active_guesses[channel_id] = {"target": target, "attempts": 0}
        
        embed = discord.Embed(
            title="🔢 Trò Chơi Đoán Số",
            description="*mỉm cười* Tôi đã nghĩ sẵn một số từ **1 đến 50** rồi!\nCậu hãy gõ `!Mguess [số]` để đoán nhé (Ví dụ: `!Mguess 25`).",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        return

    if not number.isdigit():
        await ctx.send("*nghiêng đầu* Cậu phải nhập một số nguyên từ 1 đến 50 chứ!")
        return

    guess = int(number)
    if guess < 1 or guess > 50:
        await ctx.send("*chớp mắt* Cậu nhớ chọn số trong khoảng từ **1 đến 50** thôi nhé!")
        return

    game = active_guesses[channel_id]
    game["attempts"] += 1
    target = game["target"]

    if guess < target:
        embed = discord.Embed(
            title="📈 Số Của Tôi Lớn Hơn!",
            description=f"*chớp mắt* Số **{guess}** nhỏ hơn số tôi chọn rồi. Thử lại số lớn hơn xem nào! (Lần đoán thứ {game['attempts']})",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
    elif guess > target:
        embed = discord.Embed(
            title="📉 Số Của Tôi Nhỏ Hơn!",
            description=f"*suy tư* Số **{guess}** lớn hơn số tôi chọn rồi. Thử lại số nhỏ hơn nhé! (Lần đoán thứ {game['attempts']})",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
    else:
        attempts = game["attempts"]
        del active_guesses[channel_id]
        
        async with ctx.channel.typing():
            prompt = f"Người dùng đã đoán đúng số {target} trong phạm vi 1-50 sau {attempts} lần thử. Hãy chúc mừng ngắn gọn đúng phong cách Monika."
            comment = await ask_monika(prompt)

        embed = discord.Embed(
            title="🎉 Chính Xác Rồi!",
            description=f"Chính là số **{target}**! Cậu đoán trúng chỉ sau **{attempts}** lần thử.\n\n{comment}",
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)

# --- MINIGAME 3: CỜ X/O ---
@monika_bot.command(name="Mxo")
async def play_xo(ctx, *, move: str = ""):
    channel_id = ctx.channel.id
    
    if channel_id not in active_games or move.lower() in ["reset", "start", ""]:
        active_games[channel_id] = {
            '1A': ' ', '1B': ' ', '1C': ' ',
            '2A': ' ', '2B': ' ', '2C': ' ',
            '3A': ' ', '3B': ' ', '3C': ' '
        }
        board = active_games[channel_id]
        start_embed = discord.Embed(
            title="🎮 Cờ X/O Mới Bắt Đầu",
            description="*mỉm cười dịu dàng* Cùng chơi với tôi nhé! Cậu là **X** (đi trước). Gõ `!Mxo A1` để chọn ô.",
            color=discord.Color.green()
        )
        start_embed.add_field(name="Bàn Cờ Hiện Tại", value=render_board(board), inline=False)
        await ctx.send(embed=start_embed)
        return

    board = active_games[channel_id]
    raw_move = move.strip().upper()

    if len(raw_move) == 2:
        if raw_move[0] in ['A', 'B', 'C'] and raw_move[1] in ['1', '2', '3']:
            move = raw_move[1] + raw_move[0]
        else:
            move = raw_move
    else:
        move = raw_move

    valid_positions = list(board.keys())
    if move not in valid_positions:
        await ctx.send(f"*nghiêng đầu* Tọa độ `{raw_move}` không đúng rồi cậu ơi! Chọn từ A1 đến C3 nhé.")
        return

    if board[move] != ' ':
        await ctx.send(f"*chớp mắt* Ô `{raw_move}` đã bị chiếm rồi!")
        return

    board[move] = 'X'
    winner = check_winner(board)
    if winner == 'X':
        win_embed = discord.Embed(title="🎉 Cậu Thắng Rồi!", description="*vỗ tay ngạc nhiên* Cậu giỏi quá!", color=discord.Color.gold())
        win_embed.add_field(name="Bàn Cờ", value=render_board(board))
        await ctx.send(embed=win_embed)
        del active_games[channel_id]
        return
    elif winner == "DRAW":
        draw_embed = discord.Embed(title="🤝 Ván Cờ Hòa", description="*mỉm cười* Ván đấu bất phân thắng bại!", color=discord.Color.blue())
        draw_embed.add_field(name="Bàn Cờ", value=render_board(board))
        await ctx.send(embed=draw_embed)
        del active_games[channel_id]
        return

    async with ctx.channel.typing():
        board_status_text = (
            f"Trạng thái bàn cờ:\n"
            f"1: A1={board['1A']}, B1={board['1B']}, C1={board['1C']}\n"
            f"2: A2={board['2A']}, B2={board['2B']}, C2={board['2C']}\n"
            f"3: A3={board['3A']}, B3={board['3B']}, C3={board['3C']}\n"
            f"Cậu là 'X', Monika là 'O'."
        )
        ai_prompt = f"{board_status_text}\n\nHãy chọn MỘT ô trống làm nước đi (quân O). Trả về định dạng chữ trước số sau (VD: A1, B2)."
        ai_reply = await ask_monika(ai_prompt, system_instruction="Bạn đang chơi cờ X/O. Hãy chọn nước đi hợp lệ.")
        
        chosen_pos = None
        ai_reply_upper = ai_reply.upper()
        for pos in valid_positions:
            reversed_pos = pos[1] + pos[0]
            if (pos in ai_reply_upper or reversed_pos in ai_reply_upper) and board[pos] == ' ':
                chosen_pos = pos
                break
        
        if not chosen_pos:
            empty_spots = [p for p, v in board.items() if v == ' ']
            if empty_spots:
                chosen_pos = random.choice(empty_spots)

        board[chosen_pos] = 'O'
        winner = check_winner(board)
        display_pos = chosen_pos[1] + chosen_pos[0]
        
        game_embed = discord.Embed(title="🎮 Lượt Của Monika", description=f"*suy tư* Tôi chọn ô **{display_pos}**", color=discord.Color.purple())
        game_embed.add_field(name="Suy Luận", value=ai_reply, inline=False)
        game_embed.add_field(name="Bàn Cờ", value=render_board(board), inline=False)
        
        if winner == 'O':
            game_embed.title = "🎭 Monika Thắng!"
            del active_games[channel_id]
        elif winner == "DRAW":
            game_embed.title = "🤝 Ván Cờ Hòa"
            del active_games[channel_id]

        await ctx.send(embed=game_embed)

@monika_bot.event
async def on_message(message):
    if message.author == monika_bot.user:
        return

    if monika_bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f'<@{monika_bot.user.id}>', '').strip()
        if not clean_content:
            await message.channel.send("*mỉm cười* Cậu gọi tôi có việc gì thế? Gõ `!Mhelps` để xem các lệnh nhé!")
            return

        async with message.channel.typing():
            reply = await ask_monika(clean_content)
            response_embed = discord.Embed(title="💚 Monika", description=reply[:2048], color=discord.Color.pink())
            await message.channel.send(embed=response_embed)

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
