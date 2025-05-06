# Multi-Edit Commands Support

This feature allows users to input multiple edit commands in a single message, separated by commas, semicolons, or periods. The assistant can now parse and execute these commands in sequence.

## How It Works

1. The system now splits user input on punctuation marks (commas, semicolons, periods) and treats each segment as a separate command.
2. The splitting logic uses a regex that avoids splitting numbers with decimal points (e.g., `3.14`).
3. The assistant's system prompt has been updated to handle multiple commands and return them in an `actions` array.

## Implementation Details

### Command Parsing

The command parsing logic in `app/assistants/client.py` has been enhanced:

```python
# Split commands by newlines, semicolons, commas, or periods
import re
# First replace newlines with semicolons, then split by semicolons, commas, or periods
# We use a regex to avoid splitting on periods within numbers (e.g., "3.14")
cleaned_input = user_input.replace('\n', ';')
# Split on semicolons, commas, or periods that are followed by a space or end of string
commands = [c.strip() for c in re.split(r'[;,.](?=\s|\Z)', cleaned_input) if c.strip()]
```

### System Prompt

The assistant's system prompt has been updated to include:

1. New requirement: "Разбивай пользовательский текст на запятые, точки с запятой или точки и обрабатывай каждую часть как отдельную команду редактирования"
2. New examples of multi-command inputs with their expected outputs

### Assistant Update Script

A new script has been added at `scripts/update_assistant.py` to update the assistant with the new system prompt:

```bash
python scripts/update_assistant.py
```

## Examples

Users can now input commands like:

- "строка 1 цена 100, строка 2 количество 5"
- "дата 01.06.2025. Добавить молоко 2 л 120 руб. изменить цену в строке 3 на 200."
- "поставщик ООО Ромашка; строка 1 цена 100, строка 2 количество 5."

The system will parse each part as a separate command and execute them all in sequence.

## Testing

Added tests in `tests/test_parse_commands_edge_cases.py` to verify:

1. Command parsing with different separators
2. Correct handling of decimal points in numbers
3. Combinations of different separators