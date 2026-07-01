"""
اسکریپت یک‌بار مصرف برای ساخت SESSION_STRING
این فایل را روی سیستم خودتان (لوکال) اجرا کنید، نه روی Railway.

نحوه اجرا:
    pip install telethon
    python generate_session.py
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = input("API_ID را وارد کنید: ").strip()
    api_hash = input("API_HASH را وارد کنید: ").strip()

    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        # client.start شماره تلفن و کد تایید را می‌پرسد
        me = await client.get_me()
        print("\n" + "=" * 60)
        print("ورود موفق بود به عنوان: @", me.username)
        print("=" * 60)
        print("\nSESSION_STRING شما (این را روی Railway قرار دهید):\n")
        print(client.session.save())
        print("\n" + "=" * 60)
        print("این رشته را محرمانه نگه دارید!")


if __name__ == "__main__":
    asyncio.run(main())
