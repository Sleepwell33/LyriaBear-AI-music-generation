import socket
import time
import json

HOST = '172.20.10.4'  # 本机 IP
PORT = 8080

# 缓冲数据，存每条记录: [BPM, HRV, Light, Yaw, Pitch, Roll, timestamp]
data_buffer = []

last_calc_time = time.time()

# 词库示例（可按你之前提供的完整列表替换）
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
    # 从每组词库随机选一个词
    import random
    bpm_word = random.choice(map_bpm(avg_bpm))
    light_word = random.choice(map_light(avg_light))
    motion_word = random.choice(map_motion(motion_mag))
    hrv_word = random.choice(map_hrv(avg_hrv))
    return f"{bpm_word}, {light_word}, {motion_word}, {hrv_word}"


print(f"📡 Listening on {HOST}:{PORT} ...")
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen(1)
    conn, addr = s.accept()
    print(f"✅ Connected by {addr}")

    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                print("❌ Connection closed by ESP32.")
                break

            decoded = data.decode().strip()
            print(f"📨 Received: {decoded}")

            try:
                d = json.loads(decoded)
                t = time.time()
                data_buffer.append([d['BPM'], d['HRV'], d['Light'], d['Yaw'], d['Pitch'], d['Roll'], t])
            except:
                continue

            current_time = time.time()
            # 每10秒计算一次
            if current_time - last_calc_time >= 10:
                # 取10秒内的数据
                recent_data = [x for x in data_buffer if current_time - x[6] <= 10]
                if recent_data:
                    avg_bpm = sum([x[0] for x in recent_data]) / len(recent_data)
                    avg_hrv = sum([x[1] for x in recent_data]) / len(recent_data)
                    avg_light = sum([x[2] for x in recent_data]) / len(recent_data)
                    # 计算动作幅度
                    yaw_vals = [x[3] for x in recent_data]
                    pitch_vals = [x[4] for x in recent_data]
                    roll_vals = [x[5] for x in recent_data]
                    motion_mag = max([max(yaw_vals) - min(yaw_vals),
                                      max(pitch_vals) - min(pitch_vals),
                                      max(roll_vals) - min(roll_vals)])

                    prompt = generate_prompt(avg_bpm, avg_hrv, avg_light, motion_mag)
                    print(f"🎵 WeightedPrompt (10s update): {prompt}")
                last_calc_time = current_time
