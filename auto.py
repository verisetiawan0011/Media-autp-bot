import telebot
from telebot import types
import os
from datetime import datetime
import sys
from PIL import Image
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost, GetPost
from wordpress_xmlrpc.methods.media import UploadFile

# --- FORCE ASIA/JAKARTA TIMEZONE ---
try:
    import pytz
    local_tz = pytz.timezone("Asia/Jakarta")
except ImportError:
    # Jika pytz belum terinstall di Termux, kita buat fallback manual GMT+7
    from datetime import timezone, timedelta
    local_tz = timezone(timedelta(hours=7))

# --- KONFIGURASI UTAMA ---
BOT_TOKEN = "8556458330:AAF1oMe810cHuk2_p7A3RN3o9965D-bL4ss"
CHANNEL_ID = "-1003796754985"
LOGO_FILE = "logo.png"

# --- CONFIG KEDALUWARSA ---
# Tanggal expired disuntikkan zona waktu lokal Jakarta/WIB
TANGGAL_EXPIRED = datetime(2026, 5, 27, 23, 59, 59).replace(tzinfo=None)
# Kita buat versi sadar zona waktu untuk perbandingan real-time
if hasattr(local_tz, 'localize'):
    TANGGAL_EXPIRED_TZ = local_tz.localize(datetime(2026, 5, 27, 23, 59, 59))
else:
    TANGGAL_EXPIRED_TZ = datetime(2026, 5, 27, 23, 59, 59, tzinfo=local_tz)

PESAN_EXPIRED = "<b>🚨Script Expired. Perbarui Telegram Premium📢</b>"

def cek_status_expired():
    """Fungsi untuk mengecek apakah waktu sekarang sudah lewat batas"""
    sekarang = datetime.now(local_tz)
    return sekarang > TANGGAL_EXPIRED_TZ

def get_pesan_pengingat_realtime():
    """Fungsi hitung mundur real-time mengikuti Jam HP / WIB"""
    sekarang = datetime.now(local_tz)
    if sekarang > TANGGAL_EXPIRED_TZ:
        return PESAN_EXPIRED
        
    selisih = TANGGAL_EXPIRED_TZ - sekarang
    
    # Pecah selisih waktu menjadi Hari, Jam, Menit, dan Detik
    hari = selisih.days
    jam, sisa_detik = divmod(selisih.seconds, 3600)
    menit, detik = divmod(sisa_detik, 60)
    
    tgl_teks = TANGGAL_EXPIRED.strftime("%d %B %Y pukul %H:%M:%S")
    waktu_hitunghundur = f"<b>{hari} Hari, {jam} Jam, {menit} Menit, {detik} Detik</b>"
    
    if hari <= 3:
        return f"⚠️ <b>PERINGATAN PREMIUM:</b>\nMasa aktif bot sisa: {waktu_hitunghundur}\n<i>Batas akhir: {tgl_teks} WIB</i>\n\n"
    else:
        return f"🟢 <b>STATUS AKTIF:</b>\nMasa aktif bot sisa: {waktu_hitunghundur}\n\n"

bot = telebot.TeleBot(BOT_TOKEN)

# --- DATABASE KREDENSIAL ---
WEBSITES = {
    "Infopublik.news": {"url": "https://www.infopublik.news/xmlrpc.php", "user": "autobot_infopublik.news", "pass": "oOjz DcNS MEYN 55Zi BSmH zSJK"},
    "Mediaviralnusantara.com": {"url": "https://www.mediaviralnusantara.com/xmlrpc.php", "user": "autobot_mediaviralnusantara.com", "pass": "D15U TAh6 KvY7 DJyV WBDO 3SEt"},
    "Brantastuntas.com": {"url": "https://www.brantastuntas.com/xmlrpc.php", "user": "autobot_brantastuntas.com", "pass": "b0BZ zKDO YwDG QWw2 iKQh XJTT"},
    "Mediaharianindonesia.com": {"url": "https://www.mediaharianindonesia.com/xmlrpc.php", "user": "autobot_mediaharianindonesia.com", "pass": "b7ev D39V CVLS 5ALI kFIF 4tfO"}
}

user_data = {}

# --- FUNGSI WATERMARK LOGO ---
def proses_watermark(image_path):
    try:
        if not os.path.exists(LOGO_FILE): return False
        base = Image.open(image_path).convert("RGBA")
        logo = Image.open(LOGO_FILE).convert("RGBA")
        base_w, base_h = base.size
        logo_w, logo_h = logo.size
        target_w = int(base_w * 0.15)
        target_h = int(logo_h * (target_w / logo_w))
        logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
        pos = (base_w - target_w - 20, base_h - target_h - 20)
        transparent = Image.new("RGBA", base.size, (0,0,0,0))
        transparent.paste(base, (0,0))
        transparent.paste(logo, pos, mask=logo)
        transparent.convert("RGB").save(image_path, "JPEG", quality=90)
        return True
    except: return False

# --- FUNGSI UNTUK MEMBUAT MENU TOMBOL ---
def get_main_menu_markup():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton("🌐 Info Publik", web_app=types.WebAppInfo(url="https://infopublik.news"))
    btn2 = types.KeyboardButton("🌐 Brantas Tuntas", web_app=types.WebAppInfo(url="https://brantastuntas.com"))
    btn3 = types.KeyboardButton("🌐 Media Harian", web_app=types.WebAppInfo(url="https://mediaharianindonesia.com"))
    btn4 = types.KeyboardButton("🌐 Media Viral", web_app=types.WebAppInfo(url="https://mediaviralnusantara.com"))
    markup.add(btn1, btn2, btn3, btn4)
    return markup

# --- FUNGSI POSTING (DENGAN RETURN LINK) ---
def gas_ke_wordpress_dan_channel(web_name, chat_id):
    d = user_data.get(chat_id)
    if not d: return "❌ Data hilang."
    config = WEBSITES.get(web_name)
    try:
        wp = Client(config['url'], config['user'], config['pass'])
        with open(d['photo'], 'rb') as img:
            file_data = {'name': os.path.basename(d['photo']), 'type': 'image/jpeg', 'bits': img.read(), 'overwrite': True}
        upload_res = wp.call(UploadFile(file_data))

        post = WordPressPost()
        post.title = d['judul']
        post.content = d['isi']
        post.terms_names = {'category': [d['kategori']]}
        post.thumbnail = upload_res['id']
        if d['waktu'] != "now":
            post.date = datetime.strptime(d['waktu'], "%Y-%m-%d %H:%M")
        post.post_status = 'publish'

        post_id = wp.call(NewPost(post))
        post_terbit = wp.call(GetPost(post_id))
        link_berita = post_terbit.link

        pesan_channel = (f"📢 <b>{web_name}</b>\n 📂 {d['kategori']}\n📌 <b>{d['judul']}</b>\n\n🔗 {link_berita}")
        bot.send_message(CHANNEL_ID, pesan_channel, parse_mode='HTML')

        return f"✅ <b>{web_name}</b>: Berhasil!\n🔗 {link_berita}"
    except Exception as e:
        return f"❌ <b>{web_name}</b>: Gagal ({str(e)})"

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def start(message):
    if cek_status_expired():
        bot.send_message(message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return

    info_status = get_pesan_pengingat_realtime()
    
    bot.send_message(
        message.chat.id,
        f"🪩 <b>AUTOMEDIALAMPUNG-BOT READY!</b>\n\n"
        f"{info_status}"
        f"Silakan kirim foto untuk mulai posting ke WordPress, atau buka portal berita melalui menu di bawah:🪩✍️",
        parse_mode='HTML',
        reply_markup=get_main_menu_markup()
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if cek_status_expired():
        bot.send_message(message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)
    path = f"temp_{message.chat.id}.jpg"
    with open(path, 'wb') as f: f.write(downloaded)

    proses_watermark(path)
    user_data[message.chat.id] = {'photo': path}
    msg = bot.reply_to(message, "📸 <b>Foto + Logo OK!</b>\nMasukkan <b>JUDUL</b>:", parse_mode='HTML')
    bot.register_next_step_handler(msg, get_judul)

def get_judul(message):
    if cek_status_expired():
        bot.send_message(message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return
    user_data[message.chat.id]['judul'] = message.text
    msg = bot.reply_to(message, "✍️ Judul OK. Masukkan <b>ISI BERITA</b>:", parse_mode='HTML')
    bot.register_next_step_handler(msg, get_isi)

def get_isi(message):
    if cek_status_expired():
        bot.send_message(message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return
    user_data[message.chat.id]['isi'] = message.text
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("Nasional", callback_data="set_kat_Nasional"),
               types.InlineKeyboardButton("Kabar Daerah", callback_data="set_kat_Kabar Daerah"))
    bot.send_message(message.chat.id, "📂 Pilih <b>KATEGORI</b>:", parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_kat_"))
def callback_kat(call):
    if cek_status_expired():
        bot.answer_callback_query(call.id, "Expired!")
        bot.send_message(call.message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return
    user_data[call.message.chat.id]['kategori'] = call.data.replace("set_kat_", "")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🕒 Sekarang", callback_data="set_time_now"),
               types.InlineKeyboardButton("📅 Pilih Tanggal", callback_data="set_time_custom"))
    bot.edit_message_text(f"Kategori: <b>{user_data[call.message.chat.id]['kategori']}</b>\n⏰ Atur <b>WAKTU</b>:", call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_time_"))
def callback_time(call):
    if cek_status_expired():
        bot.answer_callback_query(call.id, "Expired!")
        bot.send_message(call.message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return
    if call.data == "set_time_now":
        user_data[call.message.chat.id]['waktu'] = "now"
        show_final(call.message)
    else:
        msg = bot.send_message(call.message.chat.id, "📅 Format: <code>2026-03-31 20:00</code>", parse_mode='HTML')
        bot.register_next_step_handler(msg, get_custom_time)

def get_custom_time(message):
    if cek_status_expired():
        bot.send_message(message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return
    try:
        datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        user_data[message.chat.id]['waktu'] = message.text
        show_final(message)
    except:
        msg = bot.reply_to(message, "❌ Format salah!", parse_mode='HTML')
        bot.register_next_step_handler(msg, get_custom_time)

def show_final(message):
    d = user_data[message.chat.id]
    markup = types.InlineKeyboardMarkup(row_width=1)
    for web in WEBSITES.keys():
        markup.add(types.InlineKeyboardButton(f"🚀 Post ke {web}", callback_data=f"exec_{web}"))
    markup.add(types.InlineKeyboardButton("🔥 SEBAR KE SEMUA 🔥", callback_data="exec_ALL"))
    bot.send_message(message.chat.id, f"📝 <b>RINGKASAN</b>\n📌 {d['judul']}\n📂 {d['kategori']}\n⏰ {d['waktu']}\n\nSiap Bos?", parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("exec_"))
def callback_exec(call):
    if cek_status_expired():
        bot.answer_callback_query(call.id, "Expired!")
        bot.send_message(call.message.chat.id, PESAN_EXPIRED, parse_mode='HTML')
        return
    chat_id = call.message.chat.id
    target = call.data.replace("exec_", "")
    bot.edit_message_text("⚙️ Memproses Berita ke Website...", chat_id, call.message.message_id)

    path_foto = user_data[chat_id]['photo']
    if target == "ALL":
        for name in WEBSITES.keys():
            hasil = gas_ke_wordpress_dan_channel(name, chat_id)
            bot.send_message(chat_id, hasil, parse_mode='HTML', disable_web_page_preview=False)
    else:
        hasil = gas_ke_wordpress_dan_channel(target, chat_id)
        bot.send_message(chat_id, hasil, parse_mode='HTML', disable_web_page_preview=False)

    if os.path.exists(path_foto): os.remove(path_foto)
    del user_data[chat_id]
    
    info_status = get_pesan_pengingat_realtime()
    bot.send_message(chat_id, f"✅ <b>Tugas Selesai!</b>\n\n📢 {info_status}Silakan update / perpanjang <b>Telegram Premium</b> Anda agar bot tetap aktif.", parse_mode='HTML')

if __name__ == "__main__":
    bot.infinity_polling()
