import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import yt_dlp
import os

TOKEN = "8252398181:AAGjvUgZAXqakp_0vC5IQnVBifungWIFXFc"

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("👋 Пришли ссылку на TikTok — скачаю БЕЗ водяного знака")

@dp.message()
async def download_tiktok(message: types.Message):
    url = message.text

    if "tiktok.com" not in url:
        await message.answer("❌ Это не ссылка на TikTok")
        return

    await message.answer("⏳ Скачиваю без водяного знака...")

    ydl_opts = {
        'outtmpl': 'video.mp4',
        'format': 'best',
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await message.answer_video(
            video=types.FSInputFile("video.mp4")
        )

        os.remove("video.mp4")

    except Exception as e:
        await message.answer("❌ Не удалось скачать видео")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
