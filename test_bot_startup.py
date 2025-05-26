#!/usr/bin/env python3
"""
Test bot startup and catch any errors
"""

import asyncio
import logging
import sys
import traceback

# Configure logging to see all messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

async def test_bot_startup():
    """Test bot initialization"""
    try:
        print("=== Testing bot startup ===")
        
        # Import bot module
        print("1. Importing bot module...")
        import bot
        
        # Check main components
        print("2. Checking main components...")
        print(f"   - Bot instance: {bot.bot}")
        print(f"   - Dispatcher: {bot.dp}")
        
        # Test bot info
        print("3. Getting bot info...")
        bot_info = await bot.bot.get_me()
        print(f"   - Bot username: @{bot_info.username}")
        print(f"   - Bot name: {bot_info.first_name}")
        print(f"   - Bot ID: {bot_info.id}")
        
        # Check handlers
        print("4. Checking registered handlers...")
        routers = bot.dp._routers
        print(f"   - Number of routers: {len(routers)}")
        
        # Try to start polling for 5 seconds
        print("5. Testing polling (5 seconds)...")
        
        # Create a task for polling
        polling_task = asyncio.create_task(
            bot.dp.start_polling(bot.bot, skip_updates=True)
        )
        
        # Wait 5 seconds
        await asyncio.sleep(5)
        
        # Cancel polling
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        
        print("\n✅ Bot startup test successful!")
        
    except Exception as e:
        print(f"\n❌ Bot startup failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_bot_startup())
    sys.exit(0 if success else 1)