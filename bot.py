import asyncio
import uuid
import re
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
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
    """Разворачивает vt.tiktok.com в полный URL."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
        resp = await client.head(url)
        return str(resp.url)


def _extract_video_id(url: str) -> str | None:
    match = re.search(r'/(?:video|photo)/(\d+)', url)
    return match.group(1) if match else None


async def _fetch_tiktok_api(video_id: str) -> dict:
    """Запрос к TikTok API для получения данных поста."""
    api_url = f"https://api22-normal-c-alisg.tiktokv.com/aweme/v1/feed/?aweme_id={video_id}&version_code=262036&app_name=musical_ly"
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
        resp = await client.get(api_url)
        resp.raise_for_status()
        return resp.json()


async def _download_photo_files(photo_urls: list[str]) -> list[Path]:
    file_id = uuid.uuid4().hex
    paths = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
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
        # Разворачиваем короткие ссылки (vt.tiktok.com)
        if "vt.tiktok.com" in url or "vm.tiktok.com" in url:
            url = await _resolve_short_url(url)

        video_id = _extract_video_id(url)
        is_photo = "/photo/" in url

        if is_photo and video_id:
            await msg.edit_text("Скачиваю фото...")

            data = await _fetch_tiktok_api(video_id)
            aweme = data.get("aweme_list", [{}])[0]

            # TikTok возвращает фото в image_post_info
            image_info = aweme.get("image_post_info", {})
            images = image_info.get("images", [])

            if not images:
                await msg.edit_text("Не смог найти фото в этом посте.")
                return

            photo_urls = [
                img["display_image"]["url_list"][0]
                for img in images
                if img.get("display_image", {}).get("url_list")
            ]

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
