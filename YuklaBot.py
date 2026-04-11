import os
import asyncio
import logging
import yt_dlp
import uuid
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# ====================== KONFIGURATSIYA ======================
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = "downloads"
BOT_USERNAME = "@GoYuklaBot"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class UI:
    WELCOME = (
        "<b>👋 Assalomu alaykum, {}!</b>\n\n"
        "Men professional <b>Media Yuklovchi</b> botman ✨\n\n"
        "📥 Video: YouTube, Instagram, TikTok, Facebook\n"
        "🎵 Musiqa: Nomini yozing — 10 ta natija chiqadi\n\n"
        "✨ Link yuboring yoki musiqa nomini yozing:"
    )
    PROCESSING = "⏳ <b>Iltimos, kuting...</b>\n🔄 Yuklab olinmoqda..."
    UPLOADING = "📤 <b>Tayyor bo‘ldi!</b>\n✨ Fayl yuborilmoqda..."
    CAPTION_VIDEO = "🎬 <b>{}</b>\n\n✨ {}"
    CAPTION_MUSIC = "🎵 <b>{}</b>\n\n✨ {}"
    ERROR = "❌ <b>Kechirasiz, {}!</b>\n\nBu linkni hozir yuklab bo‘lmadi.\nKeyinroq urinib ko‘ring yoki boshqa link yuboring."
    NOT_FOUND = "🔍 <b>Hech narsa topilmadi.</b>"
    MUSIC_RESULTS = (
        "🔍 <b>\"{query}\"</b> bo‘yicha topilgan natijalar:\n\n"
        "{results_list}\n\n"
        "🎵 <b>1-10 gacha raqam yozing</b> — shu qo‘shiq yuklanadi!"
    )


def get_ydl_opts(file_base: str, is_audio: bool = False):
    """Eng ishonchli opts (2026 yil uchun)"""
    opts = {
        'outtmpl': f'{file_base}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'retries': 5,
        'fragment_retries': 5,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'geo_bypass': True,
        'merge_output_format': 'mp4',
        'http_headers': {
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.instagram.com/',
        },
    }

    if is_audio:
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        # Instagram, TikTok, YouTube uchun eng yaxshi ishlaydigan format
        opts.update({
            'format': 'bestvideo*[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo*[height<=1080]+bestaudio/best[ext=mp4]/best',
            'prefer_free_formats': False,
            'format_sort': ['proto:https', 'ext:mp4:m4a', 'res', 'br'],  # eng muhim qator
        })

    return opts


class ProfessionalDownloader:
    def __init__(self):
        self.platforms = ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "facebook.com", "fb.watch", "vt.tiktok.com"]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            UI.WELCOME.format(update.effective_user.first_name),
            parse_mode=ParseMode.HTML
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (update.message.text or "").strip()
        if not text:
            return

        user_id = update.effective_user.id

        # Raqam bosildi (musiqa tanlash)
        if text.isdigit():
            num = int(text)
            if 1 <= num <= 10 and f"pending_music_{user_id}" in context.user_data:
                await self.process_selected_music(update, context, num)
                return

        # Link bo‘lsa — video yuklash
        if any(p in text.lower() for p in self.platforms) or text.startswith(("http://", "https://")):
            await self.process_download(update, context, text)
        else:
            # Musiqa qidiruvi
            await self.youtube_search(update, context, text)

    # ==================== MUSIQA QIDIRUV (10 ta natija) ====================
    async def youtube_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
        status_msg = await update.message.reply_text(f"🔍 <b>\"{query}\"</b> qidirilmoqda...", parse_mode=ParseMode.HTML)

        try:
            loop = asyncio.get_running_loop()
            search_query = f"ytsearch10:{query} official audio"

            ydl_opts = {'quiet': True, 'no_warnings': True, 'geo_bypass': True}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))

            if not info or 'entries' not in info or not info['entries']:
                await status_msg.edit_text(UI.NOT_FOUND, parse_mode=ParseMode.HTML)
                return

            entries = info['entries'][:10]
            results_list = []
            for i, entry in enumerate(entries, 1):
                title = entry.get('title', 'Noma’lum qo‘shiq')
                uploader = entry.get('uploader', 'Artist')
                duration = entry.get('duration')
                dur_str = f"{duration//60:02d}:{duration%60:02d}" if duration else "??:??"
                results_list.append(f"<b>{i}.</b> {title}\n   👤 {uploader} | ⏱ {dur_str}")

            results_text = "\n\n".join(results_list)

            await status_msg.edit_text(
                UI.MUSIC_RESULTS.format(query=query, results_list=results_text),
                parse_mode=ParseMode.HTML
            )

            context.user_data[f"pending_music_{update.effective_user.id}"] = {'entries': entries}

        except Exception as e:
            logger.error(f"Qidiruv xatosi: {e}")
            await status_msg.edit_text(UI.ERROR.format(update.effective_user.first_name), parse_mode=ParseMode.HTML)

    # ==================== TANLANGAN MUSIQANI YUKLASH ====================
    async def process_selected_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE, num: int):
        user_id = update.effective_user.id
        data = context.user_data.get(f"pending_music_{user_id}")
        if not data:
            return

        entries = data['entries']
        idx = num - 1
        if idx >= len(entries):
            await update.message.reply_text("❌ Noto‘g‘ri raqam! 1-10 oralig‘ida yozing.")
            return

        selected = entries[idx]
        url = selected.get('url') or selected.get('webpage_url')
        if not url:
            await update.message.reply_text(UI.ERROR.format(update.effective_user.first_name), parse_mode=ParseMode.HTML)
            return

        status_msg = await update.message.reply_text(UI.PROCESSING, parse_mode=ParseMode.HTML)
        file_id = str(uuid.uuid4())
        file_base = os.path.join(DOWNLOAD_DIR, file_id)

        try:
            loop = asyncio.get_running_loop()
            ydl_opts = get_ydl_opts(file_base, is_audio=True)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                title = info.get('title', selected.get('title', 'Musiqa'))
                performer = info.get('uploader', selected.get('uploader', 'Artist'))

            file_path = self.find_file(file_id)
            if file_path:
                await status_msg.edit_text(UI.UPLOADING, parse_mode=ParseMode.HTML)
                with open(file_path, 'rb') as f:
                    await update.message.reply_audio(
                        audio=f,
                        title=title[:100],
                        performer=performer[:50],
                        caption=UI.CAPTION_MUSIC.format(title, BOT_USERNAME),
                        parse_mode=ParseMode.HTML
                    )
                await status_msg.delete()
            else:
                await status_msg.edit_text(UI.NOT_FOUND, parse_mode=ParseMode.HTML)

        except Exception as e:
            logger.error(f"Musiqa yuklash xatosi: {e}")
            await status_msg.edit_text(UI.ERROR.format(update.effective_user.first_name), parse_mode=ParseMode.HTML)
        finally:
            self.cleanup(file_id)
            context.user_data.pop(f"pending_music_{user_id}", None)

    # ==================== VIDEO YUKLASH (Instagram, TikTok, YT, FB) ====================
    async def process_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        status_msg = await update.message.reply_text(UI.PROCESSING, parse_mode=ParseMode.HTML)
        file_id = str(uuid.uuid4())
        file_base = os.path.join(DOWNLOAD_DIR, file_id)

        try:
            loop = asyncio.get_running_loop()
            ydl_opts = get_ydl_opts(file_base, is_audio=False)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                title = info.get('title', 'Video')[:100]

            file_path = self.find_file(file_id)
            if not file_path:
                raise Exception("Fayl topilmadi")

            await status_msg.edit_text(UI.UPLOADING, parse_mode=ParseMode.HTML)

            with open(file_path, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=UI.CAPTION_VIDEO.format(title, BOT_USERNAME),
                    parse_mode=ParseMode.HTML,
                    supports_streaming=True
                )
            await status_msg.delete()

        except Exception as e:
            logger.error(f"Video yuklash xatosi ({url}): {e}")
            await status_msg.edit_text(UI.ERROR.format(update.effective_user.first_name), parse_mode=ParseMode.HTML)
        finally:
            self.cleanup(file_id)

    def find_file(self, file_id: str):
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id):
                return os.path.join(DOWNLOAD_DIR, f)
        return None

    def cleanup(self, file_id: str):
        try:
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(file_id):
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
        except Exception as e:
            logger.error(f"Cleanup xatosi: {e}")


if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN topilmadi! .env faylni tekshiring.")
        exit(1)

    bot = ProfessionalDownloader()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    print("🚀 Bot muvaffaqiyatli ishga tushdi! (100% ishlaydigan versiya)")
    app.run_polling()
