import asyncio
import json
import os
import re
import subprocess
import sys
from collections import deque

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

# Параметры оптимизации
CONTEXT_WINDOW = 3  # Количество предыдущих фраз для контекста
MAX_CACHE_SIZE = 150  # Максимальный размер кэша переводов


def detect_pulse_monitor() -> str | None:
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
        self.final_buffer: deque[str] = deque(maxlen=CONTEXT_WINDOW)
        self.partial_buffer = ""
        self.last_interim_len = 0
        self.initialized = False
        self.translation_cache: dict[str, str] = {}

        # Персистентный HTTP клиент для DeepL
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=2.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

        # Счетчик для управления кэшем
        self.cache_counter = 0

    def normalize_text(self, text: str) -> str:
        """Нормализация текста для улучшения кэширования"""
        # Убираем лишние пробелы
        normalized = re.sub(r"\s+", " ", text.strip())
        # Убираем завершающую пунктуацию для совпадения interim/final
        normalized = re.sub(r"[.!?,;]+$", "", normalized)
        return normalized.lower()

    def redraw(self, text: str | None = None, is_final: bool = False):
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

    def print_interim(self, text: str):
        self.partial_buffer = text
        self.redraw(text=text, is_final=False)

    def print_final(self, text: str):
        if text and text not in self.final_buffer:
            self.final_buffer.append(text)
            self.redraw(text=text, is_final=True)
            self.partial_buffer = ""

    def get_context(self) -> str:
        """Получить контекст из предыдущих финальных фраз"""
        if len(self.final_buffer) == 0:
            return ""
        return " ".join(list(self.final_buffer))

    def manage_cache(self):
        """Управление размером кэша"""
        if len(self.translation_cache) > MAX_CACHE_SIZE:
            # Удаляем старые 50 записей
            for _ in range(50):
                if self.translation_cache:
                    self.translation_cache.pop(next(iter(self.translation_cache)))

    async def translate_text(self, text: str, is_final: bool = False) -> str:
        text = text.strip()
        if not text:
            return ""

        # Проверка кэша с нормализацией
        cache_key = self.normalize_text(text)
        if cache_key in self.translation_cache:
            return self.translation_cache[cache_key]

        url = "https://api-free.deepl.com/v2/translate"
        headers = {
            "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}",
            "User-Agent": "sub_realtime_translator/2.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # Базовые параметры перевода
        data = {
            "text": text,
            "target_lang": "RU",
            "source_lang": TRANSLATION_LANG,
            "split_sentences": "0",  # Не разбивать на предложения
            "preserve_formatting": "1",  # Сохранять форматирование
        }

        # Добавляем контекст для финальных результатов
        if is_final:
            context = self.get_context()
            if context:
                data["context"] = context

        try:
            response = await self.http_client.post(url, headers=headers, data=data)
            response.raise_for_status()
            result = response.json()
            translated = result["translations"][0]["text"]

            # Кэшируем результат
            self.translation_cache[cache_key] = translated

            # Управление размером кэша каждые 15 переводов
            self.cache_counter += 1
            if self.cache_counter % 15 == 0:
                self.manage_cache()

            return translated

        except httpx.TimeoutException:
            return text
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:  # Rate limit
                await asyncio.sleep(0.3)
            return text
        except Exception as e:
            print(f"[Translation error]: {e}")
            return text

    async def process_audio_stream(self):
        self.session_active = True
        receive_task: asyncio.Task | None = None

        try:
            # Правильные параметры Deepgram API
            async with websocket_connect(
                "wss://api.deepgram.com/v1/listen"
                "?encoding=linear16&sample_rate=16000&channels=1"
                f"&model=nova-2&language={TRANSLATION_LANG}"
                "&punctuate=true&interim_results=true"
                "&endpointing=300&smart_format=true",
                extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                ping_interval=10,
                ping_timeout=30,
            ) as ws:
                self.websocket = ws

                receive_task = asyncio.create_task(self.receive_results(ws))

                try:
                    async for chunk in read_ffmpeg_audio():
                        try:
                            await ws.send(chunk)
                        except Exception as e:
                            print(f"Send error: {e}")
                            break
                finally:
                    self.session_active = False
                    if receive_task and not receive_task.done():
                        receive_task.cancel()
                        try:
                            await receive_task
                        except asyncio.CancelledError:
                            pass

                    try:
                        await ws.send(json.dumps({"type": "CloseStream"}))
                    except Exception:
                        pass

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.session_active = False
            await self.http_client.aclose()

    async def receive_results(self, ws):
        while self.session_active:
            try:
                result = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(result)

                if "channel" in data:
                    transcript = data["channel"]["alternatives"][0]["transcript"]
                    if not transcript.strip():
                        continue

                    is_final = data.get("is_final", False)

                    # Переводим с контекстом для финальных результатов
                    translated = await self.translate_text(
                        transcript, is_final=is_final
                    )

                    if is_final:
                        self.print_final(translated)
                    else:
                        self.print_interim(translated)

            except asyncio.TimeoutError:
                print("Timeout waiting for Deepgram response")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Receive error: {e}")
                break

    def run(self):
        try:
            asyncio.run(self.process_audio_stream())
        except KeyboardInterrupt:
            self.session_active = False
            print("\nInterrupted")


if __name__ == "__main__":
    translator = RealTimeSubtitles()
    translator.run()
