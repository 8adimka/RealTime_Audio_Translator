# 🎧 RealTime Audio Translator (Deepgram + DeepL)

## Содержание

1. [Описание проекта](#1-описание-проекта)
2. [Используемые технологии](#2-используемые-технологии)
3. [Работа с проектом](#3-работа-с-проектом)
   - [3.1 Настройка виртуального окружения](#31-настройка-виртуального-окружения)
   - [3.2 Файл ](#32-файл-env)[`.env`](#32-файл-env)
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
  1) RealTime_Transcriber ->
  *Проводит транскрибацию английского аудио в английский текст и выводит результат.
   * rt_1.py

  2) RealTime_Translator ->
  *RealTime переводчик выводит перевод английской речи.
   * rt_4_cached.py	->  Оптимальная комбинация: скорость, экономия, UX, читаемость, точность 🥇
   * rt_4.py	->  Структурирован, но перегружает API из-за отсутствия кэша 🥈
   * rt_2.py	->  Устаревшая логика, дубли, плохой контроль вывода и много API-запросов, зато более простая и читаемая логика 🥉

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
   poetry run python rt_2.py
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

