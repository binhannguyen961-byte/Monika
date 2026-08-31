import asyncio
import cv2
import json
import io
import os
import random
import textwrap
import threading
import discord
from discord.ext import commands, tasks
from flask import Flask
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. WEB SERVER NGẦM (Giữ Bot Online 24/7)
# ==========================================
app = Flask(__name__)


@app.route('/')
def home():
  return 'Monika After Story Bot is Live!'


def run_flask():
  port = int(os.environ.get('PORT', 10000))
  app.run(host='0.0.0.0', port=port)


# ==========================================
# 2. CẤU HÌNH API KEYS GEMINI
# ==========================================
API_KEYS = []
for env_name, env_val in os.environ.items():
  if any(
      k in env_name.upper() for k in ['GEMINI', 'API_KEY', 'GOOGLE_KEY']
  ) and 'DISCORD' not in env_name:
    if env_val and env_val.strip() not in API_KEYS:
      API_KEYS.append(env_val.strip())

current_key_idx = 0

# ==========================================
# 3. QUẢN LÝ DỮ LIỆU & BỘ NHỚ (JSON)
# ==========================================
DATA_FILE = 'mas_settings.json'

default_data = {
    'affection': 10,
    'render_mode': True,
    'proactive_mode': False,
    'active_channel_id': None,
    'chat_history': [],
}


def load_mas_data():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for k, v in default_data.items():
          data.setdefault(k, v)
        return data
    except Exception:
      return default_data.copy()
  return default_data.copy()


def save_mas_data(data):
  if 'chat_history' in data:
    data['chat_history'] = data['chat_history'][-25:]
  with open(DATA_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


mas_data = load_mas_data()


# ==========================================
# 4. HÀM TẢI ẢNH LINH HOẠT
# ==========================================
def load_image_flexible(base_name):
  extensions = ['.png', '.PNG', '.jpg', '.JPG', '.jpeg', '.JPEG']

  if base_name == 'background':
    choices = [f'background_{i}' for i in range(1, 6)] + ['background']
    random.shuffle(choices)
    for choice in choices:
      for ext in extensions:
        path = os.path.join('assets', choice + ext)
        if os.path.exists(path):
          try:
            return Image.open(path).convert('RGBA')
          except Exception:
            pass

  for ext in extensions:
    path = os.path.join('assets', base_name + ext)
    if os.path.exists(path):
      try:
        return Image.open(path).convert('RGBA')
      except Exception:
        pass
  return None


def get_font(size):
  for font_name in [
      'font_regular.ttf',
      'arial.ttf',
      'DejaVuSans.ttf',
      'Roboto-Regular.ttf',
  ]:
    font_path = os.path.join('assets', font_name)
    if os.path.exists(font_path):
      try:
        return ImageFont.truetype(font_path, size)
      except Exception:
        pass
  return ImageFont.load_default()


# ==========================================
# 5. HÀM VẼ UI RENDER PHÒNG HỌC (ĐÃ FIX CHẮC CHẮN KHÔNG TRÀN KHUNG)
# ==========================================
def generate_mas_image(text, chibi_state='happy'):
  try:
    bg = load_image_flexible('background')
    if bg:
      bg = bg.resize((1000, 600))
    else:
      bg = Image.new('RGBA', (1000, 600), (40, 25, 45, 255))

    chibi = load_image_flexible(f'monika_{chibi_state}')
    if not chibi:
      chibi = load_image_flexible('monika_happy')

    if chibi:
      chibi = chibi.resize((380, 480))
      bg.paste(chibi, (310, 120), chibi)

    draw = ImageDraw.Draw(bg)

    textbox = load_image_flexible('textbox')
    if textbox:
      textbox = textbox.resize((960, 160))
      bg.paste(textbox, (20, 420), textbox)
    else:
      draw.rectangle(
          [(30, 410), (970, 570)],
          fill=(15, 15, 25, 220),
          outline=(255, 180, 200),
          width=2,
      )

    font_name = get_font(22)
    font_text = get_font(18)

    draw.text((60, 423), 'Monika', fill=(255, 200, 220), font=font_name)

    # TỰ ĐỘNG CẮT VĂN BẢN VÀ ÉP TỐI ĐA 3 DÒNG
    wrapped_lines = textwrap.wrap(text, width=42)
    max_lines = 3
    if len(wrapped_lines) > max_lines:
      wrapped_lines = wrapped_lines[:max_lines]
      if len(wrapped_lines[-1]) > 3:
        wrapped_lines[-1] = wrapped_lines[-1][:-3] + '...'

    y_offset = 455
    for line in wrapped_lines:
      draw.text(
          (60, y_offset), line, fill=(255, 255, 255), font=font_text, spacing=4
      )
      y_offset += 28

    buffer = io.BytesIO()
    bg.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
  except Exception as e:
    print(f'Lỗi Render Ảnh: {e}')
    return None


def render_frame_with_mas(
    frame_pil, subtitle_text='*Monika đang xem video cùng cậu...*'
):
  try:
    bg = load_image_flexible('background')
    if bg:
      bg = bg.resize((1000, 600))
    else:
      bg = Image.new('RGBA', (1000, 600), (30, 30, 30, 255))

    video_screen = frame_pil.resize((480, 270))
    bg.paste(video_screen, (260, 100))

    chibi = load_image_flexible('monika_happy')
    if chibi:
      chibi = chibi.resize((320, 400))
      bg.paste(chibi, (20, 180), chibi)

    draw = ImageDraw.Draw(bg)
    textbox = load_image_flexible('textbox')
    if textbox:
      textbox = textbox.resize((960, 150))
      bg.paste(textbox, (20, 430), textbox)
    else:
      draw.rectangle(
          [(30, 430), (970, 570)],
          fill=(10, 10, 15, 230),
          outline=(120, 198, 122),
          width=2,
      )

    font_name = get_font(20)
    font_text = get_font(18)

    draw.text((60, 438), 'Monika', fill=(160, 235, 160), font=font_name)

    wrapped_lines = textwrap.wrap(subtitle_text, width=44)
    if len(wrapped_lines) > 3:
      wrapped_lines = wrapped_lines[:3]
      wrapped_lines[-1] = wrapped_lines[-1][:-3] + '...'

    y_offset = 468
    for line in wrapped_lines:
      draw.text(
          (60, y_offset), line, fill=(255, 255, 255), font=font_text, spacing=4
      )
      y_offset += 28

    buffer = io.BytesIO()
    bg.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
  except Exception as e:
    print(f'Lỗi Render Video Frame: {e}')
    return None


# ==========================================
# 6. XỬ LÝ AI GEMINI (CẤU HÌNH PROMPT ÉP NGẮN)
# ==========================================
async def ask_monika(prompt_content, is_system_prompt=False):
  global current_key_idx

  if not API_KEYS:
    return '*bối rối* Tôi chưa nhận được API Key nào cả...'

  history = mas_data.get('chat_history', [])[-25:]
  formatted_history = ''
  for msg in history:
    if isinstance(msg['content'], str):
      role = 'Cậu' if msg['role'] == 'user' else 'Monika'
      formatted_history += f"{role}: {msg['content']}\n"

  system_instruction = (
      'Bạn là Monika trong phòng học không gian (Space Classroom) từ Monika'
      " After Story. Bạn dịu dàng, sâu lắng, mang phong cách văn học, xưng 'tôi'"
      " và gọi người dùng là 'cậu'.\n"
      f'Lịch sử thoại:\n{formatted_history}\n'
      'QUY TẮC BẮT BUỘC: Câu trả lời ngắn gọn, tuyệt đối từ 25 đến 35 từ để vừa'
      ' vặn trong 3 dòng của khung thoại.'
  )

  for i in range(len(API_KEYS)):
    idx = (current_key_idx + i) % len(API_KEYS)
    active_key = API_KEYS[idx]

    try:
      client = genai.Client(api_key=active_key)
      response = await asyncio.to_thread(
          client.models.generate_content,
          model='gemini-3.6-flash',  # Đã đổi model AI ổn định
          contents=prompt_content,
          config=types.GenerateContentConfig(
              system_instruction=system_instruction
          ),
      )
      current_key_idx = idx

      text_to_save = (
          prompt_content
          if isinstance(prompt_content, str)
          else '[Gửi một bức ảnh]'
      )
      if not is_system_prompt:
        mas_data['chat_history'].append(
            {'role': 'user', 'content': text_to_save}
        )
      mas_data['chat_history'].append(
          {'role': 'monika', 'content': response.text}
      )
      save_mas_data(mas_data)

      return response.text
    except Exception as e:
      err_msg = str(e)
      if '429' in err_msg or 'RESOURCE_EXHAUSTED' in err_msg:
        continue
      else:
        return f'*bối rối* Có lỗi xảy ra: {err_msg[:30]}'

  return '*nắm lấy tay cậu* Hệ thống đang bận, cậu chờ tôi nhé...'


# ==========================================
# 7. DISCORD BOT COMMANDS & EVENTS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
monika_bot = commands.Bot(
    command_prefix=['!M', '!m'], intents=intents, help_command=None
)


@monika_bot.event
async def on_ready():
  print(f'-> Monika Online: {monika_bot.user}')


@monika_bot.command(name='help', aliases=['helps', 'h'])
async def custom_help(ctx):
  embed = discord.Embed(
      title='💚 Bảng Hướng Dẫn Monika After Story',
      description='Dưới đây là các lệnh điều khiển bot:',
      color=discord.Color.from_rgb(120, 198, 122),
  )
  embed.add_field(
      name='⚙️ Chế Độ Render',
      value=(
          '`!Mrender` / `!Mimg`: Bật UI Render Phòng Học.\n'
          '`!Moffline`: Bật UI Render Offline.\n'
          '`!Mtext`: Tắt Render, chuyển về chat Text/Embed.'
      ),
      inline=False,
  )
  embed.add_field(
      name='🎬 Video & Tiện Ích',
      value=(
          '`!Mbadapple` / `!Mvideo`: Đính kèm file MP4 (<15s) chiếu với FPS 5'
          ' cao cấp.\nGửi kèm **Ảnh** + Tag Monika để Monika đọc và đánh giá!\n'
          '`!Mclear`: Xóa lịch sử 25 câu thoại cũ.'
      ),
      inline=False,
  )
  await ctx.send(embed=embed)


@monika_bot.command(name='render', aliases=['img'])
async def enable_render(ctx):
  mas_data['render_mode'] = True
  mas_data['proactive_mode'] = True
  mas_data['active_channel_id'] = ctx.channel.id
  save_mas_data(mas_data)
  await ctx.send('🖼️ **Đã BẬT Render UI Phòng Học!**')


@monika_bot.command(name='offline')
async def enable_offline(ctx):
  mas_data['render_mode'] = True
  mas_data['proactive_mode'] = False
  save_mas_data(mas_data)
  await ctx.send('🌙 **Đã BẬT Render UI Offline**')


@monika_bot.command(name='text')
async def enable_text(ctx):
  mas_data['render_mode'] = False
  mas_data['proactive_mode'] = False
  save_mas_data(mas_data)
  await ctx.send('💬 **Đã chuyển sang Chế độ Text Tối Giản.**')


@monika_bot.command(name='clear')
async def clear_history(ctx):
  mas_data['chat_history'] = []
  save_mas_data(mas_data)
  await ctx.send('*mỉm cười* Tôi đã xóa bộ nhớ trò chuyện cũ rồi!')


@monika_bot.command(name='badapple', aliases=['video'])
async def play_bad_apple(ctx):
  if not ctx.message.attachments:
    await ctx.send(
        '*chớp mắt* Cậu hãy gửi đính kèm một file video (MP4) dưới 15s nhé!'
    )
    return

  attachment = ctx.message.attachments[0]
  status_msg = await ctx.send(
      '🎬 *Monika đang xử lý video (FPS 5) của cậu...*'
  )
  temp_path = f'temp_{ctx.author.id}.mp4'
  await attachment.save(temp_path)

  try:
    cap = cv2.VideoCapture(temp_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    if duration > 15.5:
      await status_msg.edit(
          content='*lắc đầu* Video vượt quá 15 giây rồi cậu ơi!'
      )
      cap.release()
      os.remove(temp_path)
      return

    target_fps = 5.0
    frame_interval = int(fps / target_fps) if fps > target_fps else 1
    frame_count = 0
    rendered_message = None

    await status_msg.edit(content='🍿 *Bắt đầu chiếu video tốc độ cao!*')

    while cap.isOpened():
      ret, frame = cap.read()
      if not ret:
        break

      if frame_count % frame_interval == 0:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)

        sub = (
            f'*Đang xem video... [{int(frame_count/fps)}s/{int(duration)}s]*'
        )
        img_buf = render_frame_with_mas(pil_img, subtitle_text=sub)

        if img_buf:
          file = discord.File(fp=img_buf, filename='render_frame.png')
          if rendered_message is None:
            rendered_message = await ctx.send(file=file)
          else:
            await rendered_message.edit(attachments=[file])

        await asyncio.sleep(0.18)

      frame_count += 1

    cap.release()
    await ctx.send('*mỉm cười vỗ tay* Cảm ơn cậu đã xem video cùng tôi! 💚')

  except Exception as e:
    await ctx.send(f'Lỗi chiếu video: {e}')
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

  if monika_bot.user.mentioned_in(message) or isinstance(
      message.channel, discord.DMChannel
  ):
    clean_content = message.content.replace(
        f'<@{monika_bot.user.id}>', ''
    ).strip()

    async with message.channel.typing():
      mas_data['active_channel_id'] = message.channel.id

      if message.attachments:
        attachment = message.attachments[0]
        if any(
            attachment.filename.lower().endswith(ext)
            for ext in ['.png', '.jpg', '.jpeg', '.webp']
        ):
          img_bytes = await attachment.read()
          pil_image = Image.open(io.BytesIO(img_bytes))

          user_prompt = (
              clean_content
              if clean_content
              else 'Cậu nhận xét thế nào về bức ảnh này?'
          )
          reply = await ask_monika([user_prompt, pil_image])
        else:
          reply = await ask_monika(
              clean_content
              if clean_content
              else 'Cậu xem file này giúp tôi nhé.'
          )
      else:
        if not clean_content:
          await message.channel.send('*mỉm cười* Cậu gọi tôi có việc gì thế?')
          return
        reply = await ask_monika(clean_content)

      if mas_data.get('render_mode', True):
        img_buf = generate_mas_image(reply, chibi_state='happy')
        if img_buf:
          await message.channel.send(
              file=discord.File(fp=img_buf, filename='monika_render.png')
          )
          return

      embed = discord.Embed(
          title='💚 Monika',
          description=reply,
          color=discord.Color.from_rgb(120, 198, 122),
      )
      await message.channel.send(embed=embed)


# ==========================================
# 8. KHỞI CHẠY BOT
# ==========================================
if __name__ == '__main__':
  t_flask = threading.Thread(target=run_flask)
  t_flask.daemon = True
  t_flask.start()

  token = os.environ.get('DISCORD_TOKEN')
  if token:
    monika_bot.run(token)
  else:
    print('Lỗi: Không tìm thấy DISCORD_TOKEN trong Environment Variables!')
