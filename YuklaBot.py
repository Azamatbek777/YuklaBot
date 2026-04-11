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

# Fayl nomlarini tekshiring: GitHub-da qanday bo'lsa shunday yozing
INSTAGRAM_COOKIES = "instagram_cookies.txt"
YOUTUBE_COOKIES = "youtube_cookies1.txt" # Sizda 1 bilan ekan, shunday qoldirdim

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- RENDER PORT XATOSINI OLISHI UCHUN (HEALTH CHECK) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live!")
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
    ERROR = "❌ <b>Kechirasiz!</b>\n\nKeyinroq urinib ko‘ring yoki boshqa link/nom sinang."
    NOT_FOUND = "🔍 <b>Hech narsa topilmadi.</b>"
    MUSIC_RESULTS = (
        "🔍 <b>\"{query}\"</b> bo‘yicha topilgan natijalar:\n\n"
        "{results_list}\n\n"
        "🎵 <b>1-10 gacha raqam yozing</b> — shu qo‘shiq yuklanadi!"
    )

# --- YT-DLP SOZLAMALARI ---
def get_ydl_opts(file_base: str, is_audio: bool = False, cookies_file: str = None):
    opts = {
        'outtmpl': f'{file_base}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'retries': 15,
        'fragment_retries': 15,
        # Haqiqiy User-Agent (YouTube bloklamasligi uchun)
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'geo_bypass': True,
        'noplaylist': True,
        'socket_timeout': 60,
    }

    # DIQQAT: 'cookies' emas, 'cookiefile' bo'lishi shart!
    if cookies_file and os.path.exists(cookies_file):
        opts['cookiefile'] = cookies_file

    if is_audio:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        opts['merge_output_format'] = 'mp4'

    return opts

# --- ASOSIY LOGIKA ---
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

        if text.isdigit() and f"pending_music_{user_id}" in context.user_data:
            await self.process_selected_music(update, context, int(text))
            return

        if any(p in text.lower() for p in self.platforms) or text.startswith(("http://", "https://")):
            await self.process_download(update, context, text)
        else:
            await self.youtube_search(update, context, text)

    async def youtube_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
        status_msg = await update.message.reply_text(f"🔍 <b>\"{query}\"</b> qidirilmoqda...", parse_mode=ParseMode.HTML)
        try:
            user_id = update.effective_user.id
            ydl_opts = {'quiet': True, 'extract_flat': True, 'user_agent': 'Mozilla/5.0'}
            if os.path.exists(YOUTUBE_COOKIES):
                ydl_opts['cookiefile'] = YOUTUBE_COOKIES

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"ytsearch10:{query}", download=False)
                )

            if not info or 'entries' not in info or not info['entries']:
                await status_msg.edit_text(UI.NOT_FOUND, parse_mode=ParseMode.HTML)
                return

            entries = info['entries'][:10]
            results_list = []
            for i, entry in enumerate(entries, 1):
                title = entry.get('title', 'Noma’lum')
                uploader = entry.get('uploader', 'Artist')
                results_list.append(f"<b>{i}.</b> {title}\n👤 {uploader}")

            await status_msg.edit_text(
                UI.MUSIC_RESULTS.format(query=query, results_list="\n\n".join(results_list)),
                parse_mode=ParseMode.HTML
            )
            context.user_data[f"pending_music_{user_id}"] = {'entries': entries}
        except Exception as e:
            logger.error(f"Search error: {e}")
            await status_msg.edit_text(UI.ERROR, parse_mode=ParseMode.HTML)

    async def process_selected_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE, num: int):
        user_id = update.effective_user.id
        data = context.user_data.get(f"pending_music_{user_id}")
        if not data: return
        entries = data['entries']
        if num < 1 or num > len(entries): return

        selected = entries[num - 1]
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
                        title=info.get('title', 'Music'),
                        performer=info.get('uploader', 'Artist'),
                        caption=f"{BOT_USERNAME}",
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
                        caption=f"🎬 {info.get('title', 'Video')[:50]}\n\n{BOT_USERNAME}",
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
        print("❌ TOKEN topilmadi!")
        exit(1)

    # Render serveri uchun Health Checkni ishga tushirish
    threading.Thread(target=run_health_check, daemon=True).start()

    bot_logic = ProfessionalDownloader()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", bot_logic.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_logic.handle_message))

    print("🚀 Bot ishga tushdi!")
    app.run_polling()
