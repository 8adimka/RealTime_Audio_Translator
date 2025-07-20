import asyncio
import json
import os
import subprocess
import sys

import httpx
from dotenv import load_dotenv
from websockets.client import connect as websocket_connect

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.15
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION * 2)


def detect_pulse_monitor():
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
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "-loglevel",
        "error",
        "-",
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    while True:
        data = await process.stdout.read(CHUNK_SIZE)
        if not data:
            break
        yield data


class Translator:
    def __init__(self):
        self.cache = {}

    async def translate(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text in self.cache:
            return self.cache[text]

        url = "https://api-free.deepl.com/v2/translate"
        params = {
            "auth_key": DEEPL_API_KEY,
            "text": text,
            "target_lang": "RU",
            "source_lang": "EN",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=params)
                response.raise_for_status()
                result = response.json()
                translated = result["translations"][0]["text"]
                self.cache[text] = translated
                return translated
            except Exception as e:
                print(f"[Translation error]: {e}")
                return text


class RealTimeSubtitles:
    def __init__(self):
        self.session_active = False
        self.websocket = None
        self.translator = Translator()
        self.final_segments = []
        self.interim_segment = ""

    def redraw(self):
        sys.stdout.write("\033[2J\033[H")  # очистка экрана
        sys.stdout.flush()
        full_text = " ".join(self.final_segments)
        print(full_text)
        if self.interim_segment:
            print(self.interim_segment, end="", flush=True)

    def update_interim(self, text):
        self.interim_segment = text
        self.redraw()

    def append_final(self, text):
        self.final_segments.append(text)
        self.interim_segment = ""  # очищаем временную строку
        self.redraw()

    async def process_audio_stream(self):
        self.session_active = True
        try:
            async with websocket_connect(
                "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1&model=nova-2&language=en&punctuate=true&interim_results=true&endpointing=300",
                extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                ping_interval=10,
            ) as ws:
                print("Deepgram connection established")
                self.websocket = ws

                receive_task = asyncio.create_task(self.receive_results(ws))
                async for chunk in read_ffmpeg_audio():
                    try:
                        await ws.send(chunk)
                    except Exception as e:
                        print(f"Send error: {e}")
                        break

                receive_task.cancel()
                await ws.send(json.dumps({"type": "CloseStream"}))
        except Exception as e:
            print(f"Connection error: {e}")

    async def receive_results(self, ws):
        while self.session_active:
            try:
                result = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(result)

                if "channel" in data:
                    transcript = data["channel"]["alternatives"][0]["transcript"]
                    if not transcript.strip():
                        continue

                    if data.get("is_final", False):
                        translated = await self.translator.translate(transcript)
                        self.append_final(translated)
                    else:
                        translated = await self.translator.translate(transcript)
                        self.update_interim(translated)

            except asyncio.TimeoutError:
                print("Timeout waiting for Deepgram response")
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
            print("\nInterrupted")
        finally:
            loop.close()


if __name__ == "__main__":
    translator = RealTimeSubtitles()
    translator.run()
