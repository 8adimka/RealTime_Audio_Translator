import asyncio
import json
import os
import subprocess
import sys

from dotenv import load_dotenv
from websockets.client import connect  # type: ignore

load_dotenv()

SPEECHMATICS_API_KEY = os.getenv("SPEECHMATICS_API_KEY")
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.05  # seconds
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION * 2)  # 16-bit PCM = 2 bytes
SOURCE_LANG = "en"
TARGET_LANG = "ru"


def detect_pulse_monitor():
    """Находит monitor-источник, связанный с текущим активным sink'ом."""
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

        raise RuntimeError("Default sink not найден в pactl info")

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
        self.last_interim_len = 0
        self.partial_buffer = ""
        self.final_buffer = []  # список финальных сегментов для контекста
        self.max_context = 3  # уменьшил для скорости, но сохранил контекст

    def redraw(self, interim=None):
        # Очищаем экран
        sys.stdout.write("\033[2J\033[H")
        # Печатаем историю (последние N фраз)
        for segment in self.final_buffer[-self.max_context :]:
            print(segment)
        # Interim на последней строке
        if interim:
            print(interim, end="", flush=True)
        else:
            print("", end="", flush=True)

    async def process_audio_stream(self):
        self.session_active = True
        url = "wss://eu2.rt.speechmatics.com/v2"
        extra_headers = {"Authorization": f"Bearer {SPEECHMATICS_API_KEY}"}

        # Конфигурация с оптимизацией для минимальной задержки
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
                "max_delay": 1.0,  # можно уменьшить до 0.5 если нужно быстрее
            },
            "translation_config": {
                "target_languages": [TARGET_LANG],
                "enable_partials": True,  # важно для быстрого отображения
            },
        }

        try:
            async with connect(
                url, extra_headers=extra_headers, ping_interval=30
            ) as ws:
                sys.stdout.write("\033[2J\033[H")
                print("Speechmatics connection established")
                self.websocket = ws

                # 1. Отправляем StartRecognition
                await ws.send(json.dumps(start_msg))

                # 2. Ждём RecognitionStarted
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if data.get("message") == "RecognitionStarted":
                        break

                # 3. Запускаем приём результатов параллельно с отправкой аудио
                receive_task = asyncio.create_task(self.receive_results(ws))

                # 4. Отправляем аудиоданные (raw binary)
                try:
                    async for chunk in read_ffmpeg_audio():
                        if not self.session_active:
                            break
                        if isinstance(chunk, bytes) and len(chunk) > 0:
                            await ws.send(chunk)
                except Exception as e:
                    print(f"Audio sending error: {e}")

                # 5. Завершаем поток
                await ws.send(json.dumps({"message": "EndOfStream"}))

                # 6. Ждём завершения приёма результатов
                try:
                    await asyncio.wait_for(receive_task, timeout=5)
                except Exception:
                    receive_task.cancel()

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.session_active = False

    async def receive_results(self, ws):
        while self.session_active:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)

                if data.get("message") == "AddPartialTranslation":
                    # Быстро показываем частичный перевод
                    translation = data.get("results", [{}])[0].get("content", "")
                    if translation:
                        self.partial_buffer = translation
                        self.redraw(interim=self.partial_buffer)

                elif data.get("message") == "AddTranslation":
                    # Фиксируем финальный перевод с контекстом
                    translation = data.get("results", [{}])[0].get("content", "")
                    if translation:
                        self.final_buffer.append(translation)
                        if len(self.final_buffer) > self.max_context:
                            self.final_buffer.pop(0)
                        self.partial_buffer = ""
                        self.redraw()  # Обновляем без interim

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Result processing error: {e}")
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
