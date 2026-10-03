import os
import json
import subprocess
import cv2
import streamlit as st
import requests
import whisper
import openai

st.set_page_config(page_title="AI Shorts Fabrikası", layout="wide")
st.title("🎬 Bulut Tabanlı AI Shorts Üreticisi")

# Yan Panel API Girişleri
api_key_input = st.sidebar.text_input("OpenAI API Key:", type="password")
rapidapi_key = st.sidebar.text_input("RapidAPI Key (YouTube İndirici):", type="password")

st.write("---")
tab1, tab2 = st.tabs(["🔗 YouTube Linki İle (Garantili Proxy)", "📁 Doğrudan Video Yükle"])

with tab1:
    video_url = st.text_input("YouTube Video URL'sini Yapıştırın:")

with tab2:
    uploaded_file = st.file_uploader("Cihazınızdan Video Seçin:", type=["mp4", "mov", "mkv", "avi"])

def download_youtube_rapidapi(url, rapid_key):
    output_path = "input_video.mp4"
    if os.path.exists(output_path):
        os.remove(output_path)
    
    video_id = url.split("v=")[-1].split("&")[0].split("?")[0].split("/")[-1]
    
    # RapidAPI YouTube MP4 Downloader İstek Yapısı
    api_url = "https://youtube-video-download-cli.p.rapidapi.com/dl"
    
    headers = {
        "x-rapidapi-key": rapid_key,
        "x-rapidapi-host": "youtube-video-download-cli.p.rapidapi.com"
    }
    
    params = {"id": video_id}
    
    response = requests.get(api_url, headers=headers, params=params, timeout=15)
    
    if response.status_code == 200:
        data = response.json()
        # İndirme bağlantısını al
        download_url = data.get("urls", [{}])[0].get("url") or data.get("link")
        
        if download_url:
            r = requests.get(download_url, stream=True, timeout=60)
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=2*1024*1024):
                    if chunk:
                        f.write(chunk)
            return output_path
            
    raise Exception("RapidAPI ile video indirilemedi. Lütfen API Key'inizi veya kotanızı kontrol edin.")

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

def analyze_video(video_path, api_key):
    client = openai.OpenAI(api_key=api_key)
    
    audio_path = "temp_audio.mp3"
    subprocess.run(f'ffmpeg -y -i "{video_path}" -vn -acodec libmp3lame -ar 16000 -ac 1 "{audio_path}"', shell=True, check=True)
    
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    
    if os.path.exists(audio_path):
        os.remove(audio_path)
    
    transcript_text = ""
    for seg in result['segments']:
        transcript_text += f"[{seg['start']:.1f}s - {seg['end']:.1f}s]: {seg['text']}\n"

    prompt = f"""
    Aşağıdaki video deşifresini incele. En viral olabilecek 30-60 saniyelik sahneleri seç.
    Çıktıyı SADECE geçerli bir JSON formatında ver:
    {{
      "clips": [
        {{
          "start_time": 10.0,
          "end_time": 45.0,
          "score": 9.5,
          "reason": "Harika kanca cümlesi.",
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
    return result, json.loads(response.choices[0].message.content)

def render_clip(input_path, start, end, output_path, center_x):
    duration = end - start
    if center_x:
        crop_filter = f"crop=ih*(9/16):ih:x='min(max(0,{center_x}-out_w/2),in_w-out_w)':y=0"
    else:
        crop_filter = "crop=ih*(9/16):ih"

    cmd = f'ffmpeg -y -ss {start} -i "{input_path}" -t {duration} -vf "{crop_filter}" -c:v libx264 -crf 20 -preset fast -c:a aac "{output_path}"'
    subprocess.run(cmd, shell=True, check=True)

if st.button("Shorts Üret"):
    if not api_key_input:
        st.error("Lütfen sol panelden OpenAI API Key girin!")
    elif video_url and not rapidapi_key:
        st.error("YouTube linki indirmek için sol panelden RapidAPI Key girmeniz gerekiyor!")
    else:
        v_file = "input_video.mp4"
        with st.spinner("Video hazırlanıyor ve işleniyor..."):
            try:
                if video_url:
                    v_file = download_youtube_rapidapi(video_url, rapidapi_key)
                elif uploaded_file is not None:
                    with open(v_file, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                else:
                    st.warning("Lütfen bir YouTube URL'si girin veya video dosyası yükleyin.")
                    st.stop()

                st.info("Kare tespiti yapılıyor...")
                center_x = get_face_center_x(v_file)
                
                st.info("Ses çözümleniyor ve AI ile analiz ediliyor...")
                transcript, analysis = analyze_video(v_file, api_key_input)
                
                os.makedirs("output", exist_ok=True)
                for idx, clip in enumerate(analysis.get("clips", [])):
                    out_file = f"output/short_{idx+1}.mp4"
                    render_clip(v_file, clip['start_time'], clip['end_time'], out_file, center_x)
                    
                    st.markdown(f"### 🏆 Viral Puanı: {clip['score']} / 10")
                    st.video(out_file)
                    st.write(f"**Başlık:** {clip['title']}")
                    st.write(f"**Açıklama:** {clip['description']}")
            except Exception as e:
                st.error(f"Bir hata oluştu: {str(e)}")
