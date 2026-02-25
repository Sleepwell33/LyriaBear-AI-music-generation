import asyncio
import socket
import json
import time
import random
import numpy as np
import wave
import pyaudio
import google.genai as genai
from google.genai import types
import os

# ====== 网络代理（如不需要可注释掉） ======
os.environ["http_proxy"] = "http://127.0.0.1:7897"
os.environ["https_proxy"] = "http://127.0.0.1:7897"
os.environ["all_proxy"] = "socks5://127.0.0.1:7897"

# ====== API 配置 ======
API_KEY = "AIzaSyClRjioMUQWO7L22Qx6hEQCcc6vNwfoE0k"
MODEL = "models/lyria-realtime-exp"
BPM_DEFAULT = 90

client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})

# ====== TCP 设置 ======
HOST = '172.20.10.4'
PORT = 8080

# ====== 缓存数据 ======
DATA_BUFFER = []

# ====== 词库 ======
bpm_words = {'very_low': ['subdued', 'slow', 'gentle'],
             'low': ['calm', 'soft', 'relaxed'],
             'medium': ['steady', 'groovy', 'flowing'],
             'high': ['energetic', 'lively', 'danceable'],
             'very_high': ['intense', 'fast', 'hyper']}

light_words = {'low': ['Acoustic Instruments', 'Warm Acoustic Guitar', 'Harp'],
               'medium': ['Electric Guitar', 'Rhodes Piano', 'Synth Pads'],
               'high': ['TR-909 Drum Machine', 'Moog Oscillations', '808 Hip Hop Beat']}

motion_words = {'low': ['Classical', 'Baroque', 'Orchestral Score'],
                'medium': ['Jazz Fusion', 'Chillout', 'Lo-Fi Hip Hop'],
                'high': ['EDM', 'Dubstep', 'Hyperpop']}

hrv_words = {'very_low': ['tense', 'edgy', 'uneasy'],
             'low': ['calm', 'subdued', 'relaxed'],
             'medium': ['balanced', 'steady', 'neutral'],
             'high': ['happy', 'energetic', 'playful'],
             'very_high': ['joyful', 'euphoric', 'excited']}

# ====== 辅助函数 ======
def map_bpm(bpm):
    if bpm < 50: return bpm_words['very_low']
    elif bpm < 60: return bpm_words['low']
    elif bpm < 70: return bpm_words['medium']
    elif bpm < 90: return bpm_words['high']
    else: return bpm_words['very_high']

def map_light(light):
    if light < 500: return light_words['low']
    elif light < 3000: return light_words['medium']
    else: return light_words['high']

def map_motion(mag):
    if mag < 30: return motion_words['low']
    elif mag < 90: return motion_words['medium']
    else: return motion_words['high']

def map_hrv(hrv):
    if hrv < 40: return hrv_words['very_low']
    elif hrv < 60: return hrv_words['low']
    elif hrv < 85: return hrv_words['medium']
    elif hrv < 100: return hrv_words['high']
    else: return hrv_words['very_high']

def generate_prompt(avg_bpm, avg_hrv, avg_light, motion_mag):
    return f"{random.choice(map_bpm(avg_bpm))}, {random.choice(map_light(avg_light))}, {random.choice(map_motion(motion_mag))}, {random.choice(map_hrv(avg_hrv))}"

def compute_motion_amplitude(buffer):
    if not buffer: return 0
    yaw_vals = [d.get("Yaw", 0) for d in buffer]
    pitch_vals = [d.get("Pitch", 0) for d in buffer]
    roll_vals = [d.get("Roll", 0) for d in buffer]
    return max([max(yaw_vals)-min(yaw_vals), max(pitch_vals)-min(pitch_vals), max(roll_vals)-min(roll_vals)])

# ====== 音频接收 ======
async def receive_audio(session):
    CHANNELS, SAMPLE_WIDTH, FRAME_RATE = 2, 2, 44100
    wf = wave.open("output.wav", "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(SAMPLE_WIDTH)
    wf.setframerate(FRAME_RATE)

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pa.get_format_from_width(SAMPLE_WIDTH),
                     channels=CHANNELS,
                     rate=FRAME_RATE,
                     output=True)
    try:
        async for message in session.receive():
            if message.server_content.audio_chunks:
                chunk = message.server_content.audio_chunks[0].data
                wf.writeframes(chunk)
                stream.write(chunk)
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        wf.close()

# ====== ESP32 数据读取异步化 ======
async def esp32_reader(conn, session):
    buffer_fragment = b""
    last_update = time.time()
    while True:
        try:
            raw_data = await asyncio.to_thread(conn.recv, 1024)
            if not raw_data: continue
            buffer_fragment += raw_data
            if b"}" in buffer_fragment:
                parts = buffer_fragment.split(b"}")
                for p in parts[:-1]:
                    try:
                        d = json.loads((p + b"}").decode(errors="ignore").strip())
                        DATA_BUFFER.append(d)
                    except json.JSONDecodeError:
                        continue
                buffer_fragment = parts[-1]
        except Exception as e:
            print("⚠️ ESP32读取错误:", e)

        now = time.time()
        if now - last_update >= 20 and DATA_BUFFER:
            avg_bpm = np.mean([x.get("BPM", BPM_DEFAULT) for x in DATA_BUFFER])
            avg_hrv = np.mean([x.get("HRV", 50) for x in DATA_BUFFER])
            avg_light = np.mean([x.get("Light", 1000) for x in DATA_BUFFER])
            motion_mag = compute_motion_amplitude(DATA_BUFFER)

            prompt_text = generate_prompt(avg_bpm, avg_hrv, avg_light, motion_mag)
            print(f"🎵 WeightedPrompt (20s update): {prompt_text}")

            try:
                await session.set_weighted_prompts(
                    prompts=[types.WeightedPrompt(text=prompt_text, weight=1.0)]
                )
                await session.set_music_generation_config(
                    config=types.LiveMusicGenerationConfig(
                        bpm=int(avg_bpm) if avg_bpm > 60 else BPM_DEFAULT,
                        music_generation_mode=types.MusicGenerationMode.QUALITY
                    )
                )
                await session.reset_context()
            except Exception as e:
                print("⚠️ Lyria API 更新失败:", e)

            DATA_BUFFER.clear()
            last_update = now

# ====== 主逻辑 ======
async def main():
    print(f"📡 Listening on {HOST}:{PORT} ...")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    conn, addr = await asyncio.to_thread(server.accept)
    print(f"✅ Connected by {addr}")
    conn.settimeout(1.0)

    async with client.aio.live.music.connect(model=MODEL) as session, asyncio.TaskGroup() as tg:
        tg.create_task(receive_audio(session))
        tg.create_task(esp32_reader(conn, session))

        # 初始 prompt & 播放
        await session.set_weighted_prompts(prompts=[types.WeightedPrompt(text="Ambient Calm Music", weight=1.0)])
        await session.set_music_generation_config(config=types.LiveMusicGenerationConfig(
            bpm=BPM_DEFAULT,
            music_generation_mode=types.MusicGenerationMode.QUALITY
        ))
        await session.play()
        print("🎶 音乐已开始播放，等待 ESP32 数据输入...")

if __name__ == "__main__":
    asyncio.run(main())