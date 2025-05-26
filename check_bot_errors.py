#!/usr/bin/env python3
"""Quick bot error check"""

import asyncio
import sys
import traceback

async def check_bot():
    try:
        print("1. Importing modules...")
        from app.config import settings
        from bot import create_bot_and_dispatcher, register_handlers
        
        print("2. Checking configuration...")
        if not settings.TELEGRAM_BOT_TOKEN:
            print("❌ ERROR: TELEGRAM_BOT_TOKEN not configured")
            return False
            
        print("3. Creating bot instance...")
        bot, dp = create_bot_and_dispatcher()
        
        print("4. Testing bot connection...")
        bot_info = await bot.get_me()
        print(f"✅ Bot connected: @{bot_info.username}")
        
        print("5. Registering handlers...")
        register_handlers(dp, bot)
        
        print("\n✅ Bot initialization successful!")
        print(f"Bot is ready to run as @{bot_info.username}")
        
        await bot.session.close()
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(check_bot())
    sys.exit(0 if success else 1)