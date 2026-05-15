import asyncio
import uuid
import logging
import os
import httpx
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import yt_dlp

# Настройка логирования
logging.basicConfig(level=logging.INFO)

TOKEN = "8252398181:AAGjvUgZAXqakp_0vC5IQnVBifungWIFXFc"
DOWNLOAD_DIR = Path("downloads")
COOKIES_FILE = "cookies.txt"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

def get_yt_dlp_opts(out_path: str):
    opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out_path,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'socket_timeout': 15,
        'retries': 5,
        'extractor_args': {'tiktok': {'webpage_download': True}},
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    return opts

async def _resolve_short_url(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=HEADERS) as client:
        resp = await client.get(url)
        return str(resp.url)

def _download_video(url: str) -> Path:
    file_id = uuid.uuid4().hex
    out_path = DOWNLOAD_DIR / f"{file_id}.mp4"
    with yt_dlp.YoutubeDL(get_yt_dlp_opts(str(out_path))) as ydl:
        ydl.download([url])
    return out_path

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 <b>Привет!</b> Скинь ссылку на TikTok (видео или фото), и я пришлю его без водяного знака."
    )

@dp.message()
async def download_tiktok(message: types.Message):
    url = message.text.strip() if message.text else ""
    if "tiktok.com" not in url:
        return

    msg = await message.answer("🔍 Обрабатываю ссылку...")
    files: list[Path] = []

    try:
        # 1. Разворачиваем короткую ссылку (vt/vm)
        if any(x in url for x in ["vt.tiktok.com", "vm.tiktok.com"]):
            url = await _resolve_short_url(url)
        
        # 2. Очистка ссылки от лишних параметров (?_r=1...)
        # Это исправляет ошибку "Unsupported URL"
        url = url.split('?')[0]

        # 3. Получаем информацию о контенте
        ydl_opts = get_yt_dlp_opts("")
        ydl_opts['ignoreerrors'] = True 
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)

        if not info:
            raise Exception("Не удалось получить данные. Попробуйте обновить yt-dlp: pip install -U yt-dlp")

        # 4. Проверка на фото (слайд-шоу)
        photo_urls = []
        if 'entries' in info:
            photo_urls = [e['url'] for e in info['entries'] if e.get('url')]
        
        # Если это точно фото-пост, пробуем найти ссылки в форматах
        if not photo_urls and "/photo/" in url:
            if 'formats' in info:
                photo_urls = [f['url'] for f in info['formats'] if f.get('protocol') == 'https' or 'image' in f.get('format_note', '').lower()]

        if photo_urls:
            await msg.edit_text("📸 Обнаружено фото, скачиваю...")
            file_id = uuid.uuid4().hex
            async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
                for i, p_url in enumerate(photo_urls[:10]): # Лимит 10 фото
                    res = await client.get(p_url)
                    if res.status_code == 200:
                        p_path = DOWNLOAD_DIR / f"{file_id}_{i}.jpg"
                        p_path.write_bytes(res.content)
                        files.append(p_path)

            if files:
                media_group = [types.InputMediaPhoto(media=types.FSInputFile(f)) for f in files]
                await message.answer_media_group(media=media_group)
                await msg.delete()
                return 
            else:
                raise Exception("Не удалось скачать изображения")

        # 5. Если не фото — качаем как видео
        await msg.edit_text("⏳ Скачиваю видео...")
        video_path = await asyncio.to_thread(_download_video, url)
        files.append(video_path)
        await message.answer_video(video=types.FSInputFile(video_path))
        await msg.delete()

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        error_text = str(e)
        if "cookies" in error_text.lower():
            await msg.edit_text("⚠️ Ошибка: Нужны свежие cookies.txt")
        else:
            await msg.edit_text(f"❌ Ошибка: {error_text}")

    finally:
        # Удаление временных файлов
        for f in files:
            try:
                if f.exists(): f.unlink()
            except: pass

async def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
