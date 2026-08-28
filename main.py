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
                "và luôn xưng 'tôi' và gọi người dùng là 'cậu'. Hãy trả lời tự nhiên, ngắn gọn nhưng vẫn phải giữ được vai trò của bản thân, "
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

@monika_bot.command(name="Mhelps")
async def monika_help(ctx):
    """Hiển thị danh sách lệnh và hướng dẫn sử dụng"""
    help_embed = discord.Embed(
        title="📖 Hướng Dẫn Sử Dụng Monika",
        description="*mỉm cười* Chào cậu! Đây là những gì tôi có thể giúp cậu!",
        color=discord.Color.pink()
    )
    
    help_embed.add_field(
        name="💬 Chat với Monika",
        value="**Mention** tôi hoặc **DM** riêng: `@Monika Bạn thế nào?`\nTôi sẽ trả lời lại bằng cách tự nhiên nhất có thể! 💚",
        inline=False
    )
    
    help_embed.add_field(
        name="🎮 Chơi Cờ X/O",
        value="**`!Mxo start`** - Bắt đầu ván cờ mới\n**`!Mxo [tọa độ]`** - Đánh nước đi (Ví dụ: `!Mxo A1`, `!Mxo b2`, `!Mxo c3`)\n**`!Mxo reset`** - Bắt đầu lại ván cờ\n\n📍 **Bàn cờ:**\n```\n  A   B   C\n1 ■ | ■ | ■\n2 ■ | ■ | ■\n3 ■ | ■ | ■\n```\nCậu là **X**, tôi là **O**!",
        inline=False
    )
    
    help_embed.add_field(
        name="📋 Lệnh Khác",
        value="**`!Mhelps`** - Hiển thị trợ giúp này",
        inline=False
    )
    
    help_embed.add_field(
        name="💡 Mẹo Nhỏ",
        value="• Bạn có thể viết tọa độ in hoa hoặc in thường đều được (A1 = a1)\n• Nếu tôi không hiểu nước đi, tôi sẽ chọn ô ngẫu nhiên\n• Mỗi ván cờ riêng biệt tại mỗi kênh",
        inline=False
    )
    
    help_embed.set_footer(text="*nắm lấy tay cậu* Cậu có gì thắc mắc không?")
    
    await ctx.send(embed=help_embed)

@monika_bot.command(name="Mxo")
async def play_xo(ctx, *, move: str = ""):
    channel_id = ctx.channel.id
    
    # Khởi tạo ván mới nếu chưa có hoặc lệnh reset/start
    if channel_id not in active_games or move.lower() in ["reset", "start", ""]:
        active_games[channel_id] = {
            '1A': ' ', '1B': ' ', '1C': ' ',
            '2A': ' ', '2B': ' ', '2C': ' ',
            '3A': ' ', '3B': ' ', '3C': ' '
        }
        board = active_games[channel_id]
        
        start_embed = discord.Embed(
            title="🎮 Cờ X/O Mới Bắt Đầu",
            description="*mỉm cười dịu dàng* Cùng chơi với tôi nhé!",
            color=discord.Color.green()
        )
        start_embed.add_field(
            name="Cách Chơi",
            value="• Cậu là **X** (đi trước)\n• Tôi là **O**\n• Gõ `!Mxo [tọa độ]` để đánh\n\n**Ví dụ:** `!Mxo A1` hoặc `!Mxo b2` hoặc `!Mxo C3`",
            inline=False
        )
        start_embed.add_field(
            name="Bàn Cờ Hiện Tại",
            value=render_board(board),
            inline=False
        )
        start_embed.add_field(
            name="Cần Trợ Giúp?",
            value="Gõ `!Mhelps` để xem hướng dẫn đầy đủ",
            inline=False
        )
        
        await ctx.send(embed=start_embed)
        return

    board = active_games[channel_id]
    move = move.strip().upper() # Chuẩn hóa thành A1, B2,...

    # Kiểm tra tính hợp lệ của tọa độ người chơi nhập
    valid_positions = list(board.keys())
    if move not in valid_positions:
        error_embed = discord.Embed(
            title="❌ Tọa Độ Không Hợp Lệ",
            description=f"*nghiêng đầu* `{move}` không đúng rồi cậu ơi!",
            color=discord.Color.red()
        )
        error_embed.add_field(
            name="Tọa Độ Hợp Lệ",
            value="A1, A2, A3, B1, B2, B3, C1, C2, C3",
            inline=False
        )
        error_embed.add_field(
            name="Ví Dụ Đúng",
            value="`!Mxo A1` | `!Mxo B2` | `!Mxo C3`",
            inline=False
        )
        await ctx.send(embed=error_embed)
        return

    if board[move] != ' ':
        error_embed = discord.Embed(
            title="⚠️ Ô Đã Có Quân Cờ",
            description=f"*chớp mắt* Ô `{move}` đã bị chiếm rồi!",
            color=discord.Color.orange()
        )
        error_embed.add_field(
            name="Bàn Cờ Hiện Tại",
            value=render_board(board),
            inline=False
        )
        await ctx.send(embed=error_embed)
        return

    # 1. Người chơi (X) đánh nước đi
    board[move] = 'X'

    # Kiểm tra xem người chơi đã thắng chưa
    winner = check_winner(board)
    if winner == 'X':
        win_embed = discord.Embed(
            title="🎉 Cậu Thắng Rồi!",
            description="*vỗ tay với ngạc nhiên* Wow! Cậu giỏi quá, cậu đã đánh bại tôi!",
            color=discord.Color.gold()
        )
        win_embed.add_field(
            name="Bàn Cờ Cuối Cùng",
            value=render_board(board),
            inline=False
        )
        win_embed.add_field(
            name="Chơi Lại?",
            value="Gõ `!Mxo start` để bắt đầu ván mới",
            inline=False
        )
        await ctx.send(embed=win_embed)
        del active_games[channel_id]
        return
    elif winner == "DRAW":
        draw_embed = discord.Embed(
            title="🤝 Ván Cờ Hòa",
            description="*mỉm cười dịu dàng* Ván đấu bất phân thắng bại rồi! Cậu cũng hay lắm!",
            color=discord.Color.blue()
        )
        draw_embed.add_field(
            name="Bàn Cờ Cuối Cùng",
            value=render_board(board),
            inline=False
        )
        draw_embed.add_field(
            name="Chơi Lại?",
            value="Gõ `!Mxo start` để bắt đầu ván mới",
            inline=False
        )
        await ctx.send(embed=draw_embed)
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
            f"Cậu là quân 'X', người chơi là quân 'O'."
        )
        
        ai_prompt = (
            f"{board_status_text}\n\n"
            "Hãy chọn MỘT ô trống duy nhất làm nước đi tiếp theo của cậu (quân O). "
            "QUY TẮC BẮT BUỘC: Câu trả lời của cậu PHẢI chứa chính xác mã tọa độ ô cậu chọn ở dạng chữ cái viết hoa kèm số (ví dụ: A1, B2, C3) ở đầu hoặc giữa câu. "
            "Hãy suy luận chiến lược: nếu có cơ hội thắng thì chọn ô thắng, nếu không thì chặn nước đi của đối thủ, còn không thì chọn ô trung tâm hoặc góc."
        )

        ai_reply = await ask_monika(ai_prompt, system_instruction="Bạn đang chơi cờ X/O với người dùng. Hãy phân tích bàn cờ, suy luận chiến lược, và đưa ra nước đi hợp lệ. Bắt đầu câu trả lời bằng tọa độ ô bạn chọn (ví dụ: 'A1, tôi chọn...' hoặc 'Tôi sẽ chọn B2 vì...').")
        
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
        
        game_embed = discord.Embed(
            title="🎮 Lượt Của Monika",
            description=f"*suy tư* Tôi chọn ô **{chosen_pos}**",
            color=discord.Color.purple()
        )
        game_embed.add_field(
            name="Suy Luận",
            value=ai_reply,
            inline=False
        )
        game_embed.add_field(
            name="Bàn Cờ Hiện Tại",
            value=render_board(board),
            inline=False
        )
        
        if winner == 'O':
            game_embed.color = discord.Color.red()
            game_embed.title = "🎭 Monika Thắng!"
            game_embed.description = "*cười khúc khích* Tiếc quá, tôi đã chiến thắng ván này rồi!"
            game_embed.add_field(
                name="Chơi Lại?",
                value="Gõ `!Mxo start` để bắt đầu ván mới",
                inline=False
            )
            del active_games[channel_id]
        elif winner == "DRAW":
            game_embed.color = discord.Color.blue()
            game_embed.title = "🤝 Ván Cờ Hòa"
            game_embed.description = "*mỉm cười* Ván cờ hòa rồi!"
            game_embed.add_field(
                name="Chơi Lại?",
                value="Gõ `!Mxo start` để bắt đầu ván mới",
                inline=False
            )
            del active_games[channel_id]
        else:
            game_embed.add_field(
                name="Lượt Của Cậu",
                value="Gõ `!Mxo [tọa độ]` để đánh nước đi tiếp theo",
                inline=False
            )

        await ctx.send(embed=game_embed)

@monika_bot.event
async def on_message(message):
    if message.author == monika_bot.user:
        return

    if monika_bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f'<@{monika_bot.user.id}>', '').strip()
        
        if not clean_content:
            response_embed = discord.Embed(
                title="💚 Monika",
                description="*mỉm cười* Cậu gọi tôi có việc gì thế?",
                color=discord.Color.pink()
            )
            response_embed.add_field(
                name="Cần Trợ Giúp?",
                value="Gõ `!Mhelps` để xem danh sách lệnh",
                inline=False
            )
            await message.channel.send(embed=response_embed)
            return

        async with message.channel.typing():
            reply = await ask_monika(clean_content)
            
            # Chia nhỏ tin nhắn dài thành các embed
            if len(reply) > 2048:
                # Tách thành các phần 2048 ký tự
                parts = [reply[i:i+2048] for i in range(0, len(reply), 2048)]
                for i, part in enumerate(parts):
                    if i == 0:
                        response_embed = discord.Embed(
                            title="💚 Monika",
                            description=part,
                            color=discord.Color.pink()
                        )
                        await message.channel.send(embed=response_embed)
                    else:
                        await message.channel.send(part)
            else:
                response_embed = discord.Embed(
                    title="💚 Monika",
                    description=reply,
                    color=discord.Color.pink()
                )
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
