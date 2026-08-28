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
        "
