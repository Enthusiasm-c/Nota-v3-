#!/usr/bin/env python
"""
Script to update the OpenAI Assistant with a new system prompt.
This allows us to update the assistant without manually copying the prompt in the OpenAI UI.

Usage:
    python scripts/update_assistant.py
"""

import sys
from pathlib import Path
from openai import OpenAI

# Add the project root to the path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

def update_assistant():
    """Update the assistant with the new system prompt."""
    # Check if we have the required environment variables
    if not settings.OPENAI_CHAT_KEY:
        print("Error: OPENAI_CHAT_KEY not set in environment or .env file")
        return False
        
    if not settings.OPENAI_ASSISTANT_ID:
        print("Error: OPENAI_ASSISTANT_ID not set in environment or .env file")
        return False
        
    # Read the prompt file
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "edit_assistant_v1.0.txt"
    if not prompt_path.exists():
        print(f"Error: Prompt file not found at {prompt_path}")
        return False
        
    with open(prompt_path, "r", encoding="utf-8") as f:
        instructions = f.read()
    
    # Initialize the OpenAI client
    client = OpenAI(api_key=settings.OPENAI_CHAT_KEY)
    
    try:
        # Update the assistant
        assistant = client.beta.assistants.update(
            assistant_id=settings.OPENAI_ASSISTANT_ID,
            instructions=instructions,
        )
        print(f"Successfully updated assistant: {assistant.id}")
        print(f"Model: {assistant.model}")
        print(f"Name: {assistant.name}")
        print(f"Instructions length: {len(instructions)} chars")
        return True
    except Exception as e:
        print(f"Error updating assistant: {e}")
        return False

if __name__ == "__main__":
    success = update_assistant()
    sys.exit(0 if success else 1)