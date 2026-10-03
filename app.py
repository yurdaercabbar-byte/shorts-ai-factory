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

api_key_input = st.sidebar.text_input("OpenAI API Key:", type="password")
video_url = st.text_input("YouTube Video URL'sini Yapıştırın:")

def download_video(url):
    output_path = "input_video.mp4"
    
    # Yöntem 1: Cobalt API V10
    try:
        api_endpoint = "https://co.wuk.sh/api/json"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "url": url,
            "vCodec": "h264",
            "vQuality": "720",
            "isAudioOnly": False
        }
        
        response = requests.post(api_endpoint, json=payload, headers=headers, timeout=15)
        data = response.json()
        
        dl_url = data.get("url")
        if dl_url:
            r = requests.get(dl_url, stream=True, timeout=30)
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            return output_path
    except Exception:
        pass

    # Yöntem 2: Invidious Open Source Proxy API (Yedek)
    try:
        # Video ID çekme
        video_id = url.split("v=")[-1].split("&")[0].split("?")[0].split("/")[-1]
        inv_api = f"https://invidious.nerdvpn.de/api/v1/videos/{video_id}"
        resp = requests.get(inv_api, timeout=15).json()
        
        # En uygun MP4 formatını seçme
        for fmt in resp.get("formatStreams", []):
            if "video/mp4" in fmt.get("container", "") or "mp4" in fmt.get("type", ""):
                v_url = fmt.get("url")
                r = requests.get(v_url, stream=True, timeout=30)
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
                return output_path
    except Exception as e:
        raise Exception(f"Video indirilemedi, sunucu engeline takıldı. Hata: {str(e)}")

    raise Exception("Video akışı bulunamadı. Lütfen başka bir YouTube linki deneyin.")

def get_face_center_x(video_path):
    cap = cv2.VideoCapture(video_path)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    total_x, count, frame_count = 0, 0, 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % 15 == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            for (x, y, w, h) in faces:
                total_x += (x + w // 2)
                count += 1
        frame_count += 1
        if count > 40:
            break
    cap.release()
    return int(total_x / count) if count > 0 else None

def analyze_video(video_path, api_key):
    client = openai.OpenAI(api_key=api_key)
    model = whisper.load_model("base")
    result = model.transcribe(video_path)
    
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

if st.button("Shorts Üret") and video_url:
    if not api_key_input:
        st.error("Lütfen sol panelden OpenAI API Key girin!")
    else:
        with st.spinner("Video indiriliyor ve bulutta işleniyor..."):
            try:
                v_file = download_video(video_url)
                center_x = get_face_center_x(v_file)
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
