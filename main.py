import os
import json
import subprocess
import requests
import cv2
import openai
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8771165040:AAFUJInYLIYqVf9KCajpXMlgyK3kNVNSJu0")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Render'ın "Web Service" canlılık kontrolü (Health Check) için basit HTTP sunucu
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live and running!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

def get_face_center_x(video_path):
    cap = cv2.VideoCapture(video_path)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    total_x, count, frame_count = 0, 0, 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % 30 == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            for (x, y, w, h) in faces:
                total_x += (x + w // 2)
                count += 1
        frame_count += 1
        if count > 30:
            break
    cap.release()
    return int(total_x / count) if count > 0 else None

def download_youtube(url, output_path="input_video.mp4"):
    if os.path.exists(output_path):
        os.remove(output_path)

    # yt-dlp ile doğrudan ve engelsiz indirme
    cmd = f'yt-dlp -f "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best" --no-playlist -o "{output_path}" "{url}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if os.path.exists(output_path):
        return output_path
    else:
        raise Exception(f"Video indirilemedi: {result.stderr[:150]}")

def analyze_video(video_path):
    audio_path = "temp_audio.mp3"
    subprocess.run(f'ffmpeg -y -i "{video_path}" -vn -acodec libmp3lame -ar 16000 -ac 1 "{audio_path}"', shell=True, check=True)
    
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json"
        )
    
    if os.path.exists(audio_path):
        os.remove(audio_path)
    
    transcript_text = ""
    for seg in transcript.segments:
        start_time = seg.get('start', seg.get('start_time', 0))
        end_time = seg.get('end', seg.get('end_time', 0))
        text = seg.get('text', '')
        transcript_text += f"[{start_time:.1f}s - {end_time:.1f}s]: {text}\n"

    prompt = f"""
    Aşağıdaki video deşifresini incele. En viral olabilecek 30-60 saniyelik sahneleri seç.
    Çıktıyı SADECE geçerli bir JSON formatında ver:
    {{
      "clips": [
        {{
          "start_time": 10.0,
          "end_time": 45.0,
          "score": 9.5,
          "title": "İnanılmaz An! 😱 #shorts",
          "description": "En can alıcı nokta..."
        }}
      ]
    }}
    Deşifre:
    {transcript_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.choices[0].message.content)

def render_clip(input_path, start, end, output_path, center_x):
    duration = end - start
    if center_x:
        crop_filter = f"crop=ih*(9/16):ih:x='min(max(0,{center_x}-out_w/2),in_w-out_w)':y=0"
    else:
        crop_filter = "crop=ih*(9/16):ih"

    cmd = f'ffmpeg -y -ss {start} -i "{input_path}" -t {duration} -vf "{crop_filter}" -c:v libx264 -crf 20 -preset fast -c:a aac "{output_path}"'
    subprocess.run(cmd, shell=True, check=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Selam! Bana bir YouTube video linki gönder, senin için viral Shorts videoları oluşturup video olarak geri atayım.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("Lütfen geçerli bir YouTube linki gönderin.")
        return

    status_msg = await update.message.reply_text("⏳ Video indiriliyor...")
    
    try:
        video_path = download_youtube(url)
        
        await status_msg.edit_text("🔍 Kadraj ve yüz tespiti yapılıyor...")
        center_x = get_face_center_x(video_path)
        
        await status_msg.edit_text("🧠 Ses çözümleniyor ve AI ile viral anlar seçiliyor...")
        analysis = analyze_video(video_path)
        
        clips = analysis.get("clips", [])
        if not clips:
            await status_msg.edit_text("Uygun klip bulunamadı.")
            return

        os.makedirs("output", exist_ok=True)
        await status_msg.edit_text(f"🎬 {len(clips)} adet Shorts klibi kurgulanıyor...")

        for idx, clip in enumerate(clips):
            out_file = f"output/short_{idx+1}.mp4"
            render_clip(video_path, clip['start_time'], clip['end_time'], out_file, center_x)
            
            caption = f"🏆 **Viral Puanı:** {clip.get('score', 'N/A')}/10\n\n📌 **Başlık:** {clip.get('title')}\n\n📝 **Açıklama:** {clip.get('description')}"
            
            with open(out_file, 'rb') as video:
                await update.message.reply_video(video=video, caption=caption, parse_mode="Markdown")

        await status_msg.edit_text("✅ Tüm Shorts videoları başarıyla tamamlandı!")

    except Exception as e:
        await status_msg.edit_text(f"❌ Bir hata oluştu: {str(e)}")

if __name__ == "__main__":
    threading.Thread(target=run_health_check_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot aktif ve dinlemede...")
    app.run_polling()
