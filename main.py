import os
import time
import json
import glob
import subprocess
from google.generativeai import configure as genai_configure
import google.generativeai as genai
from gtts import gTTS
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont, ImageOps
import textwrap
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# ========== SECRETS (From GitHub Settings) ==========
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

# ========== GEMINI CONTENT ==========
genai_configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash-lite-preview")

def generate_youtube_content(topic):
    prompt = f"""
    Topic: "{topic}". Generate JSON only:
    {{"title": "Catchy title (max 70 chars)",
     "description": "200 words + 5 hashtags",
     "script": "60-sec narration script",
     "tags": "8 tags, comma separated"}}
    """
    response = model.generate_content(prompt)
    text = response.text.strip().strip("```json").strip("```")
    return json.loads(text)

# ========== VOICEOVER ==========
def create_voiceover(script, output="voiceover.mp3"):
    tts = gTTS(script, lang='en', slow=False)
    tts.save(output)
    return output

# ========== STOCK IMAGES ==========
def get_stock_images(query, count=6):
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/v1/search?query={query}&per_page={count}&orientation=landscape"
    resp = requests.get(url, headers=headers).json()
    paths = []
    for i, photo in enumerate(resp["photos"][:count]):
        img_url = photo["src"]["large"]
        path = f"img_{i}.jpg"
        with open(path, "wb") as f:
            f.write(requests.get(img_url).content)
        paths.append(path)
    return paths

# ========== BUILD VIDEO ==========
def build_video(images, audio, title, output="video.mp4"):
    audio_clip = AudioFileClip(audio)
    dur_per_img = audio_clip.duration / len(images)
    
    clips = []
    for img in images:
        clip = (ImageClip(img, duration=dur_per_img)
                .resize(lambda t: 1 + 0.02 * t)
                .set_position("center"))
        clips.append(clip)
    
    video = concatenate_videoclips(clips, method="compose")
    txt_clip = (TextClip(title[:50], fontsize=60, color='white', font='Arial-Bold')
                .set_position(('center', 'bottom')).set_duration(3))
    
    final = CompositeVideoClip([video.set_audio(audio_clip), txt_clip])
    final = final.resize((1280, 720))
    final.write_videofile(output, fps=24, codec="libx264", audio_codec="aac",
                          temp_audiofile="temp.m4a", remove_temp=True, verbose=False, logger=None)
    return output

# ========== YOUTUBE UPLOAD ==========
def get_youtube_service():
    creds_data = {
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": YOUTUBE_CLIENT_ID,
        "client_secret": YOUTUBE_CLIENT_SECRET,
        "refresh_token": YOUTUBE_REFRESH_TOKEN,
        "token": "",
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"]
    }
    creds = Credentials.from_authorized_user_info(creds_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

def upload_video(video_path, title, desc, tags):
    yt = get_youtube_service()
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags.split(","),
                    "categoryId": "28"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status: print(f"Upload: {int(status.progress()*100)}%")
    return resp["id"]

# ========== MAIN LOOP ==========
def process_topic(topic):
    print(f"🚀 Processing: {topic}")
    
    # 1. Gemini
    content = generate_youtube_content(topic)
    title, desc, script, tags = content["title"], content["description"], content["script"], content["tags"]
    
    # 2. Voice
    audio = create_voiceover(script)
    
    # 3. Images + Video
    images = get_stock_images(topic)
    video = build_video(images, audio, title)
    
    # 4. Upload
    video_id = upload_video(video, title, desc, tags)
    print(f"✅ LIVE: https://youtube.com/watch?v={video_id}")
    
    # Cleanup
    for f in glob.glob("img_*.jpg") + glob.glob("*.mp3") + ["video.mp4"]:
        os.remove(f)

if __name__ == "__main__":
    topics = [
        "Python Tips 2026",  # Add your topics here
        "AI News Today"
    ]
    for topic in topics:
        process_topic(topic)
        time.sleep(300)  # 5 min cooldown
