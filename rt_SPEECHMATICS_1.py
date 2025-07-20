import asyncio
import json
import os
import subprocess
import sys

import httpx
from dotenv import load_dotenv
from websockets.client import connect as websocket_connect

load_dotenv()

SPEECHMATICS_API_KEY = os.getenv("SPEECHMATICS_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.05  # seconds (минимальный для максимальной отзывчивости)
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION * 2)  # 16-bit PCM = 2 bytes
SOURCE_LANG = "en"
TARGET_LANG = "ru"


def detect_pulse_monitor():
    """
    Находит monitor-источник, связанный с текущим активным sink'ом (потоком системного звука).
    """
    try:
        result = subprocess.run(
            ["pactl", "info"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Default Sink:"):
                default_sink = line.split(":", 1)[1].strip()
                return f"{default_sink}.monitor"
        raise RuntimeError("Default sink не найден в pactl info")
    except Exception as e:
        print(f"[Monitor detection error]: {e}")
        return None


async def read_ffmpeg_audio():
    monitor_source = detect_pulse_monitor()
    if not monitor_source:
        monitor_source = "alsa_output.pci-0000_00_1f.3.analog-stereo.monitor"
    cmd = [
        "ffmpeg",
        "-f",
        "pulse",
        "-i",
        monitor_source,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        "-f",
        "s16le",
        "-loglevel",
        "error",
        "-",
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    while True:
        data = await process.stdout.read(CHUNK_SIZE)
        if not data:
            break
        yield data


class RealTimeSubtitles:
    def __init__(self):
        self.session_active = False
        self.websocket = None
        self.last_interim_len = 0
        self.partial_buffer = ""
        self.final_buffer = []  # список финальных сегментов для контекста
        self.max_context = 10  # сколько финальных сегментов держать для контекста

    def redraw(self, interim=None):
        sys.stdout.write("\033[2J\033[H")
        for segment in self.final_buffer[-self.max_context :]:
            print(segment)
        if interim:
            print(interim, end="", flush=True)
        else:
            print("", end="", flush=True)

    def print_interim(self, text):
        self.last_interim_len = len(text)
        self.redraw(interim=text)

    def print_final(self, text):
        self.last_interim_len = 0
        self.redraw(interim=None)

    def get_context(self):
        return " ".join(self.final_buffer[-self.max_context :])

    async def process_audio_stream(self):
        self.session_active = True
        url = "wss://eu2.rt.speechmatics.com/v2"
        extra_headers = {"Authorization": f"Bearer {SPEECHMATICS_API_KEY}"}
        start_msg = {
            "message": "StartRecognition",
            "audio_format": {
                "type": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": SAMPLE_RATE,
            },
            "transcription_config": {
                "language": SOURCE_LANG,
                "operating_point": "enhanced",
                "enable_partials": True,
                "max_delay": 1.0,
            },
            "translation_config": {
                "target_languages": [TARGET_LANG],
                "enable_partials": True,  # Включение частичных переводов
            },
        }
        try:
            async with websocket_connect(
                url, extra_headers=extra_headers, ping_interval=30, max_size=2**24
            ) as ws:
                sys.stdout.write("\033[2J\033[H")
                print("Speechmatics connection established")
                self.websocket = ws

                # Отправляем StartRecognition
                await ws.send(json.dumps(start_msg))

                # Ждём RecognitionStarted
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("message") == "RecognitionStarted":
                        break

                # Запускаем приём результатов параллельно с отправкой аудио
                receive_task = asyncio.create_task(self.receive_results(ws))

                # Отправляем аудиоданные
                try:
                    async for chunk in read_ffmpeg_audio():
                        if not isinstance(chunk, bytes):
                            break
                        if len(chunk) == 0:
                            continue
                        await ws.send(chunk)
                except Exception:
                    pass

                # Завершаем поток
                await ws.send(json.dumps({"message": "EndOfStream"}))

                # Ждём завершения приёма результатов
                try:
                    await asyncio.wait_for(receive_task, timeout=5)
                except Exception:
                    receive_task.cancel()
        except Exception:
            pass

    async def receive_results(self, ws):
        while self.session_active:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                if data.get("message") == "AddPartialTranslation":
                    translation = data.get("results", [{}])[0].get("content", "")
                    if translation:
                        self.partial_buffer = translation
                        self.print_interim(self.partial_buffer)
                elif data.get("message") == "AddTranslation":
                    translation = data.get("results", [{}])[0].get("content", "")
                    if translation:
                        self.final_buffer.append(translation)
                        if len(self.final_buffer) > self.max_context:
                            self.final_buffer = self.final_buffer[-self.max_context :]
                        self.partial_buffer = ""
                        self.print_final(translation)
            except asyncio.TimeoutError:
                break
            except Exception:
                break

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.process_audio_stream())
        except KeyboardInterrupt:
            self.session_active = False
            print("Interrupted")
        finally:
            loop.close()


if __name__ == "__main__":
    translator = RealTimeSubtitles()
    translator.run()
