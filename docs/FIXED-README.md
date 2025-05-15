# Nota Invoice Processing Telegram Bot

A Telegram bot for processing invoice photos, extracting data using OCR, and sending the information to Syrve API.

## Features

- Process invoice photos automatically via Telegram
- Extract text from images using OpenAI Vision API
- Match extracted products with a database
- Edit and correct data before sending
- Integration with Syrve API
- Multi-language support

## Requirements

- Python 3.8+
- Telegram Bot Token
- OpenAI API Keys
- Syrve API credentials

## Quick Start

1. Clone the repository
2. Set up environment variables in `.env` file
3. Install dependencies
4. Run the bot

### Environment Setup

Create a `.env` file with the following variables:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_OCR_KEY=your_openai_vision_api_key
OPENAI_CHAT_KEY=your_openai_chat_api_key
OPENAI_ASSISTANT_ID=your_assistant_id
OPENAI_VISION_ASSISTANT_ID=your_vision_assistant_id

SYRVE_SERVER_URL=https://your-syrve-instance:443
SYRVE_LOGIN=your_login
SYRVE_PASSWORD=your_password
DEFAULT_STORE_ID=your_store_id

USE_OPENAI_OCR=1
MATCH_THRESHOLD=0.65
```

### Installation

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Bot

The recommended way to run the bot is using the provided script:

```bash
# Make scripts executable
chmod +x run_bot.sh

# Start the bot
./run_bot.sh
```

This will:
1. Check for existing bot instances and stop them
2. Reset the webhook to prevent conflicts
3. Start the bot with proper environment settings
4. Monitor the bot process for clean shutdown

### Manual Restart

If you need to manually restart the bot:

```bash
# Using the helper script
python check_and_restart.py
```

## Troubleshooting

### Common Issues

1. **"Conflict: terminated by other getUpdates request"**:
   - Use `check_and_restart.py` to ensure only one instance is running
   - Check for stale processes with `ps aux | grep bot.py`

2. **Bot not responding to photos**:
   - Verify your OpenAI API keys in `.env`
   - Check the logs for OCR errors
   - Ensure the photo handler is registered correctly

3. **Cancel button makes bot unresponsive**:
   - This issue should be fixed in the latest version
   - If it persists, restart the bot with `python check_and_restart.py`

### Viewing Logs

Logs are stored in the `logs` directory:

```bash
# View real-time logs
tail -f logs/bot.log

# Check for errors
grep ERROR logs/bot.log
```

## Configuration

### Customizing Product Matching

Edit the following parameters in your `.env` file:

```
MATCH_THRESHOLD=0.65     # Minimum similarity score for matching
MATCH_EXACT_BONUS=0.1    # Bonus for exact matches
MATCH_LENGTH_PENALTY=0.05 # Penalty for length differences
MATCH_MIN_SCORE=0.5      # Absolute minimum score
```

### Product Database

The bot uses CSV files for product matching:
- `data/base_products.csv`: Base product database
- `data/learned_products.csv`: Learned aliases for products

## Development

### Project Structure

- `bot.py`: Main bot file and entry point
- `app/`: Main application code
  - `handlers/`: Message and callback handlers
  - `fsm/`: Finite State Machine states
  - `utils/`: Utility functions
  - `formatters/`: Output formatting
- `check_and_restart.py`: Bot instance management script
- `run_bot.sh`: Production run script

### Adding New Features

To add new handlers:
1. Create a new file in `app/handlers/`
2. Define a router and register your handler functions
3. Import and include your router in `bot.py`

## License

This project is proprietary software. All rights reserved.