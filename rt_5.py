import asyncio
import json
import os
import subprocess
import sys

import httpx
from dotenv import load_dotenv
from websockets.client import connect as websocket_connect  # type: ignore

load_dotenv()

# Конфигурация
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
TRANSLATION_LANG = "EN"  # Изменяемо, напр. с EN на ES
CHUNK_DURATION = 0.1  # секунды
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION * 2)  # 16-bit PCM = 2 байта


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
        "-f",
        "s16le",
        "-loglevel",
        "error",
        "-",
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    if not process.stdout:
        raise RuntimeError("Failed to get stdout from ffmpeg process")
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
        self.translation_cache = {}  # Новый: кэш переводов

    def redraw(self, text=None, is_final=False):
        if not self.initialized:
            os.system("clear")
            print("Deepgram connection established")
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

    async def translate_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        if text in self.translation_cache:
            return self.translation_cache[text]

        url = "https://api-free.deepl.com/v2/translate"
        params = {
            "auth_key": DEEPL_API_KEY,
            "text": text,
            "target_lang": "RU",
            "source_lang": TRANSLATION_LANG,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, data=params)
                response.raise_for_status()
                result = response.json()
                translated = result["translations"][0]["text"]
                self.translation_cache[text] = translated
                return translated
            except Exception as e:
                print(f"[Translation error]: {e}")
                return text  # fallback

    async def process_audio_stream(self):
        self.session_active = True
        try:
            async with websocket_connect(
                "wss://api.deepgram.com/v1/listen"
                "?encoding=linear16&sample_rate=16000&channels=1"
                f"&model=nova-2&language={TRANSLATION_LANG}&punctuate=true"
                "&interim_results=true&endpointing=300",
                extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                ping_interval=10,
            ) as ws:
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

                    translated = await self.translate_text(transcript)

                    if data.get("is_final", False):
                        self.print_final(translated)
                    else:
                        self.print_interim(translated)

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
            print("Interrupted")
        finally:
            loop.close()


if __name__ == "__main__":
    translator = RealTimeSubtitles()
    translator.run()
