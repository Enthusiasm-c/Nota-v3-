# Telegram Bot Testing Guide

This document provides guidance on testing the Telegram bot to verify its functionality, especially after applying fixes to the button handlers.

## Overview

We've created a comprehensive test script (`bot_tester_real.py`) that uses the Telethon library to test real interactions with the bot. The script focuses on verifying that the fixes for the "Cancel" and "Upload New Invoice" buttons are working properly.

## Prerequisites

Before running the tests, you'll need:

1. **Python 3** installed on your system
2. **Telethon** library (`pip install telethon`)
3. **Telegram API credentials**:
   - API ID and API Hash (get from https://my.telegram.org/auth)
   - You'll need a Telegram account to get these credentials
4. **A sample invoice image** for testing at `test_data/invoice_sample.jpg`

## Running the Tests

We've provided a helper script (`run_bot_tests.sh`) to make it easy to run the tests:

```bash
# Run all tests
./run_bot_tests.sh --real --api-id YOUR_API_ID --api-hash YOUR_API_HASH

# Test only the cancel button
./run_bot_tests.sh --real --api-id YOUR_API_ID --api-hash YOUR_API_HASH --test cancel

# Test only the "Upload New Invoice" button
./run_bot_tests.sh --real --api-id YOUR_API_ID --api-hash YOUR_API_HASH --test new
```

### Available Test Types

- `all`: Run all tests (default)
- `start`: Test only the start command
- `photo`: Test photo upload functionality
- `cancel`: Test the Cancel button
- `new`: Test the "Upload New Invoice" button
- `flow`: Test the complete user flow (equivalent to 'all')

## Test Flow

The testing script simulates a complete user interaction:

1. **Start conversation**: Sends `/start` command
2. **Upload a photo**: Sends a test invoice image
3. **Wait for processing**: Waits for photo processing to complete
4. **Test Cancel button**: Clicks the Cancel button and verifies proper return to main menu
5. **Test second photo**: Uploads another test photo
6. **Test Upload New Invoice button**: Clicks the "Upload New Invoice" button

## Test Results

After running the tests, you'll see a summary of the results in the console, and detailed logs will be saved to the `logs` directory:

- **Test log file**: Contains detailed logs of the test execution
- **Conversation history**: A readable record of the conversation with the bot

## Troubleshooting

### Common Issues

1. **Button not found**:
   - Check that the button text or data matches what the script is looking for
   - The button might be missing from the message or have different text

2. **No response after button click**:
   - This is the main issue we're trying to fix - if you see this, the button might still be causing the bot to hang
   - Check the bot's logs for errors or exceptions

3. **Processing timeout**:
   - If photo processing times out, you may need to increase the `PROCESSING_TIMEOUT` value in the script

4. **Authentication issues**:
   - Make sure your API credentials are correct
   - The first time you run the script, it will ask you to log in to your Telegram account

### Checking Bot Logs

If tests are failing, check the bot's logs for more information:

```bash
tail -f logs/bot.log
```

## Button Handling Fixes

The main fixes implemented in `simplified_fix.py` address these issues:

1. **cancel:all button**:
   - Now properly sets state before UI operations
   - Includes comprehensive error handling
   - Ensures clean state transitions

2. **action:new button** (Upload New Invoice):
   - Simplified handler that avoids complex operations
   - Proper state management
   - Better error handling

3. **Handler conflicts**:
   - Removed conflicts between handlers in different files
   - Made sure only appropriate handlers process each button type

## Next Steps

If tests are failing, you may need to:

1. Check the bot logs for errors
2. Make further adjustments to the handlers
3. Run `simplified_fix.py` again to apply the fixes
4. Restart the bot using the `start_bot_debugged.sh` script
5. Run the tests again to verify the fixes

## References

- [Telethon Documentation](https://docs.telethon.dev/en/stable/)
- [Telegram Bot API Documentation](https://core.telegram.org/bots/api)