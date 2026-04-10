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

# --- KONFIGURATSIYA ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = "downloads"
BOT_USERNAME = "@GoYuklaBot" # Bot username

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CHIROYLI MATNLAR TO'PLAMI ---
class UI:
    WELCOME = (
        "<b>👋 Assalomu alaykum, {}!</b>\n\n"
        "Men professional <b>Media Yuklovchi</b> botman. ✨\n\n"
        "📌 <b>Nimalar qila olaman?</b>\n"
        " 📥 <i>YouTube, Instagram, TikTok va Facebook'dan video yuklash.</i>\n"
        " 🎵 <i>Musiqa nomini yozsangiz, qidirib topib berish.</i>\n\n"
        "✨ <b>Boshlash uchun link yuboring yoki musiqa nomini yozing:</b>"
    )
    PROCESSING = "⏳ <b>Iltimos, kuting...</b>\n🔄 <i>So'rovingizga ishlov berilmoqda...</i>"
    UPLOADING = "📤 <b>Tayyor!</b>\n✨ <i>Fayl Telegramga yuklanmoqda...</i>"
    
    # Video va Audio tagidagi imzo
    CAPTION_VIDEO = "🎬 <b>{}</b>\n\n✨ {}: Yuklab beruvchi bot"
    CAPTION_MUSIC = "🎵 <b>{}</b>\n\n✨ {}: Yuklab beruvchi bot"
    
    ERROR = "❌ <b>Kechirasiz, {}!</b>\n\n Xatolik yuz berdi."
    NOT_FOUND = "🔍 <b>Afsuski, hech narsa topilmadi.</b>"

# --- YT-DLP SOZLAMALARI ---
def get_ydl_opts(file_base, is_audio=False):
    opts = {
        'outtmpl': f'{file_base}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'referer': 'https://www.google.com/',
    }
    
    if is_audio:
        # Renderda FFmpeg muammosi bo'lmasligi uchun postprocessor'lar olib tashlandi
        opts.update({
            'format': 'bestaudio/best',
        })
    else:
        opts.update({
            'format': 'best[ext=mp4]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
        })
    
    return opts

# --- BOT LOGIKASI ---
class ProfessionalDownloader:
    def __init__(self):
        self.platforms = ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "facebook.com", "fb.watch"]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_name = update.effective_user.first_name
        await update.message.reply_text(
            UI.WELCOME.format(user_name),
            parse_mode=ParseMode.HTML
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if not text: return

        if any(p in text.lower() for p in self.platforms) or text.startswith("http"):
            await self.process_download(update, context, text)
        else:
            await self.youtube_search(update, context, text)

    async def process_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        status_msg = await update.message.reply_text(UI.PROCESSING, parse_mode=ParseMode.HTML)
        file_id = str(uuid.uuid4())
        file_base = os.path.join(DOWNLOAD_DIR, file_id)
        user_name = update.effective_user.first_name

        try:
            loop = asyncio.get_running_loop()
            with yt_dlp.YoutubeDL(get_ydl_opts(file_base)) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                title = info.get('title', 'Video')

            file_path = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(file_id):
                    file_path = os.path.join(DOWNLOAD_DIR, f)
                    break

            if not file_path: raise Exception("Fayl topilmadi.")

            await status_msg.edit_text(UI.UPLOADING, parse_mode=ParseMode.HTML)
            
            with open(file_path, 'rb') as f:
                caption_text = UI.CAPTION_VIDEO.format(title, BOT_USERNAME)
                await update.message.reply_video(
                    video=f, 
                    caption=caption_text,
                    parse_mode=ParseMode.HTML
                )
            
            await status_msg.delete()

        except Exception as e:
            logger.error(f"Error: {e}")
            await status_msg.edit_text(UI.ERROR.format(user_name), parse_mode=ParseMode.HTML)
        finally:
            self.cleanup(file_base)

    async def youtube_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
        status_msg = await update.message.reply_text(f"🔍 <b>\"{query}\"</b> qidirilmoqda...", parse_mode=ParseMode.HTML)
        file_id = str(uuid.uuid4())
        file_base = os.path.join(DOWNLOAD_DIR, file_id)
        user_name = update.effective_user.first_name

        try:
            loop = asyncio.get_running_loop()
            # Musiqa qidirish va yuklash (FFmpegsiz)
            with yt_dlp.YoutubeDL(get_ydl_opts(file_base, is_audio=True)) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch1:{query}", download=True))
                
                if not info or 'entries' not in info or not info['entries']:
                    await status_msg.edit_text(UI.NOT_FOUND, parse_mode=ParseMode.HTML)
                    return
                
                entry = info['entries'][0]
                title = entry.get('title', 'Musiqa')

            # Yuklangan faylni kengaytmasidan qat'iy nazar topish
            file_path = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(file_id):
                    file_path = os.path.join(DOWNLOAD_DIR, f)
                    break

            if file_path and os.path.exists(file_path):
                await status_msg.edit_text(UI.UPLOADING, parse_mode=ParseMode.HTML)
                with open(file_path, 'rb') as f:
                    caption_text = UI.CAPTION_MUSIC.format(title, BOT_USERNAME)
                    await update.message.reply_audio(
                        audio=f, 
                        title=title, 
                        caption=caption_text,
                        parse_mode=ParseMode.HTML
                    )
                await status_msg.delete()
            else:
                await status_msg.edit_text(UI.NOT_FOUND, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Search error: {e}")
            await status_msg.edit_text(UI.ERROR.format(user_name), parse_mode=ParseMode.HTML)
        finally:
            self.cleanup(file_base)

    def cleanup(self, base):
        try:
            base_dir = os.path.dirname(base)
            base_name = os.path.basename(base)
            for f in os.listdir(base_dir):
                if f.startswith(base_name):
                    os.remove(os.path.join(base_dir, f))
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("XATO: BOT_TOKEN topilmadi!")
    else:
        bot = ProfessionalDownloader()
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", bot.start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
        
        print(f"✨ {BOT_USERNAME} ishga tushdi!")
        app.run_polling()
