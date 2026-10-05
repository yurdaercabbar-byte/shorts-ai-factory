import asyncio
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import edge_tts
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

GROQ_API_KEY = "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"
TELEGRAM_BOT_TOKEN = "8277254415:AAHGXNzkv8GTh9Q6fW_c6Vw5L_f6JgT3eok"

groq_client = Groq(api_key=GROQ_API_KEY)

# Render'ın Port Taramasını Geçmek İçin Kukla HTTP Sunucusu
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# 1. SENARYO ÜRETİMİ (GÜNCEL MODEL)
def generate_story(topic):
    prompt = f"""
    Sen profesyonel bir içerik üreticisisin.
    Konu: '{topic}'.
    Bu konu hakkında akıcı, sürükleyici, anlatıcı dilinde detaylı bir konuşma metni hazırla.
    Metni ana sahnelere böl ve her sahne için İngilizce çizim/karikatür görsel promptları ekle.
    
    Format:
    SAHNE 1: [Görsel Promptu - İngilizce]
    METİN 1: [Okunacak Konuşma Metni - Türkçe]
    """
    completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile"
    )
    return completion.choices[0].message.content

# 2. FİLİGRANSIZ GÖRSEL ÜRETİMİ
def generate_watermark_free_image(prompt_text, output_path):
    encoded_prompt = requests.utils.quote(f"{prompt_text}, digital art style, detailed, expressive animation look, no watermark")
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&model=flux&nologo=true"
    response = requests.get(image_url)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    return False

# 3. SESLENDİRME
async def generate_audio(text, output_path):
    communicate = edge_tts.Communicate(text, "tr-TR-AhmetNeural")
    await communicate.save(output_path)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Selam! Bana bir konu söyle, senaryosunu yazayım, filigransız görselini çizeyim ve Türkçe seslendireyim!")

async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_topic = update.message.text
    chat_id = update.effective_chat.id
    
    status_msg = await update.message.reply_text(f"🚀 **Ajan Devreye Girdi!**\n\n`{user_topic}` konusu araştırılıyor...")
    
    try:
        story_text = generate_story(user_topic)
        
        audio_file = "voice.mp3"
        image_file = "scene.jpg"
        
        sample_audio_text = f"{user_topic} hakkında hazırlanan içerik özeti seslendiriliyor."
        await generate_audio(sample_audio_text, output_path=audio_file)
        
        generate_watermark_free_image(f"An illustration representing {user_topic}, dynamic concept art", image_file)
        
        with open(image_file, 'rb') as photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo, caption="🎨 **Üretilen Filigransız Sahne Görseli**")
            
        with open(audio_file, 'rb') as audio:
            await context.bot.send_audio(chat_id=chat_id, audio=audio, caption="🎙️ **Akıcı Türkçe Seslendirme**")
            
        await context.bot.send_message(chat_id=chat_id, text=f"📝 **Oluşturulan Senaryo:**\n\n{story_text[:3500]}")
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Bir hata oluştu: {str(e)}")

def main():
    # Render port kontrolünü geçmek için sunucuyu yan thread'de çalıştır
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🤖 Telegram Botu Başlatılıyor...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_topic))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
