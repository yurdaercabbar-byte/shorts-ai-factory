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

# Render Port Taramasını Sorunsuz Geçmek İçin HTTP Sunucusu
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
        
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return # Log kirliliği yapmasın

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# 1. SENARYO ÜRETİMİ (OTOMATİK MODEL YEDEKLEME SİSTEMİ)
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
    
    # Groq'un aktif olan tüm güncel modellerini sırayla dener
    models_to_try = [
        "llama3-8b-8192",
        "llama3-70b-8192",
        "mixtral-8x7b-32768",
        "gemma2-9b-it"
    ]
    
    last_error = None
    for model_name in models_to_try:
        try:
            completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model_name
            )
            return completion.choices[0].message.content
        except Exception as e:
            last_error = e
            continue
            
    raise Exception(f"Tüm modeller denendi fakat çalışmadı: {last_error}")

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

# 3. SESLEND
