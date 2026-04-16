import asyncio
import uuid
import re
import json
import httpx
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import yt_dlp

TOKEN = "8252398181:AAGjvUgZAXqakp_0vC5IQnVBifungWIFXFc"

bot = Bot(token=TOKEN)
dp = Dispatcher()

DOWNLOAD_DIR = Path("downloads")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tiktok.com/",
}

TIKTOK_ARGS = {
    'tiktok': {
        'webpage_download': True,
        'app_name': 'musical_ly',
        'app_version': '34.1.2',
    }
}

BASE_OPTS = {
    'extractor_args': TIKTOK_ARGS,
    'socket_timeout': 10,
    'retries': 3,
    'quiet': True,
    'no_warnings': True,
}


async def _resolve_short_url(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=10, headers=HEADERS) as client:
        resp = await client.head(url)
        return str(resp.url)


def _extract_video_id(url: str) -> str | None:
    match = re.search(r'/(?:video|photo)/(\d+)', url)
    return match.group(1) if match else None


async def _scrape_photo_urls(url: str) -> list[str]:
    """Парсим HTML страницы TikTok и вытаскиваем фото из __UNIVERSAL_DATA_FOR_REHYDRATION__."""
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
        resp = await client.get(url)
        html = resp.text

    # TikTok прячет данные в JSON внутри тега <script>
    match = re.search(r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    # Ищем imagePost внутри вложенного JSON
    raw = json.dumps(data)
    images_match = re.findall(r'"imageURL"\s*:\s*\{[^}]*"urlList"\s*:\s*\[([^\]]+)\]', raw)

    urls = []
    for block in images_match:
        found = re.findall(r'"(https://[^"]+)"', block)
        if found:
            # Берём первый URL (лучшее качество)
            urls.append(found[0])

    return urls


async def _download_photo_files(photo_urls: list[str]) -> list[Path]:
    file_id = uuid.uuid4().hex
    paths = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for i, url in enumerate(photo_urls):
            resp = await client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get('content-type', '')
            ext = 'webp' if 'webp' in ct else 'png' if 'png' in ct else 'jpg'
            path = DOWNLOAD_DIR / f"{file_id}_{i}.{ext}"
            path.write_bytes(resp.content)
            paths.append(path)
    return paths


def _download_video(url: str) -> Path:
    file_id = uuid.uuid4().hex
    out_path = DOWNLOAD_DIR / f"{file_id}.mp4"
    opts = {
        **BASE_OPTS,
        'outtmpl': str(out_path),
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'concurrent_fragment_downloads': 8,
        'buffersize': 1024 * 16,
        'http_chunk_size': 1024 * 1024 * 10,
        'fragment_retries': 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return out_path


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "Привет! Скинь ссылку на TikTok и я скачаю без водяного знака.\n"
        "Работает и с видео, и со слайдшоу."
    )


@dp.message()
async def download_tiktok(message: types.Message):
    url = message.text.strip()

    if "tiktok.com" not in url:
        await message.answer("Это не ссылка на TikTok.")
        return

    msg = await message.answer("Смотрю что там...")
    files: list[Path] = []

    try:
        if "vt.tiktok.com" in url or "vm.tiktok.com" in url:
            url = await _resolve_short_url(url)

        is_photo = "/photo/" in url

        if is_photo:
            await msg.edit_text("Скачиваю фото...")

            photo_urls = await _scrape_photo_urls(url)

            if not photo_urls:
                await msg.edit_text("Не смог найти фото — попробуй отправить полную ссылку из браузера.")
                return

            files = await _download_photo_files(photo_urls)

            if len(files) == 1:
                await message.answer_photo(photo=types.FSInputFile(files[0]))
            else:
                media_group = [
                    types.InputMediaPhoto(media=types.FSInputFile(f))
                    for f in files
                ]
                await message.answer_media_group(media=media_group)
        else:
            await msg.edit_text("Скачиваю видео...")
            video_path = await asyncio.to_thread(_download_video, url)
            files = [video_path]
            await message.answer_video(video=types.FSInputFile(video_path))

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"Что-то пошло не так: {e}")

    finally:
        for f in files:
            if f.exists():
                f.unlink()


async def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
