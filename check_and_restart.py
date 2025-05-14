#!/usr/bin/env python3
"""
Check and restart Telegram bot script.

This script:
1. Checks if Telegram bot session is already running
2. Forcefully terminates any conflicting sessions 
3. Starts the bot with the --force-restart flag
"""

import os
import sys
import time
import requests
import subprocess
import logging
import signal
from configparser import ConfigParser

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def get_bot_token():
    """Get bot token from environment or .env file."""
    # Try environment first
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if token:
        return token
    
    # Try .env file
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith('TELEGRAM_BOT_TOKEN='):
                    return line.strip().split('=', 1)[1].strip('"\'')
    except Exception as e:
        logger.error(f"Error reading .env file: {e}")
    
    return None

def kill_python_processes_with_bot_py():
    """Find and kill all python processes that contain 'bot.py' in their command line."""
    killed = 0
    for process in os.popen("ps aux | grep -i 'python.*bot.py' | grep -v grep").read().strip().split('\n'):
        if not process:
            continue
        
        try:
            # Extract PID
            parts = process.split()
            if len(parts) > 1:
                pid = int(parts[1])
                logger.info(f"Killing process {pid}: {' '.join(parts[10:])}")
                os.kill(pid, signal.SIGTERM)
                killed += 1
        except Exception as e:
            logger.error(f"Error killing process: {e}")
    
    logger.info(f"Killed {killed} processes")
    if killed > 0:
        # Give processes time to clean up
        time.sleep(1)
    
    return killed

def check_telegram_bot_status(token):
    """Check if bot is already active by making a getMe request."""
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=5
        )
        
        data = response.json()
        if data.get('ok'):
            bot_info = data.get('result', {})
            logger.info(f"Bot active: @{bot_info.get('username')} (ID: {bot_info.get('id')})")
            return True, bot_info
        else:
            logger.error(f"Bot status error: {data.get('description')}")
            return False, data
    except Exception as e:
        logger.error(f"Error checking bot status: {e}")
        return False, None

def reset_telegram_webhook(token):
    """Reset webhook to ensure polling works correctly."""
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true",
            timeout=5
        )
        
        data = response.json()
        if data.get('ok'):
            logger.info("Webhook reset successfully")
            return True
        else:
            logger.error(f"Webhook reset error: {data.get('description')}")
            return False
    except Exception as e:
        logger.error(f"Error resetting webhook: {e}")
        return False

def start_bot():
    """Start the bot with force-restart flag."""
    try:
        # Build command with appropriate Python executable
        if os.path.exists('venv/bin/python'):
            cmd = ["venv/bin/python", "bot.py", "--force-restart"]
        else:
            cmd = ["python3", "bot.py", "--force-restart"]
        
        logger.info(f"Starting bot: {' '.join(cmd)}")
        
        # Start process detached from this one
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        
        # Wait a moment to see if it starts
        time.sleep(2)
        
        if process.poll() is None:
            logger.info("Bot started successfully")
            return True
        else:
            stdout, stderr = process.communicate()
            logger.error(f"Bot failed to start. Exit code: {process.returncode}")
            logger.error(f"STDOUT: {stdout.decode('utf-8')}")
            logger.error(f"STDERR: {stderr.decode('utf-8')}")
            return False
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return False

def main():
    # Change to the script's directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Get token
    token = get_bot_token()
    if not token:
        logger.error("Could not find Telegram bot token. Set TELEGRAM_BOT_TOKEN in .env file.")
        return 1
    
    # Kill existing processes
    logger.info("Checking for existing bot processes...")
    killed = kill_python_processes_with_bot_py()
    
    # Check if bot is active
    logger.info("Checking Telegram bot status...")
    is_active, bot_info = check_telegram_bot_status(token)
    
    # Reset webhook to be safe
    logger.info("Resetting Telegram webhook...")
    reset_telegram_webhook(token)
    
    # Start bot
    logger.info("Starting bot...")
    if start_bot():
        logger.info("Bot check and restart completed successfully!")
        return 0
    else:
        logger.error("Failed to start bot")
        return 1

if __name__ == "__main__":
    sys.exit(main())