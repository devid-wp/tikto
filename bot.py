import asyncio
import os
import uuid
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import yt_dlp

TOKEN = "8252398181:AAGjvUgZAXqakp_0vC5IQnVBifungWIFXFc"

bot = Bot(token=TOKEN)
dp = Dispatcher()

DOWNLOAD_DIR = Path("downloads")

def _download_sync(url: str) -> Path:
    """Синхронная загрузка в отдельном потоке."""
    file_id = uuid.uuid4().hex
    out_path = DOWNLOAD_DIR / f"{file_id}.mp4"

    ydl_opts = {
        'outtmpl': str(out_path),
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        # === БЕЗ ВОДЯНОГО ЗНАКА ===
        'extractor_args': {
            'tiktok': {
                'webpage_download': True,
                'app_name': 'musical_ly',
                'app_version': '34.1.2',
            }
        },
        # === СКОРОСТЬ ===
        'concurrent_fragment_downloads': 8,
        'buffersize': 1024 * 16,
        'http_chunk_size': 1024 * 1024 * 10,
        'socket_timeout': 10,
        'retries': 3,
        'fragment_retries': 3,
        # === ТИХИЙ РЕЖИМ ===
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return out_path


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(" Пришли ссылку на TikTok — скачаю БЕЗ водяного знака")


@dp.message()
async def download_tiktok(message: types.Message):
    url = message.text.strip()

    if "tiktok.com" not in url:
        await message.answer(" Это не ссылка на TikTok")
        return

    msg = await message.answer(" Скачиваю без водяного знака...")
    file_path: Path | None = None

    try:
        # Не блокируем event loop
        file_path = await asyncio.to_thread(_download_sync, url)

        await message.answer_video(
            video=types.FSInputFile(file_path),
            caption="Готово — без водяного знака!"
        )
        await msg.delete()

    except Exception as e:
        await msg.edit_text(f" Не удалось скачать видео: {e}")

    finally:
        # Удаляем файл в любом случае
        if file_path and file_path.exists():
            file_path.unlink()


async def main():
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
