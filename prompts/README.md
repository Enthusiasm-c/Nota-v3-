# Assistant Prompts

This directory contains the system prompts used for OpenAI Assistants.

## Files

- `edit_assistant_v1.0.txt` - System prompt for the edit assistant

## Updating Assistants

After modifying any prompts, you need to update the assistant with the new instructions.

### Using the Script

The easiest way to update the assistant is to use the provided script:

```bash
python scripts/update_assistant.py
```

This will read the prompt from `prompts/edit_assistant_v1.0.txt` and update the assistant specified by the `OPENAI_ASSISTANT_ID` environment variable.

### Manual Update

If you need to update the assistant manually through the OpenAI UI:

1. Go to [OpenAI Platform](https://platform.openai.com/assistants)
2. Select the assistant you want to update
3. Copy the content of the prompt file
4. Paste it into the "Instructions" field
5. Save the changes

## Version History

### edit_assistant_v1.0.txt

- Initial version with support for basic edit operations
- Added multi-edit commands support (splitting by commas, semicolons, periods)

## Important Notes

- Always test prompt changes thoroughly before deploying to production
- Update the version number in the filename when making significant changes
- Document the changes in this README
