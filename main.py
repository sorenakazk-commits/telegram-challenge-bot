import os
import re
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --------------------------------------------------------------------------- #
# تنظیمات لاگ
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("userbot")

# --------------------------------------------------------------------------- #
# متغیرهای محیطی
# --------------------------------------------------------------------------- #
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
CHAT_ID = int(os.environ["CHAT_ID"])              # آیدی عددی کانال چالش (-100...)
TARGET_PM_ID = int(os.environ["TARGET_PM_ID"])    # آیدی عددی شخص چالش‌دهنده
CONTROL_CHAT = os.environ.get("CONTROL_CHAT", "me")  # چت فرمان (پیش‌فرض Saved Messages)

TEHRAN = ZoneInfo("Asia/Tehran")

# --------------------------------------------------------------------------- #
# وضعیت ربات
# --------------------------------------------------------------------------- #
armed = False                  # الگوی A: مسلح منتظر پیام بعدی کانال
scheduled_task = None          # task زمان‌بندی‌شده الگوی B
scheduled_info = {"word": None, "time": None}

# کلمات کلیدی پیام‌های اعلان/اطلاعاتی که نباید به عنوان «کلمه چالش» ارسال شوند
SKIP_KEYWORDS = [
    "چالش", "ساعت", "جایزه", "برنده", "عضو", "فوروارد", "لینک",
    "t.me", "http", "@", "📣", "🔴", "💬", "🗣", "کلمه",
    "فرستاد", "پیویم", "پیوی", "حتماً", "سلام",
]

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


# --------------------------------------------------------------------------- #
# هندلر فرمان‌ها (Saved Messages)
# --------------------------------------------------------------------------- #
@client.on(events.NewMessage(chats=CONTROL_CHAT, outgoing=True))
async def control_handler(event):
    global armed, scheduled_task

    text = (event.message.message or "").strip()
    if not text:
        return

    # الگوی A: آماده
    if text == "آماده":
        armed = True
        log.info("ربات مسلح شد - منتظر پیام بعدی کانال")
        await event.reply("✅ ربات مسلح شد.\nمنتظر پیام بعدی کانال می‌مونم.")
        return

    # الگوی B: کلمه <word> <HH:MM>
    m = re.match(r"^کلمه\s+(.+?)\s+(\d{1,2})[:.](\d{1,2})$", text)
    if m:
        word = m.group(1).strip()
        h, mi = int(m.group(2)), int(m.group(3))

        now_teh = datetime.now(TEHRAN)
        target = now_teh.replace(hour=h, minute=mi, second=0, microsecond=0)
        if target <= now_teh:
            target += timedelta(days=1)

        if scheduled_task and not scheduled_task.done():
            scheduled_task.cancel()

        scheduled_info["word"] = word
        scheduled_info["time"] = target
        scheduled_task = asyncio.create_task(schedule_send(target, word))
        log.info("زمان‌بندی: «%s» در %s تهران", word, target.strftime("%H:%M:%S"))
        await event.reply(
            f"⏰ برنامه‌ریزی شد.\nکلمه: «{word}»\nزمان: {target.strftime('%H:%M:%S')} (تهران)"
        )
        return

    # لغو
    if text == "لغو":
        armed = False
        if scheduled_task and not scheduled_task.done():
            scheduled_task.cancel()
        scheduled_task = None
        scheduled_info["word"] = None
        scheduled_info["time"] = None
        await event.reply("❌ لغو شد.")
        return

    # وضعیت
    if text == "وضعیت":
        lines = [f"مسلح: {'بله ✅' if armed else 'خیر'}"]
        if scheduled_info["time"]:
            lines.append(
                f"زمان‌بندی: «{scheduled_info['word']}» در "
                f"{scheduled_info['time'].strftime('%H:%M:%S')}"
            )
        else:
            lines.append("زمان‌بندی: ندارد")
        await event.reply("\n".join(lines))
        return

    # تست شناسایی مقصد
    if text.startswith("تست"):
        parts = text.split()
        target_id = int(parts[1]) if len(parts) > 1 else TARGET_PM_ID
        try:
            entity = await client.get_entity(target_id)
            await event.reply(f"✅ شناسایی شد: {getattr(entity, 'first_name', '?')} (@{getattr(entity, 'username', '?')}) id={entity.id}")
        except Exception as e:
            await event.reply(f"❌ شناسایی نشد: {e}")
        return

    # پینگ - سنجش سرعت ارسال
    if text == "پینگ":
        import time
        t0 = time.monotonic()
        msg = await event.reply("🏓 ...")
        t1 = time.monotonic()
        latency_ms = round((t1 - t0) * 1000, 1)
        await msg.edit(f"🏓 پونگ! تاخیر: {latency_ms}ms")
        return

    # فرمان ناشناخته → نادیده
    return


# --------------------------------------------------------------------------- #
# هندلر پیام‌های کانال
# --------------------------------------------------------------------------- #
@client.on(events.NewMessage(chats=CHAT_ID))
async def channel_handler(event):
    global armed
    if not armed:
        return

    text = (event.message.message or "").strip()
    if not text:
        return

    # رد کردن پیام‌های اعلان/اطلاعاتی
    for kw in SKIP_KEYWORDS:
        if kw in text:
            return
    # پیام‌های خیلی بلند احتمالا اعلان هستند
    if len(text) > 100:
        return

    # ارسال فوری (متن خام، نه فوروارد)
    armed = False
    try:
        await client.send_message(TARGET_PM_ID, text)
        log.info("✅ ارسال شد (armed): %s", text[:60])
        await notify(f"✅ ارسال شد (مسلح): «{text}»")
    except Exception as e:
        log.error("خطا در ارسال: %s", e)
        await notify(f"❌ خطا در ارسال مسلح: {e}")


# --------------------------------------------------------------------------- #
# ارسال پیام به Saved Messages برای اطلاع‌رسانی
# --------------------------------------------------------------------------- #
async def notify(text):
    try:
        await client.send_message("me", text)
    except Exception as e:
        log.error("خطا در ارسال نوتیفیکیشن: %s", e)


# --------------------------------------------------------------------------- #
# زمان‌بندی ارسال راس ساعت (الگوی B)
# --------------------------------------------------------------------------- #
async def schedule_send(target_time, word):
    try:
        log.info("زمان‌بندی فعال: «%s» برای %s", word, target_time.strftime("%H:%M:%S"))
        # تا ۰.۵ ثانیه قبل با sleep، سپس busy-wait برای دقت
        while True:
            now = datetime.now(TEHRAN)
            delta = (target_time - now).total_seconds()
            if delta <= 0:
                break
            if delta > 0.5:
                await asyncio.sleep(delta - 0.5)
            else:
                await asyncio.sleep(0.01)

        log.info("رسید به زمان هدف، در حال ارسال...")
        await client.send_message(TARGET_PM_ID, word)
        log.info("✅ ارسال راس ساعت: %s", word)
        await notify(f"✅ ارسال راس ساعت انجام شد: «{word}»")
    except asyncio.CancelledError:
        log.info("زمان‌بندی لغو شد")
        await notify(f"❌ زمان‌بندی «{word}» لغو شد.")
        raise
    except Exception as e:
        log.error("خطا در ارسال راس ساعت: %s", e)
        await notify(f"❌ خطا در ارسال «{word}»: {e}")
    finally:
        scheduled_info["word"] = None
        scheduled_info["time"] = None


# --------------------------------------------------------------------------- #
# اجرا
# --------------------------------------------------------------------------- #
async def main():
    await client.connect()
    if not await client.is_user_authorized():
        log.error("SESSION_STRING نامعتبر است!")
        return
    me = await client.get_me()
    log.info("ربات آنلاین شد: @%s (id=%s)", me.username, me.id)
    log.info("چت کنترل: %s | کانال: %s | مقصد: %s", CONTROL_CHAT, CHAT_ID, TARGET_PM_ID)
    log.info("زمان‌بندی بر اساس Asia/Tehran")

    # دریافت لیست چت‌ها برای پر کردن کش Telethon
    log.info("در حال دریافت لیست چت‌ها برای شناسایی مقصد...")
    await client.get_dialogs(limit=100)
    log.info("لیست چت‌ها دریافت شد.")

    # تست رزولوشن مقصد
    try:
        entity = await client.get_entity(TARGET_PM_ID)
        log.info("✅ مقصد شناسایی شد: %s (id=%s)", getattr(entity, 'username', '?'), entity.id)
    except Exception as e:
        log.error("❌ مقصد (id=%s) شناسایی نشد!", TARGET_PM_ID)
        log.error("⚠️ از Saved Messages بنویس: تست %s", TARGET_PM_ID)
        log.error("جزئیات: %s", e)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
