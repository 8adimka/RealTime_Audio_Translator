import asyncio
import json
import os
import subprocess
import sys

from dotenv import load_dotenv
from websockets.client import connect as websocket_connect  # type: ignore

load_dotenv()

SPEECHMATICS_API_KEY = os.getenv("SPEECHMATICS_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.1
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION * 2)
SOURCE_LANG = "en"
TARGET_LANG = "ru"


def detect_pulse_monitor():
    try:
        result = subprocess.run(
            ["pactl", "info"], capture_output=True, text=True, check=True
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
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
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
    if process.stdout is None:
        raise RuntimeError("Failed to open ffmpeg stdout pipe")
    while True:
        data = await process.stdout.read(CHUNK_SIZE)
        if not data:
            break
        yield data


class RealTimeSubtitles:
    def __init__(self):
        self.session_active = False
        self.websocket = None
        self.final_buffer = []
        self.partial_buffer = ""
        self.last_interim_len = 0
        self.initialized = False
        self.translation_cache = {}  # Новый кэш переводов

    def redraw(self, text=None, is_final=False):
        if not self.initialized:
            os.system("clear")
            print("Speechmatics connection established")
            self.initialized = True

        if is_final and text:
            sys.stdout.write("\r" + " " * self.last_interim_len + "\r")
            sys.stdout.flush()
            print(text)
            self.last_interim_len = 0
        elif text:
            sys.stdout.write("\r" + " " * self.last_interim_len + "\r")
            sys.stdout.write(text)
            sys.stdout.flush()
            self.last_interim_len = len(text)

    def print_interim(self, text):
        self.partial_buffer = text
        self.redraw(text=text, is_final=False)

    def print_final(self, text):
        if text and text not in self.final_buffer:
            self.final_buffer.append(text)
            self.redraw(text=text, is_final=True)
            self.partial_buffer = ""

    def maybe_cached(self, text):
        text = text.strip()
        if not text:
            return ""
        if text in self.translation_cache:
            return self.translation_cache[text]
        self.translation_cache[text] = text  # Кэшируем то, что пришло от Speechmatics
        return text

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
                "enable_partials": True,
            },
        }
        try:
            async with websocket_connect(
                url, extra_headers=extra_headers, ping_interval=30, max_size=2**24
            ) as ws:
                self.websocket = ws
                await ws.send(json.dumps(start_msg))

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("message") == "RecognitionStarted":
                        break

                receive_task = asyncio.create_task(self.receive_results(ws))

                async for chunk in read_ffmpeg_audio():
                    if chunk:
                        await ws.send(chunk)

                await ws.send(json.dumps({"message": "EndOfStream"}))
                try:
                    await asyncio.wait_for(receive_task, timeout=5)
                except Exception:
                    receive_task.cancel()
        except Exception as e:
            print(f"Connection error: {e}")

    async def receive_results(self, ws):
        while self.session_active:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)

                if data.get("message") == "AddPartialTranslation":
                    translation = data.get("results", [{}])[0].get("content", "")
                    translation = self.maybe_cached(translation)
                    if translation:
                        self.print_interim(translation)

                elif data.get("message") == "AddTranslation":
                    translation = data.get("results", [{}])[0].get("content", "")
                    translation = self.maybe_cached(translation)
                    if translation:
                        self.print_final(translation)

            except asyncio.TimeoutError:
                print("Timeout waiting for Speechmatics response")
                break
            except Exception as e:
                print(f"Receive error: {e}")
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
