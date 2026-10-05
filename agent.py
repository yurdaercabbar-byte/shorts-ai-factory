import os
import asyncio
import requests
import edge_tts
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# API VE BOT TOKENLARI
GROQ_API_KEY = "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"
TELEGRAM_BOT_TOKEN = "8277254415:AAHGXNzkv8GTh9Q6fW_c6Vw5L_f6JgT3eok"

groq_client = Groq(api_key=GROQ_API_KEY)

# 1. HİKAYE VE SENARYO ÜRETİMİ (GROQ)
def generate_story(topic):
    prompt = f"""
    Sen profesyonel bir içerik üreticisisin.
    Konu: '{topic}'.
    Bu konu hakkında akıcı, sürükleyici, anlatıcı dilinde 5-10 dakikalık detaylı bir konuşma metni hazırla.
    Metni ana sahnelere böl ve her sahne için İngilizce çizim/karikatür görsel promptları ekle.
    
    Format:
    SAHNE 1: [Görsel Promptu - İngilizce]
    METİN 1: [Okunacak Konuşma Metni - Türkçe]
    """
    
    completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant"
    )
    return completion.choices[0].message.content

# 2. FİLİGRANSIZ GÖRSEL ÜRETİMİ (Pollinations AI - Flux)
def generate_watermark_free_image(prompt_text, output_path):
    encoded_prompt = requests.utils.quote(f"{prompt_text}, digital art style, detailed, expressive animation look, no watermark")
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&model=flux&nologo=true"
    
    response = requests.get(image_url)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    return False

# 3. DOĞAL SESLENDİRME (Edge TTS)
async def generate_audio(text, output_path):
    communicate = edge_tts.Communicate(text, "tr-TR-AhmetNeural")
    await communicate.save(output_path)

# START KOMUTU
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Selam! Bana bir konu söyle (Örn: 'İlk insanlar ateşi nasıl keşfetti?'), senin için araştırıp senaryosunu, filigransız görselini ve seslendirmesini hazırlayayım!")

# MESAJ YAKALAYICI VE İÇERİK ÜRETİCİ
async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_topic = update.message.text
    chat_id = update.effective_chat.id
    
    status_msg = await update.message.reply_text(f"🚀 **Ajan Devreye Girdi!**\n\n`{user_topic}` konusu araştırılıyor, senaryo yazılıyor ve görseller üretiliyor... Lütfen bekleyin.")
    
    try:
        # Senaryo Üret
        story_text = generate_story(user_topic)
        
        # Örnek Görsel ve Ses Dosya Yolları
        audio_file = "voice.mp3"
        image_file = "scene.jpg"
        
        # Örnek Seslendirme Metni Çekimi
        sample_audio_text = f"{user_topic} hakkında hazırlanan içerik özeti seslendiriliyor."
        await generate_audio(sample_audio_text, audio_file)
        
        # Filigransız Çizim Üretimi
        generate_watermark_free_image(f"An illustration representing {user_topic}, dynamic concept art", image_file)
        
        # Telegram'a Gönder
        with open(image_file, 'rb') as photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo, caption="🎨 **Üretilen Filigransız Sahne Görseli**")
            
        with open(audio_file, 'rb') as audio:
            await context.bot.send_audio(chat_id=chat_id, audio=audio, caption="🎙️ **Akıcı Türkçe Seslendirme**")
            
        await context.bot.send_message(chat_id=chat_id, text=f"📝 **Oluşturulan Senaryo:**\n\n{story_text[:3500]}")
        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Bir hata oluştu: {str(e)}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_topic))
    
    print("🤖 OTO-AJAN BOTU ÇALIŞIYOR...")
    app.run_polling(drop_pending_updates=True)
