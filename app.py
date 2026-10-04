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

# Yan Panel - Sadece OpenAI API Key yeterli
api_key_input = st.sidebar.text_input("OpenAI API Key:", type="password")

st.write("---")
tab1, tab2 = st.tabs(["🔗 YouTube Linki İle (Akıllı Proxy)", "📁 Doğrudan Video Yükle"])

with tab1:
    video_url = st.text_input("YouTube Video URL'sini Yapıştırın:")

with tab2:
    uploaded_file = st.file_uploader("Cihazınızdan Video Seçin (Max 1 GB):", type=["mp4", "mov", "mkv", "avi"])

def download_youtube_smart_proxy(url):
    output_path = "input_video.mp4"
    if os.path.exists(output_path):
        os.remove(output_path)

    # 1. YÖNTEM: Cobalt API Ağları (En hızlı ve yüksek kalite)
    cobalt_instances = [
        "https://api.cobalt.tools",
        "https://cobalt-api.kwiatek.xyz",
        "https://cobalt.q13.cz",
        "https://co.wuk.sh"
    ]

    for instance in cobalt_instances:
        try:
            headers = {"Accept": "application/json", "Content-Type": "application/json"}
            payload = {"url": url, "videoQuality": "720"}
            res = requests.post(f"{instance}/", json=payload, headers=headers, timeout=8)
            if res.status_code == 200:
                stream_url = res.json().get("url")
                if stream_url:
                    r = requests.get(stream_url, stream=True, timeout=60)
                    with open(output_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=2*1024*1024):
                            if chunk:
                                f.write(chunk)
                    return output_path
        except Exception:
            continue

    # 2. YÖNTEM: Piped API Ağları (Cobalt takılırsa yedek hat)
    video_id = url.split("v=")[-1].split("&")[0].split("?")[0].split("/")[-1]
    piped_instances = [
        "https://pipedapi.kavin.rocks",
        "https://api.piped.privacydev.net",
        "https://pipedapi.tokhmi.xyz"
    ]

    for instance in piped_instances:
        try:
            api_url = f"{instance}/streams/{video_id}"
            resp = requests.get(api_url, timeout=8)
            if resp.status_code == 200:
                streams = resp.json().get("videoStreams", [])
                best_stream = None
                for s in streams:
                    if s.get("container") == "mp4" and not s.get("videoOnly"):
                        best_stream = s.get("url")
                        break
                if best_stream:
                    r = requests.get(best_stream, stream=True, timeout=60)
                    with open(output_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=2*1024*1024):
                            if chunk:
                                f.write(chunk)
                    return output_path
        except Exception:
            continue

    raise Exception("YouTube indirme ağları şu an yanıt vermedi. Lütfen birkaç dakika sonra tekrar deneyin veya videoyu dosya olarak yükleyin.")

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
    else:
        v_file = "input_video.mp4"
        with st.spinner("Video link üzerinden çekiliyor ve işleniyor..."):
            try:
                if video_url:
                    v_file = download_youtube_smart_proxy(video_url)
                elif uploaded_file is not None:
                    with open(v_file, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                else:
                    st.warning("Lütfen bir YouTube linki girin veya video dosyası yükleyin.")
                    st.stop()

                st.info("Kare tespiti ve yüz odağı yapılıyor...")
                center_x = get_face_center_x(v_file)
                
                st.info("Ses çözümleniyor ve OpenAI ile en viral anlar seçiliyor...")
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
