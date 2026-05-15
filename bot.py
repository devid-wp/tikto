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

# Логирование
logging.basicConfig(level=logging.INFO)

TOKEN = "8252398181:AAGjvUgZAXqakp_0vC5IQnVBifungWIFXFc"
DOWNLOAD_DIR = Path("downloads")
COOKIES_FILE = "cookies.txt"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

def get_yt_dlp_opts(out_path: str):
    opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': out_path,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'socket_timeout': 20,
        'retries': 10,
        # Важно: подменяем User-Agent внутри самого yt-dlp
        'user_agent': HEADERS["User-Agent"],
        'extractor_args': {'tiktok': {'webpage_download': True}},
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
        logging.info("Использую cookies.txt")
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
    await message.answer("👋 Привет! Пришли ссылку на TikTok (фото или видео).")

@dp.message()
async def download_tiktok(message: types.Message):
    url_raw = message.text.strip() if message.text else ""
    if "tiktok.com" not in url_raw:
        return

    msg = await message.answer("🔍 Работаю над ссылкой...")
    files: list[Path] = []

    try:
        # 1. Разворачиваем и чистим URL
        url = await _resolve_short_url(url_raw)
        url = url.split('?')[0] # Убираем мусор
        
        # 2. Получаем инфо
        ydl_opts = get_yt_dlp_opts("")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Используем wait, чтобы не падать при первой ошибке
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)

        if not info:
            raise Exception("TikTok заблокировал запрос. Попробуй позже или обнови cookies.txt")

        # 3. Логика сбора ФОТО
        photo_urls = []
        
        # Проверяем все возможные места, где могут лежать картинки
        if 'entries' in info:
            photo_urls = [e['url'] for e in info['entries'] if e.get('url')]
        elif 'formats' in info:
            # Ищем протокол https и пометки о картинках
            photo_urls = [f['url'] for f in info['formats'] if f.get('url') and ('image' in str(f.get('format_note', '')).lower() or f.get('protocol') == 'https')]

        # 4. Если это фото-пост
        if photo_urls and ("/photo/" in url or info.get('api_reveal') == 'post_photo' or len(photo_urls) > 1):
            await msg.edit_text("📸 Качаю фото-слайды...")
            file_id = uuid.uuid4().hex
            
            async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
                for i, p_url in enumerate(photo_urls[:10]):
                    try:
                        res = await client.get(p_url)
                        if res.status_code == 200:
                            p_path = DOWNLOAD_DIR / f"{file_id}_{i}.jpg"
                            p_path.write_bytes(res.content)
                            files.append(p_path)
                    except:
                        continue

            if files:
                media_group = [types.InputMediaPhoto(media=types.FSInputFile(f)) for f in files]
                await message.answer_media_group(media=media_group)
                await msg.delete()
                return
            else:
                raise Exception("Не удалось загрузить изображения из найденных ссылок.")

        # 5. Если это видео
        await msg.edit_text("⏳ Качаю видео...")
        video_path = await asyncio.to_thread(_download_video, url)
        files.append(video_path)
        await message.answer_video(video=types.FSInputFile(video_path))
        await msg.delete()

    except Exception as e:
        logging.error(f"Error: {e}")
        await msg.edit_text(f"❌ Не удалось обработать.\nПричина: {str(e)[:100]}")

    finally:
        for f in files:
            try: f.unlink()
            except: pass

async def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
