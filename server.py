import asyncio
import json
import os
import io
import time
import uuid

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
import uvicorn
import openai_api,ollama_api
from fastapi.staticfiles import StaticFiles
app = FastAPI()

# 挂载静态文件目录
app.mount("/web", StaticFiles(directory="web"), name="web")

# 初始化 faster-whisper 模型
model = WhisperModel("./whisper-large-v3-turbo", device="cuda", compute_type="int8")
os.makedirs("data", exist_ok=True)

# 全局变量，用于跟踪时间偏移
global_audio_offset = 0.0


def translate_text_local(text, source_lang="", target_lang="中文", pre_prompt=None, pre_line=None, post_line=None):
    """调用 xAI Grok API 进行翻译"""
    prompt = (
        f"将下面的这句翻译为 {target_lang}, 保持原文的语义、语气和风格,直接给出最优的翻译结果,不要在翻译结果后面添加任何注释内容,除了翻译结果不要任何多余的内容,包括解释、注释、说明等,"
        f"不要添加任何注释内容,翻译结果保持一行,不要添加换行符,如果无法翻译则保留原文\n {text}")
    if pre_prompt:
        prompt = pre_prompt + ' ' + prompt

    return ollama_api.chat(prompt)


added_segments = []


async def process_audio_stream(temp_file_path: str, websocket: WebSocket, segment_duration: int = 10000,
                               session_id: str = None):
    """处理视频分片的音频并生成字幕，返回新的时间偏移"""
    global global_audio_offset
    audio_duration = 0
    try:
        # 尝试加载临时文件为 AudioSegment
        audio = AudioSegment.from_file(temp_file_path, format="mp4")
        audio_duration = len(audio)  # 音频时长（毫秒）
        print('audio_duration', audio_duration, 'session_id', session_id)
        if audio_duration and audio_duration / 1000 < global_audio_offset:
            # print(
            #     f"Session {session_id}: 当前音频时长 {audio_duration / 1000:.2f}s 小于全局偏移 {global_audio_offset:.2f}s，跳过处理")
            return global_audio_offset
        # 分段处理音频（每段 10 秒）
        for i in range(0, len(audio), segment_duration):
            if i in added_segments:
                continue
            if i / 1000 < global_audio_offset:
                # print(f"Session {session_id[-8:]}: 跳过已处理的分片 {i / 1000:.2f}s")
                added_segments.append(i)
                continue
            added_segments.append(i)
            segment = audio[i:i + segment_duration]
            segment_path = f"data/temp_segment_{i}_{int(time.time())}.wav"
            segment.export(segment_path, format="wav")

            # 使用 faster-whisper 转录
            segments, _ = model.transcribe(segment_path)
            os.remove(segment_path)

            # 累加分段偏移量（基于全局偏移）
            segment_offset = i / 1000.0  # 当前分片内的偏移（秒）
            for seg in segments:
                if session_id != current_session_id:
                    print(f"Session {session_id}: 已取消，跳过分片处理")
                    return global_audio_offset
                subtitle = {
                    "type": "subtitle",
                    "start": f"{seg.start + segment_offset :.3f}",
                    "end": f"{seg.end + segment_offset :.3f}",
                    "text": translate_text_local(seg.text.strip())
                }
                # print('segment_offset', segment_offset, 'global_audio_offset', global_audio_offset)
                print('subtitle', subtitle, 'session_id', session_id)

                await websocket.send_text(json.dumps(subtitle))

            # 模拟实时处理（根据实际需求调整）
            await asyncio.sleep(0.1)  # 降低延迟

        # 更新全局时间偏移
        # global_audio_offset += audio_duration / 1000.0
        return global_audio_offset

    except CouldntDecodeError as e:
        print(f"无法解码视频分片 audio_duration ", audio_duration, 'session_id', session_id)
        await websocket.send_text(json.dumps({"type": "error", "message": "视频分片解码失败，可能数据不完整"}))
        return global_audio_offset
    except Exception as e:
        print(f"处理音频流时出错: {e}")
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        return global_audio_offset


@app.get("/")
async def get_index():
    return FileResponse("web/index.html")


current_session_id = None


@app.websocket("/ws/subtitles")
async def websocket_endpoint(websocket: WebSocket):
    global current_session_id
    # 生成唯一会话 ID
    session_id = str(uuid.uuid4())
    current_session_id = session_id
    print(f"Session {session_id}: 新 WebSocket 连接建立")
    await websocket.accept()
    temp_file_path = "data/" + session_id + '.mp4'  # 临时文件路径
    global global_audio_offset, added_segments
    cancel_event = asyncio.Event()
    # 初始化临时文件
    print('websocket_endpoint 初始化临时文件')
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)
    added_segments = []  # 清空已处理的分片列表
    try:

        while True:
            data = await websocket.receive()
            print('data type', data["type"])
            if data["type"] == "websocket.receive":
                if "text" in data:
                    print('data', data)
                    # 解析文本消息
                    message = json.loads(data["text"])
                    if message.get("type") == "end":
                        print("接收到结束标志，完成视频处理")
                        # 最后一次处理临时文件（确保所有数据处理完毕）
                        await process_audio_stream(temp_file_path, websocket, session_id=session_id)
                        break
                    elif message.get("type") == "seek":
                        # 处理 seek 事件
                        seek_time = float(message.get("time", 0))
                        print(f"Session {session_id}: 接收到 seek 事件，时间点: {seek_time}s")
                        global_audio_offset = seek_time  # 更新全局时间偏移

                        await websocket.send_text(
                            json.dumps({"type": "seek_ack", "message": f"已同步到时间点 {seek_time}s"}))
                    else:
                        await websocket.send_text(json.dumps({"type": "error", "message": "未知消息类型"}))
                else:
                    if session_id != current_session_id:
                        print(f"Session {session_id}: 已取消，跳过接收数据")
                        break
                    # print('接收到视频数据，保存到临时文件')
                    # 接收分片数据并追加到临时文件
                    with open(temp_file_path, "ab") as f:
                        f.write(data["bytes"])
                    print(
                        f"Session {session_id[-8:]}: 接收到: {os.path.getsize(temp_file_path) / 1024 / 1024} M字节",
                        temp_file_path)

                    # 尝试处理当前分片
                    await process_audio_stream(temp_file_path, websocket, session_id=session_id)
            elif data["type"] == "websocket.disconnect":
                print('WebSocket 断开连接:  ', data)

            else:
                await websocket.send_text(json.dumps({"type": "error", "message": f"不支持的数据类型: {data['type']}"}))
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
    finally:
        print("finally called")
        # 清理临时文件
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        await websocket.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
