import socks
import asyncio
import wave
import pyaudio
# from google import genai
import google.genai as genai
from google.genai import types
# import requests
#
# resp = requests.get('http://go.to',
#                     dict(http='socks5://host:port',https='socks5://host:port'))
import os
os.environ["http_proxy"] = "http://127.0.0.1:7897"
os.environ["https_proxy"] = "http://127.0.0.1:7897"
os.environ["all_proxy"] = "socks5://127.0.0.1:7897"


# ====== 配置API Key ======
API_KEY = "AIzaSyClRjioMUQWO7L22Qx6hEQCcc6vNwfoE0k"
MODEL = "models/lyria-realtime-exp"
BPM = 90 #这里可以改变节奏，比如和心率数值联动，文档里有写

# ====== 初始提示词 ======
PROMPT_TEXT = """提示词在这里，用英文逗号隔开
"""

# 初始化客户端
client = genai.Client(
    api_key=API_KEY,
    http_options={'api_version': 'v1alpha'}
)

async def receive_audio(session):
    """
    接收实时生成的音频，并边播放边保存
    """
    CHANNELS = 2
    SAMPLE_WIDTH = 2
    FRAME_RATE = 44100

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
            if not message.server_content.audio_chunks:
                continue
            chunk = message.server_content.audio_chunks[0].data
            wf.writeframes(chunk)
            stream.write(chunk)
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        wf.close()

async def prompt_input(session):
    """
    这个函数用于即时读取输入参数，改变音乐
    """
    print("\n🎹 输入新的乐器或风格标签（例如 'Dubstep', 'Jazz Guitar'），回车生效")
    print("输入 'quit' 退出程序\n")
    loop = asyncio.get_event_loop()
    while True:
        # 异步读取终端输入
        new_prompt = await loop.run_in_executor(None, input, ">> ")
        if new_prompt.strip().lower() in ["quit", "exit"]:
            print("⏹ 停止音乐生成...")
            await session.stop()
            break
        if new_prompt.strip():
            print(f"🎯 更新提示词 => {new_prompt}")
            await session.set_weighted_prompts(
                prompts=[types.WeightedPrompt(text=new_prompt, weight=1.0)]
            )

async def main():
    """
    这个函数不用管，是一些其余控制项
    """
    async with (
        client.aio.live.music.connect(model=MODEL) as session,
        asyncio.TaskGroup() as tg,
    ):
        # 启动音频接收和用户输入任务
        tg.create_task(receive_audio(session))
        tg.create_task(prompt_input(session))

        # 设置初始提示词
        await session.set_weighted_prompts(
            prompts=[types.WeightedPrompt(text=PROMPT_TEXT, weight=1.0)]
        )

        # 设置音乐生成参数
        await session.set_music_generation_config(
            config=types.LiveMusicGenerationConfig(
                bpm=BPM,
                temperature=1.0
            )
        )

        print("输入新提示词可以即时更新音乐效果")
        await session.play()

if __name__ == "__main__":
    asyncio.run(main())
