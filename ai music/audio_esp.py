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

# ====== 网络代理 ======
os.environ["http_proxy"] = "http://127.0.0.1:7897"
os.environ["https_proxy"] = "http://127.0.0.1:7897"
os.environ["all_proxy"] = "socks5://127.0.0.1:7897"

# ====== API 配置 ======
API_KEY = "SetAPIKey"
MODEL = "models/lyria-realtime-exp"
BPM_DEFAULT = 90

client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})

# ====== TCP ======
HOST = '172.20.10.4'
PORT = 8080

# ====== 全局缓存（移动到函数外部） ======
MPU_BUFFER = []
LIGHT_BUFFER = []
HR_BUFFER = []

# ====== 阈值 ======
MPU_THRESHOLD = 15
LIGHT_THRESHOLD = 5

# ====== 阶段状态 ======
CURRENT_STAGE = "MPU"  # MPU → LIGHT → MPU → ...

# ====== 词库 ======
bpm_words = {
    'very_low': ['subdued', 'slow', 'gentle'],
    'low': ['calm', 'soft', 'relaxed'],
    'medium': ['steady', 'groovy', 'flowing'],
    'high': ['energetic', 'lively', 'danceable'],
    'very_high': ['intense', 'fast', 'hyper']
}

light_words = {
    'low': ['Acoustic Instruments', 'Warm Acoustic Guitar', 'Harp'],
    'medium': ['Electric Guitar', 'Rhodes Piano', 'Synth Pads'],
    'high': ['TR-909 Drum Machine', 'Moog Oscillations', '808 Hip Hop Beat']
}

motion_words = {
    'low': ['Classical', 'Baroque', 'Orchestral Score'],
    'medium': ['Jazz Fusion', 'Chillout', 'Lo-Fi Hip Hop'],
    'high': ['EDM', 'Dubstep', 'Hyperpop']
}

hrv_words = {
    'very_low': ['tense', 'edgy', 'uneasy'],
    'low': ['calm', 'subdued', 'relaxed'],
    'medium': ['balanced', 'steady', 'neutral'],
    'high': ['happy', 'energetic', 'playful'],
    'very_high': ['joyful', 'euphoric', 'excited']
}


# ====== 映射函数 ======
def map_bpm(bpm):
    if bpm < 50:
        return bpm_words['very_low']
    elif bpm < 60:
        return bpm_words['low']
    elif bpm < 70:
        return bpm_words['medium']
    elif bpm < 90:
        return bpm_words['high']
    else:
        return bpm_words['very_high']


def map_light(light):
    if light < 500:
        return light_words['low']
    elif light < 3000:
        return light_words['medium']
    else:
        return light_words['high']


def map_motion(mag):
    if mag < 30:
        return motion_words['low']
    elif mag < 90:
        return motion_words['medium']
    else:
        return motion_words['high']


def map_hrv(hrv):
    if hrv < 40:
        return hrv_words['very_low']
    elif hrv < 60:
        return hrv_words['low']
    elif hrv < 85:
        return hrv_words['medium']
    elif hrv < 100:
        return hrv_words['high']
    else:
        return hrv_words['very_high']


def generate_prompt(avg_bpm, avg_hrv, avg_light, motion_mag):
    return (
        f"{random.choice(map_bpm(avg_bpm))}, "
        f"{random.choice(map_motion(motion_mag))}, "
        f"{random.choice(map_light(avg_light))}, "
        f"{random.choice(map_hrv(avg_hrv))}"
    )


# ====== MPU 幅度计算 ======
def compute_motion_amplitude(buffer):
    if not buffer: return 0
    yaw = [d.get("yaw", 0) for d in buffer]  # 注意：小写 yaw
    pitch = [d.get("pitch", 0) for d in buffer]  # 注意：小写 pitch
    roll = [d.get("roll", 0) for d in buffer]  # 注意：小写 roll
    return max(
        max(yaw) - min(yaw),
        max(pitch) - min(pitch),
        max(roll) - min(roll)
    )


# ====== 音频接收 ======
async def receive_audio(session):
    wf = wave.open("output.wav", "wb")
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(44100)

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=2, rate=44100, output=True)

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


# ====== 数据分流函数 ======
def route_data(d):
    global MPU_BUFFER, LIGHT_BUFFER, HR_BUFFER

    data_type = d.get("type", "").lower()

    if data_type == "mpu":
        # 标准化键名（转换为大写以匹配后续处理）
        mpu_data = {
            "Yaw": d.get("yaw", 0),
            "Pitch": d.get("pitch", 0),
            "Roll": d.get("roll", 0)
        }
        MPU_BUFFER.append(mpu_data)
        print(f"✅ 收到 MPU 数据: {mpu_data}")

    elif data_type == "light":
        light_data = {"Light": d.get("lux", 0)}
        LIGHT_BUFFER.append(light_data)
        print(f"💡 收到 LIGHT 数据: {light_data}")

    elif data_type == "hr" or "BPM" in d or "HRV" in d:
        hr_data = {}
        if "BPM" in d:
            hr_data["BPM"] = d["BPM"]
        if "HRV" in d:
            hr_data["HRV"] = d["HRV"]
        if "HR" in d:
            hr_data["BPM"] = d["HR"]  # 假设 HR 就是 BPM
        HR_BUFFER.append(hr_data)
        print(f"❤️ 收到 HR 数据: {hr_data}")


# ====== 阶段触发条件 ======
def ready_for_update():
    global CURRENT_STAGE
    if CURRENT_STAGE == "MPU":
        return len(MPU_BUFFER) >= MPU_THRESHOLD
    else:
        return len(LIGHT_BUFFER) >= LIGHT_THRESHOLD


# ====== ESP32 读取（修正版） ======
async def esp32_reader(conn, session):
    global MPU_BUFFER, LIGHT_BUFFER, HR_BUFFER, CURRENT_STAGE

    buffer = b""
    last_update = time.time()
    last_keepalive = time.time()

    while True:
        try:
            # 接收数据
            raw = await asyncio.to_thread(conn.recv, 1024)
            if not raw:
                await asyncio.sleep(0.01)
                continue

            buffer += raw

            # 按行分割（因为数据是按行发送的）
            lines = buffer.split(b'\n')
            # 保留最后一行不完整的数据
            buffer = lines[-1]

            for line in lines[:-1]:  # 处理完整的行
                line = line.strip()
                if not line:
                    continue

                try:
                    # 解析 JSON
                    d = json.loads(line.decode('utf-8', errors='ignore'))
                    print(f"📥 收到原始数据: {line.decode('utf-8', errors='ignore')}")

                    # 分流处理
                    route_data(d)

                except json.JSONDecodeError as e:
                    print(f"❌ JSON 解析错误: {e}, 数据: {line}")
                    continue
                except Exception as e:
                    print(f"❌ 数据处理错误: {e}")
                    continue

        except socket.timeout:
            # 正常超时，继续循环
            pass
        except Exception as e:
            print(f"⚠️ ESP32 读取错误: {e}")
            await asyncio.sleep(0.1)
            continue

        # ===== 状态打印 =====
        print(
            f"[状态] MPU:{len(MPU_BUFFER)} "
            f"LIGHT:{len(LIGHT_BUFFER)} "
            f"HR:{len(HR_BUFFER)} "
            f"阶段:{CURRENT_STAGE}"
        )

        # ===== 检查是否满足更新条件 =====
        if ready_for_update():
            try:
                print(f"🎵 触发 {CURRENT_STAGE} 阶段更新...")

                # 根据当前阶段选择数据
                if CURRENT_STAGE == "MPU":
                    # 使用 MPU 数据
                    motion_mag = compute_motion_amplitude(MPU_BUFFER)
                    avg_light = np.mean([x.get("Light", 1000) for x in LIGHT_BUFFER]) if LIGHT_BUFFER else 1000
                    avg_hrv = np.mean([x.get("HRV", 75) for x in HR_BUFFER]) if HR_BUFFER else 75
                    avg_bpm = np.mean([x.get("BPM", BPM_DEFAULT) for x in HR_BUFFER]) if HR_BUFFER else BPM_DEFAULT

                    prompt_text = generate_prompt(avg_bpm, avg_hrv, avg_light, motion_mag)
                    print(f"🎵 生成 Prompt: {prompt_text}")

                    # 更新 Lyria
                    await session.set_weighted_prompts(
                        prompts=[types.WeightedPrompt(text=prompt_text, weight=1.0)]
                    )

                    # 清空 MPU 缓存
                    MPU_BUFFER.clear()

                else:  # LIGHT 阶段
                    # 使用光照数据
                    avg_light = np.mean([x.get("Light", 1000) for x in LIGHT_BUFFER]) if LIGHT_BUFFER else 1000
                    avg_hrv = np.mean([x.get("HRV", 75) for x in HR_BUFFER]) if HR_BUFFER else 75
                    avg_bpm = np.mean([x.get("BPM", BPM_DEFAULT) for x in HR_BUFFER]) if HR_BUFFER else BPM_DEFAULT

                    prompt_text = generate_prompt(avg_bpm, avg_hrv, avg_light, 0)
                    print(f"💡 生成 Prompt: {prompt_text}")

                    # 更新 Lyria
                    await session.set_weighted_prompts(
                        prompts=[types.WeightedPrompt(text=prompt_text, weight=1.0)]
                    )

                    # 清空 LIGHT 缓存
                    LIGHT_BUFFER.clear()

                # 切换阶段
                CURRENT_STAGE = "LIGHT" if CURRENT_STAGE == "MPU" else "MPU"
                print(f"🔄 切换到 {CURRENT_STAGE} 阶段")

            except Exception as e:
                print(f"⚠️ Lyria API 更新失败: {e}")

        # ===== 防止 Lyria 被踢：强制 keep-alive =====
        if time.time() - last_keepalive > 10:
            try:
                print("🔄 发送 keep-alive...")
                await session.set_weighted_prompts(
                    prompts=[types.WeightedPrompt(text="ambient", weight=1.0)]
                )
                last_keepalive = time.time()
            except Exception as e:
                print(f"⚠️ Keep-alive 失败: {e}")

        await asyncio.sleep(0.05)


# ====== 主入口 ======
async def main():
    print(f"📡 监听 {HOST}:{PORT} ...")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)

    conn, addr = await asyncio.to_thread(server.accept)
    print(f"✅ 已连接: {addr}")
    conn.settimeout(0.1)  # 设置较小的超时时间

    async with client.aio.live.music.connect(model=MODEL) as session:
        # 初始化配置
        await session.set_weighted_prompts(
            prompts=[types.WeightedPrompt(text="Ambient Calm Music", weight=1.0)]
        )
        await session.set_music_generation_config(
            config=types.LiveMusicGenerationConfig(
                bpm=BPM_DEFAULT,
                music_generation_mode=types.MusicGenerationMode.QUALITY
            )
        )
        await session.play()
        print("🎶 音乐已开始播放，等待 ESP32 数据输入...")

        # 运行两个任务
        await asyncio.gather(
            receive_audio(session),
            esp32_reader(conn, session)
        )


if __name__ == "__main__":
    asyncio.run(main())