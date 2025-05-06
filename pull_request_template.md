# Enhanced Command Parsing for Multi-edit Commands

## Summary
- Added support for multi-edit commands separated by commas, semicolons, or periods
- Updated assistant system prompt to handle multiple commands in a single message

## Changes Made
1. Updated `edit_assistant_v1.0.txt` system prompt to:
   - Add a new requirement (#6) for splitting user text by punctuation
   - Add examples of multi-command requests with expected responses

2. Enhanced `parse_edit_command` function in `app/assistants/client.py` to:
   - Split user input on commas, semicolons, or periods (but not periods in numbers)
   - Use regex to properly handle edge cases

3. Added tests for multi-command parsing in `tests/test_parse_commands_edge_cases.py`

## Testing
- Added unit tests to verify command parsing with different separators
- Tested edge cases like decimal points in numbers to ensure they don't get split

## How to Use
Now users can input multiple commands in a single message, like:
- "строка 1 цена 100, строка 2 количество 5" 
- "строка 1 название Молоко. строка 1 цена 200. строка 1 количество 3"

The assistant will parse each part as a separate command and execute them all.