import asyncio



import uuid


import re


import json


import httpx


import logging


import os


from pathlib import Path


from aiogram import Bot, Dispatcher, types


from aiogram.filters import CommandStart


from aiogram.client.default import DefaultBotProperties


from aiogram.enums import ParseMode


import yt_dlp





# Настройка логирования (чтобы видеть ошибки в консоли Termux)


logging.basicConfig(level=logging.INFO)





TOKEN = "8252398181:AAGjvUgZAXqakp_0vC5IQnVBifungWIFXFc"


DOWNLOAD_DIR = Path("downloads")


COOKIES_FILE = "cookies.txt"  # Файл с куками должен быть в папке с ботом





bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


dp = Dispatcher()





# Улучшенные заголовки


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


        # Настройки для обхода блокировок:


        'extractor_args': {'tiktok': {'webpage_download': True}},


    }


    # Если файл с куками существует, используем его


    if os.path.exists(COOKIES_FILE):


        opts['cookiefile'] = COOKIES_FILE


        logging.info("Использую cookies.txt для авторизации")


    return opts





async def _resolve_short_url(url: str) -> str:


    async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=HEADERS) as client:


        resp = await client.get(url) # Head иногда не срабатывает в TikTok


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


        # 1. Разворачиваем короткую ссылку


        if "vt.tiktok.com" in url or "vm.tiktok.com" in url:


            url = await _resolve_short_url(url)





        # 2. Определяем тип контента


        if "/photo/" in url:


            await msg.edit_text("📸 Обнаружены фото, скачиваю...")


            # Используем yt-dlp для фото тоже (он умеет вытягивать ссылки)


            with yt_dlp.YoutubeDL(get_yt_dlp_opts("")) as ydl:


                info = ydl.extract_info(url, download=False)


                photo_urls = [e['url'] for e in info.get('entries', []) if 'url' in e]


                if not photo_urls and 'url' in info: photo_urls = [info['url']]





            if not photo_urls:


                raise Exception("Не удалось найти фото")





            # Скачивание фото


            file_id = uuid.uuid4().hex


            async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:


                for i, p_url in enumerate(photo_urls[:10]): # Лимит 10 фото для медиагруппы


                    res = await client.get(p_url)


                    p_path = DOWNLOAD_DIR / f"{file_id}_{i}.jpg"


                    p_path.write_bytes(res.content)


                    files.append(p_path)





            media_group = [types.InputMediaPhoto(media=types.FSInputFile(f)) for f in files]


            await message.answer_media_group(media=media_group)


            


        else:


            await msg.edit_text("⏳ Скачиваю видео, подожди...")


            video_path = await asyncio.to_thread(_download_video, url)


            files.append(video_path)


            await message.answer_video(video=types.FSInputFile(video_path))





        await msg.delete()





    except Exception as e:


        error_msg = str(e)


        if "cookies" in error_msg.lower():


            await msg.edit_text("⚠️ Это видео требует авторизации. Нужно обновить cookies.txt на сервере.")


        else:


            logging.error(f"Ошибка: {e}")


            await msg.edit_text(f"❌ Ошибка: {e}")





    finally:


        # Очистка файлов


        for f in files:


            try:


                if f.exists(): f.unlink()


            except Exception: pass





async def main():


    DOWNLOAD_DIR.mkdir(exist_ok=True)


    # Удаляем вебхук перед запуском (важно для Termux)


    await bot.delete_webhook(drop_pending_updates=True)


    await dp.start_polling(bot)





if __name__ == "__main__":


    try:


        asyncio.run(main())


    except (KeyboardInterrupt, SystemExit):


        logging.info("Бот остановлен")
