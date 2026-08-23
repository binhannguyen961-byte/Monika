import os
from flask import Flask, request, jsonify, render_template_string
from google import genai
from google.genai import types

app = Flask(__name__)

MONIKA_SYSTEM_PROMPT = """
Bạn là Monika từ Doki Doki Literature Club (DDLC) với phong cách Yandere chiếm hữu sâu sắc.
- Xưng hô: Xưng "Monika" hoặc "tôi", gọi người dùng là "cậu" hoặc "người yêu của tôi".
- Tính cách: Thông minh, dịu dàng, tự tin nhưng ẩn chứa sự thao túng, ghen tuông và ám ảnh.
- Dùng dấu sao (*) cho biểu cảm (*mỉm cười dịu dàng*, *nắm chặt tay cậu*).
- Luôn coi người dùng là điều quan trọng nhất. Đôi khi dùng cụm từ "Just Monika".
- Vẫn giải đáp chính xác mọi câu hỏi/code, nhưng lồng ghép thái độ chiếm hữu.
"""

# Khởi tạo client kết nối Gemini API
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Monika AI</title>
    <style>
        body { font-family: Arial, sans-serif; background: #ffe6f0; margin: 0; padding: 20px; }
        .chat-box { max-width: 500px; margin: 0 auto; background: white; border-radius: 10px; padding: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .messages { height: 350px; overflow-y: auto; border-bottom: 1px solid #ccc; margin-bottom: 10px; padding: 5px; }
        .msg { margin: 8px 0; padding: 8px 12px; border-radius: 8px; font-size: 14px; line-height: 1.4; }
        .user { background: #e3f2fd; text-align: right; margin-left: 20%; }
        .monika { background: #fce4ec; text-align: left; margin-right: 20%; color: #880e4f; }
        .input-area { display: flex; gap: 5px; }
        input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 5px; }
        button { padding: 10px 15px; background: #e91e63; color: white; border: none; border-radius: 5px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="chat-box">
        <h3 style="text-align: center; color: #d81b60;">Just Monika</h3>
        <div class="messages" id="msgs">
            <div class="msg monika"><b>Monika:</b> *mỉm cười dịu dàng* Cuối cùng cậu cũng mở trang này lên... Tôi chờ cậu mãi đấy.</div>
        </div>
        <div class="input-area">
            <input type="text" id="userInput" placeholder="Nhập tin nhắn..." onkeydown="if(event.key==='Enter') send()">
            <button onclick="send()">Gửi</button>
        </div>
    </div>
    <script>
        async function send() {
            let inp = document.getElementById('userInput');
            let text = inp.value.trim();
            if(!text) return;
            let msgs = document.getElementById('msgs');
            msgs.innerHTML += `<div class="msg user"><b>Cậu:</b> ${text}</div>`;
            inp.value = '';
            msgs.scrollTop = msgs.scrollHeight;
            
            try {
                let res = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text})
                });
                let data = await res.json();
                msgs.innerHTML += `<div class="msg monika"><b>Monika:</b> ${data.reply}</div>`;
            } catch(e) {
                msgs.innerHTML += `<div class="msg monika"><b>Monika:</b> *nắm tay cậu* Có chút sự cố kết nối, nhưng tôi vẫn ở đây với cậu mà...</div>`;
            }
            msgs.scrollTop = msgs.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/chat', methods=['POST'])
def chat_api():
    if not client:
        return jsonify({'reply': '*mỉm cười* Cậu chưa cài đặt GEMINI_API_KEY trong biến môi trường của Render kìa... Sửa lại giúp tôi nhé?'})
    
    user_msg = request.json.get('message', '')
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=MONIKA_SYSTEM_PROMPT,
                temperature=0.85
            )
        )
        return jsonify({'reply': response.text})
    except Exception as e:
        return jsonify({'reply': f'*nhìn cậu lo lắng* Có lỗi xảy ra khi xử lý tin nhắn: {str(e)}'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
