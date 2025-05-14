# Nota Telegram Bot - Fixed Version

This is a fixed version of the Nota Telegram Bot that addresses several critical issues:

## Fixed Issues

1. **Telegram API Conflict**: Resolved the "Conflict: terminated by other getUpdates request" error by:
   - Adding force-restart capability to properly terminate existing sessions
   - Using `drop_pending_updates=True` to prevent duplicate messages
   - Creating a check_and_restart script to safely start the bot

2. **Photo Handler Not Working**: Fixed by:
   - Ensuring the photo router is registered first in the handler registration order
   - Adding detailed logging for handler registration
   - Moving the fallback handler to be registered last

3. **Dependencies**: Ensured all required dependencies are properly installed:
   - Used a virtual environment to avoid system-wide package conflicts
   - Added proper error handling for missing dependencies
   - Added dependencies check in test mode

## How to Run the Bot

### Setup

1. Create a `.env` file with your Telegram Bot token:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   OPENAI_API_KEY=your_openai_api_key (optional)
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running

**Option 1: Direct Start**
```bash
python bot.py
```

**Option 2: Safe Start (Recommended)**
This method will check for running instances, terminate them, and restart properly:
```bash
./check_and_restart.py
```

**Test Mode (Check Dependencies)**
```bash
python bot.py --test-mode
```

**Force Restart**
```bash
python bot.py --force-restart
```

## Troubleshooting

If you encounter issues:

1. Check the logs in the `logs/` directory
2. Make sure no other instances are running: `ps aux | grep bot.py`
3. Try running with force-restart: `python bot.py --force-restart`
4. Verify your Telegram Bot token is correctly set in `.env`

## Directory Structure

- `app/`: Main application code
  - `handlers/`: Message handlers, including photo_handler
  - `utils/`: Utility functions
  - `formatters/`: Report formatting
- `data/`: Product database and other data files
- `tmp/`: Temporary files (automatically cleaned)
- `logs/`: Log files

## Key Features

- OCR processing of invoice photos
- Product name matching
- Interactive editing of invoice items
- Incremental UI updates during processing
- Multiple language support