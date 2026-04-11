import os
import asyncio
import logging
import traceback
import yt_dlp
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
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

load_dotenv()

# --- SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = "downloads"
BOT_USERNAME = "@GoYuklaBot"

# Cookies fayllari nomini GitHub'dagidek yozing
INSTAGRAM_COOKIES = "instagram_cookies.txt"
YOUTUBE_COOKIES = "youtube_cookies1.txt"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- RENDER HEALTH CHECK (Bot o'chib qolmasligi uchun) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live and running!")
    def log_message(self, format, *args): return

def run_health_check():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- UI MATNLARI ---
class UI:
    WELCOME = (
        "<b>👋 Assalomu alaykum, {}!</b>\n\n"
        "📥 Video: YouTube, Instagram, TikTok, Facebook\n"
        "🎵 Musiqa: Nomini yozing — 10 ta natija chiqadi\n\n"
        "✨ Link yuboring yoki musiqa nomini yozing:"
    )
    PROCESSING = "⏳ <b>Iltimos, kuting...</b>\n🔄 Yuklab olinmoqda..."
    UPLOADING = "📤 <b>Tayyor!</b>\n✨ Fayl yuborilmoqda..."
    CAPTION_VIDEO = "🎬 <b>{}</b>\n\n✨ {}"
    CAPTION_MUSIC = "🎵 <b>{}</b>\n\n✨ {}"
    ERROR = "❌ <b>Kechirasiz!</b>\n\nYuklashda xatolik yuz berdi. Iltimos, boshqa link yuborib ko'ring."
    NOT_FOUND = "🔍 <b>Hech narsa topilmadi.</b>"
    MUSIC_RESULTS = (
        "🔍 <b>\"{query}\"</b> bo‘yicha topilgan natijalar:\n\n"
        "{results_list}\n\n"
        "🎵 <b>1-10 gacha raqam yozing</b> — shu qo‘shiq yuklanadi!"
    )

# --- YT-DLP KONFIGURATSIYASI ---
def get_ydl_opts(file_base: str, is_audio: bool = False, cookies_file: str = None):
    opts = {
        'outtmpl': f'{file_base}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'retries': 15,
        'fragment_retries': 15,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'geo_bypass': True,
        'noplaylist': True,
        'socket_timeout': 60,
    }

    if cookies_file and os.path.exists(cookies_file):
        opts['cookiefile'] = cookies_file

    if is_audio:
        # Eng yaxshi audioni tanlash va MP3 ga o'girish
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # FORMAT XATOSI BO'LMASLIGI UCHUN:
        # Avval 720p mp4 qidiradi, bo'lmasa eng yaxshi mp4, bo'lmasa borini oladi.
        opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        opts['merge_output_format'] = 'mp4'

    return opts

# --- ASOSIY SINFG ---
class ProfessionalDownloader:
    def __init__(self):
        self.platforms = ["youtube.com", "youtu.be", "instagram.com", "tiktok.com",
                         "facebook.com", "fb.watch", "vt.tiktok.com"]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            UI.WELCOME.format(update.effective_user.first_name),
            parse_mode=ParseMode.HTML
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (update.message.text or "").strip()
        if not text: return
        user_id = update.effective_user.id

        # Musiqa tanlash rejimi
        if text.isdigit() and f"pending_music_{user_id}" in context.user_data:
            await self.process_selected_music(update, context, int(text))
            return

        # Link yoki Qidiruv
        if any(p in text.lower() for p in self.platforms) or text.startswith(("http://", "https://")):
            await self.process_download(update, context, text)
        else:
            await self.youtube_search(update, context, text)

    async def youtube_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
        status_msg = await update.message.reply_text(f"🔍 <b>\"{query}\"</b> qidirilmoqda...", parse_mode=ParseMode.HTML)
        try:
            user_id = update.effective_user.id
            ydl_opts = {'quiet': True, 'extract_flat': True, 'user_agent': 'Mozilla/5.0'}
            if os.path.exists(YOUTUBE_COOKIES): ydl_opts['cookiefile'] = YOUTUBE_COOKIES

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"ytsearch10:{query}", download=False)
                )

            if not info or 'entries' not in info or not info['entries']:
                await status_msg.edit_text(UI.NOT_FOUND, parse_mode=ParseMode.HTML)
                return

            entries = [e for e in info['entries'] if e]
            results_list = []
            for i, entry in enumerate(entries[:10], 1):
                title = entry.get('title', 'Noma’lum')
                results_list.append(f"<b>{i}.</b> {title}")

            await status_msg.edit_text(UI.MUSIC_RESULTS.format(query=query, results_list="\n\n".join(results_list)), parse_mode=ParseMode.HTML)
            context.user_data[f"pending_music_{user_id}"] = {'entries': entries}
        except Exception as e:
            logger.error(f"Search error: {e}")
            await status_msg.edit_text(UI.ERROR, parse_mode=ParseMode.HTML)

    async def process_selected_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE, num: int):
        user_id = update.effective_user.id
        data = context.user_data.get(f"pending_music_{user_id}")
        if not data or num < 1 or num > len(data['entries']): return

        selected = data['entries'][num - 1]
        url = selected.get('url') or selected.get('webpage_url')
        status_msg = await update.message.reply_text(UI.PROCESSING, parse_mode=ParseMode.HTML)
        file_id = str(uuid.uuid4())
        file_base = os.path.join(DOWNLOAD_DIR, file_id)

        try:
            ydl_opts = get_ydl_opts(file_base, is_audio=True, cookies_file=YOUTUBE_COOKIES)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: ydl.extract_info(url, download=True)
                )
            
            file_path = self.find_file(file_id)
            if file_path:
                await status_msg.edit_text(UI.UPLOADING, parse_mode=ParseMode.HTML)
                with open(file_path, 'rb') as f:
                    await context.bot.send_audio(
                        chat_id=update.effective_chat.id,
                        audio=f,
                        title=info.get('title', 'Musiqa'),
                        performer=info.get('uploader', 'Artist'),
                        caption=f"🎵 <b>{info.get('title')}</b>\n\n{BOT_USERNAME}",
                        parse_mode=ParseMode.HTML
                    )
                await status_msg.delete()
            else: raise Exception("File not found")
        except Exception as e:
            logger.error(f"Music Error: {e}")
            await status_msg.edit_text(UI.ERROR, parse_mode=ParseMode.HTML)
        finally:
            self.cleanup(file_id)
            context.user_data.pop(f"pending_music_{user_id}", None)

    async def process_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        status_msg = await update.message.reply_text(UI.PROCESSING, parse_mode=ParseMode.HTML)
        file_id = str(uuid.uuid4())
        file_base = os.path.join(DOWNLOAD_DIR, file_id)
        
        cookie = INSTAGRAM_COOKIES if "instagram.com" in url.lower() else YOUTUBE_COOKIES

        try:
            ydl_opts = get_ydl_opts(file_base, is_audio=False, cookies_file=cookie)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: ydl.extract_info(url, download=True)
                )

            file_path = self.find_file(file_id)
            if file_path:
                await status_msg.edit_text(UI.UPLOADING, parse_mode=ParseMode.HTML)
                with open(file_path, 'rb') as f:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=f,
                        caption=f"🎬 <b>{info.get('title', 'Video')[:50]}</b>\n\n{BOT_USERNAME}",
                        parse_mode=ParseMode.HTML,
                        supports_streaming=True
                    )
                await status_msg.delete()
            else: raise Exception("File not found")
        except Exception as e:
            logger.error(f"Download Error: {e}")
            await status_msg.edit_text(UI.ERROR, parse_mode=ParseMode.HTML)
        finally:
            self.cleanup(file_id)

    def find_file(self, file_id: str):
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id): return os.path.join(DOWNLOAD_DIR, f)
        return None

    def cleanup(self, file_id: str):
        try:
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(file_id): os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass

# --- ISHGA TUSHIRISH ---
if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN topilmadi!")
        exit(1)

    # Render portini band qilish (Botni o'chib qolishdan asraydi)
    threading.Thread(target=run_health_check, daemon=True).start()

    bot_app = ProfessionalDownloader()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", bot_app.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.handle_message))

    print("🚀 Bot Render serverida ishga tushdi!")
    app.run_polling()
