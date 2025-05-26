#!/usr/bin/env python3
"""
Run bot with enhanced error logging
"""

import asyncio
import logging
import sys
import traceback
from datetime import datetime

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'logs/bot_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)

# Suppress some noisy loggers
logging.getLogger('aiogram').setLevel(logging.INFO)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

async def run_bot():
    """Run the bot with error handling"""
    try:
        print("=== Starting Nota Bot ===")
        print(f"Time: {datetime.now()}")
        
        # Import after logging is configured
        from bot import create_bot_and_dispatcher, register_handlers, _check_dependencies
        
        # Check dependencies
        print("\n1. Checking dependencies...")
        if not _check_dependencies():
            print("❌ Failed dependency check")
            return False
        print("✅ Dependencies OK")
        
        # Create bot and dispatcher
        print("\n2. Creating bot and dispatcher...")
        bot, dp = create_bot_and_dispatcher()
        print(f"✅ Bot created")
        
        # Get bot info
        print("\n3. Getting bot info...")
        try:
            bot_info = await bot.get_me()
            print(f"✅ Bot info retrieved:")
            print(f"   - Username: @{bot_info.username}")
            print(f"   - Name: {bot_info.first_name}")
            print(f"   - ID: {bot_info.id}")
        except Exception as e:
            print(f"❌ Failed to get bot info: {e}")
            return False
        
        # Register handlers
        print("\n4. Registering handlers...")
        register_handlers(dp, bot)
        print("✅ Handlers registered")
        
        # Start polling
        print("\n5. Starting polling...")
        print("Bot is running! Press Ctrl+C to stop.")
        print("-" * 50)
        
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Bot stopped by user")
        return True
    except Exception as e:
        print(f"\n\n❌ Bot crashed with error: {type(e).__name__}: {e}")
        traceback.print_exc()
        
        # Log to file
        with open('logs/bot_crash.log', 'a') as f:
            f.write(f"\n\n{'='*60}\n")
            f.write(f"Crash at {datetime.now()}\n")
            f.write(f"Error: {type(e).__name__}: {e}\n")
            f.write(traceback.format_exc())
        
        return False
    
    return True


def main():
    """Main entry point"""
    print("Starting Nota Bot with enhanced logging...")
    
    # Check if we can import required modules
    try:
        import aiogram
        import openai
        from app.config import settings
        
        print(f"✓ aiogram version: {aiogram.__version__}")
        print(f"✓ Bot token configured: {'Yes' if settings.TELEGRAM_BOT_TOKEN else 'No'}")
        print(f"✓ OpenAI keys configured: {'Yes' if settings.OPENAI_OCR_KEY else 'No'}")
        
    except ImportError as e:
        print(f"❌ Missing required module: {e}")
        sys.exit(1)
    
    # Run the bot
    try:
        success = asyncio.run(run_bot())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Failed to run bot: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()