import asyncio
import uuid
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import yt_dlp

TOKEN = "8252398181:AAGjvUgZAXqakp_0vC5IQnVBifungWIFXFc"

bot = Bot(token=TOKEN)
dp = Dispatcher()

DOWNLOAD_DIR = Path("downloads")

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


def _probe_content_type(url: str) -> str:
    opts = {**BASE_OPTS, 'skip_download': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get('_type') == 'playlist' or isinstance(info.get('images'), list):
        return 'photo'
    if info.get('ext') in ('jpg', 'jpeg', 'png', 'webp'):
        return 'photo'
    return 'video'


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


def _download_photos(url: str) -> list[Path]:
    file_id = uuid.uuid4().hex
    out_template = str(DOWNLOAD_DIR / f"{file_id}_%(autonumber)s.%(ext)s")
    opts = {
        **BASE_OPTS,
        'outtmpl': out_template,
        'format': 'bestvideo/best',
        'fragment_retries': 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    photos = []
    for ext in ('jpg', 'jpeg', 'png', 'webp'):
        photos.extend(sorted(DOWNLOAD_DIR.glob(f"{file_id}_*.{ext}")))
    return photos


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
        content_type = await asyncio.to_thread(_probe_content_type, url)

        if content_type == 'photo':
            await msg.edit_text("Скачиваю фото...")
            files = await asyncio.to_thread(_download_photos, url)

            if not files:
                await msg.edit_text("Не смог найти фото в этом посте.")
                return

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
