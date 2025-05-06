"""
Simple English-only text module for Nota AI.
"""

import logging
import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Cached translations dictionary
_translations = {}

def t(key: str, params: dict = None, lang: str = None) -> str:
    """
    Get a string for the given key, with simple parameter substitution.
    
    Args:
        key: The translation key (e.g., 'status.text_recognized')
        params: Parameters for string formatting (e.g., {"count": 5})
        lang: Ignored parameter for backward compatibility
        
    Returns:
        The English string, or the key itself if not found
    """
    global _translations
    
    # Load translations if not already loaded
    if not _translations:
        try:
            # Get the directory of this file
            current_dir = Path(os.path.dirname(os.path.abspath(__file__)))
            file_path = current_dir / "texts_en.yaml"
            
            if not file_path.exists():
                logger.warning(f"Translation file not found: {file_path}")
                return key
                
            with open(file_path, 'r', encoding='utf-8') as f:
                _translations = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading translations: {str(e)}")
            return key
    
    # Get the value from the nested dictionary
    value = _get_nested_value(_translations, key)
    
    if value is None:
        return key
    
    # Apply string formatting if params are provided
    if params:
        try:
            return value.format(**params)
        except Exception as e:
            logger.error(f"Error formatting translation: {str(e)}")
            return value
    
    return value

def _get_nested_value(data: Dict[str, Any], key_path: str) -> Optional[str]:
    """Get a nested value from a dictionary using dot notation."""
    if not data:
        return None
        
    keys = key_path.split('.')
    result = data
    
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return None
    
    return result if isinstance(result, str) else None