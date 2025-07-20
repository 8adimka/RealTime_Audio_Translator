# 🇬🇧 English version

## 🎧 RealTime Audio Translator (Deepgram + DeepL)

## Table of Contents

1. [Project Description](#1-project-description)
2. [Technologies Used](#2-technologies-used)
3. [Working with the Project](#3-working-with-the-project)
   - [3.1 Setting Up Virtual Environment](#31-setting-up-virtual-environment)
   - [3.2 `.env` File](#32-env-file)
   - [3.3 Running the Project](#33-running-the-project)
4. [Startup Steps](#4-startup-steps)
5. [Useful Resources](#5-useful-resources)

---

## 1. Project Description

This project is designed for:

1. Capturing system audio
2. Transcribing English speech to text
3. Translating it into Russian (optional)

using Deepgram API (speech-to-text) and DeepL API (translation).

The result is displayed in the terminal in real time. Latency is kept to a minimum.

Currently, the project includes the following versions:

1. **RealTime_Transcriber**
    - *Performs transcription of English audio into English text and displays it.*
        - `rt_1.py`

2. **RealTime_Translator**
    - *Real-time translator outputs Russian translation of English speech.*
        - `rt_4_cached.py` — Optimal combination: speed, cost-efficiency, UX, readability, accuracy 🥇
        - `rt_2.py` — Outdated logic, duplicates, poor output control, many API requests, but simpler and easier to follow 🥈
        - `rt_SPEECHMATICS_1.py` — Alternative version using the SPEECHMATICS API 🥉

---

## 2. Technologies Used

- Python 3.11+
- [Poetry](https://python-poetry.org/) for dependency management
- [Deepgram API](https://www.deepgram.com/)
- [DeepL API](https://www.deepl.com/)
- ffmpeg (PulseAudio audio capture)

---

## 3. Working with the Project

### 3.1 Setting Up Virtual Environment

```bash
poetry install
```

Or, if the project is not yet initialized:

```bash
poetry init  # or poetry new project_name
poetry add python-dotenv httpx websockets
```

### 3.2 `.env` File

Create a `.env` file in the root of the project:

```dotenv
DEEPGRAM_API_KEY=your_deepgram_api_key_here
DEEPL_API_KEY=your_deepl_api_key_here
```

### 3.3 Running the Project

To transcribe English speech into text:

```bash
poetry run python rt_1.py
```

Or to translate into Russian:

```bash
poetry run python rt_4_cached.py
```

---

## 4. Startup Steps

1. Make sure PulseAudio/system audio is enabled
2. Ensure `ffmpeg` is installed:

   ```bash
   sudo pacman -S ffmpeg  # for Arch
   sudo apt install ffmpeg  # for Debian/Ubuntu
   ```

3. Edit the `.env` file
4. Run the command from the project folder:

   ```bash
   poetry run python rt_4_cached.py
   ```

---

## 5. Useful Resources

- [Official Poetry Documentation](https://python-poetry.org/docs/)
- [Deepgram Developer Docs](https://developers.deepgram.com/)
- [DeepL API Docs](https://www.deepl.com/docs-api)
- [pactl — PulseAudio CLI](https://www.freedesktop.org/wiki/Software/PulseAudio/Documentation/User/CLI/)
- [Using ffmpeg with PulseAudio](https://trac.ffmpeg.org/wiki/Capture/PulseAudio)

---

> The project works on Linux (tested on Arch Linux + PipeWire + KDE Plasma). For Windows and macOS, a different audio configuration will be required.

---
---

# 🇷🇺 На русском

## 🎧 RealTime Audio Translator (Deepgram + DeepL)

## Содержание

1. [Описание проекта](#1-описание-проекта)
2. [Используемые технологии](#2-используемые-технологии)
3. [Работа с проектом](#3-работа-с-проектом)
   - [3.1 Настройка виртуального окружения](#31-настройка-виртуального-окружения)
   - [3.2 Файл](#32-файл-env)[`.env`](#32-файл-env)
   - [3.3 Запуск проекта](#33-запуск-проекта)
4. [Этапы запуска](#4-этапы-запуска)
5. [Полезные материалы](#5-полезные-материалы)

---

## 1. Описание проекта

Данный проект предназначен для:

1) перехвата системного звука
2) разпознования английской речи в текст (транскрипции)
3) перевода на русский язык (текст) (опционально)

с помощью API Deepgram (речь в текст) и DeepL (перевод).

Результат выводится в терминал в режиме реального времени. Задержки сведены к минимому.

Сейчас проект включает следующие версии:

1. **RealTime_Transcriber**
    - *Проводит транскрибацию английского аудио в английский текст и выводит результат.*
        - `rt_1.py`

2. **RealTime_Translator**
    - *RealTime переводчик выводит перевод английской речи.*
        - `rt_4_cached.py` — Оптимальная комбинация: скорость, экономия, UX, читаемость, точность 🥇
        - `rt_2.py` — Устаревшая логика, дубли, плохой контроль вывода и много API-запросов, зато более простая и читаемая логика 🥈
        - `rt_SPEECHMATICS_1.py` — Альтернативная версия на API от SPEECHMATICS 🥉

---

## 2. Используемые технологии

- Python 3.11+
- [Poetry](https://python-poetry.org/) для управления зависимостями
- [Deepgram API](https://www.deepgram.com/)
- [DeepL API](https://www.deepl.com/)
- ffmpeg (PulseAudio захват звука)

---

## 3. Работа с проектом

### 3.1 Настройка виртуального окружения

```bash
poetry install
```

Или, если проект не был ещё инициализирован:

```bash
poetry init  # или poetry new project_name
poetry add python-dotenv httpx websockets
```

### 3.2 Файл `.env`

Создайте файл `.env` в корне проекта:

```dotenv
DEEPGRAM_API_KEY=your_deepgram_api_key_here
DEEPL_API_KEY=your_deepl_api_key_here
```

### 3.3 Запуск проекта

для транскрипции английской речи в текст

```bash
poetry run python rt_1.py
```

или для перевода на русский язык

```bash
poetry run python rt_4_cached.py
```

---

## 4. Этапы запуска

1. Убедитесь, что PulseAudio/Системный звук включен
2. Убедитесь, что ffmpeg установлен:

   ```bash
   sudo pacman -S ffmpeg  # для Arch
   sudo apt install ffmpeg  # для Debian/Ubuntu
   ```

3. Отредактируйте `.env`
4. Запустите команду из папки проекта:

   ```bash
   poetry run python rt_4_cached.py
   ```

---

## 5. Полезные материалы

- [Официальная документация Poetry](https://python-poetry.org/docs/)
- [Deepgram Developer Docs](https://developers.deepgram.com/)
- [DeepL API Docs](https://www.deepl.com/docs-api)
- [pactl — работа с PulseAudio](https://www.freedesktop.org/wiki/Software/PulseAudio/Documentation/User/CLI/)
- [Работа с ffmpeg и PulseAudio](https://trac.ffmpeg.org/wiki/Capture/PulseAudio)

---

> Проект работает в Linux (проверено на Arch Linux + PipeWire + KDE Plasma). На Windows и macOS потребуется другая конфигурация аудиопотока.
