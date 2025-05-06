"""
Internationalization (i18n) module for Nota AI.
Provides translation functions for multi-language support.
"""

import os
import logging
import yaml
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Dictionary to store loaded translations
_translations: Dict[str, Dict[str, Any]] = {}

def load_translations(lang: str) -> Dict[str, Any]:
    """
    Load translations for the specified language.
    
    Args:
        lang: The language code to load (e.g., 'en', 'ru')
        
    Returns:
        Dictionary with translation keys
    """
    if lang in _translations:
        return _translations[lang]
    
    try:
        # Get the directory of this file
        current_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        file_path = current_dir / f"texts_{lang}.yaml"
        
        if not file_path.exists():
            logger.warning(f"Translation file for language '{lang}' not found: {file_path}")
            # Fall back to English if the requested language is not available
            if lang != "en":
                return load_translations("en")
            return {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            translations = yaml.safe_load(f)
            _translations[lang] = translations
            return translations
    except Exception as e:
        logger.error(f"Error loading translations for '{lang}': {str(e)}")
        # Fall back to empty dict in case of errors
        return {}

def get_nested_value(data: Dict[str, Any], key_path: str) -> Optional[str]:
    """
    Get a nested value from a dictionary using dot notation.
    
    Args:
        data: The dictionary to search in
        key_path: The path to the value (e.g., 'button.edit')
        
    Returns:
        The value if found, None otherwise
    """
    keys = key_path.split('.')
    result = data
    
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return None
    
    return result if isinstance(result, str) else None

def t(key: str, lang: str = "en", **kwargs) -> str:
    """
    Get a translated string for the given key and language.
    
    Args:
        key: The translation key (e.g., 'button.edit')
        lang: The language code (default: 'en')
        **kwargs: Format arguments to be inserted into the translated string
        
    Returns:
        The translated string, or the key itself if not found
    """
    translations = load_translations(lang)
    value = get_nested_value(translations, key)
    
    if value is None:
        logger.warning(f"Translation key '{key}' not found for language '{lang}'")
        return key
    
    # Apply string formatting if kwargs are provided
    if kwargs:
        try:
            return value.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing format argument in translation: {str(e)}")
            return value
        except Exception as e:
            logger.error(f"Error formatting translation: {str(e)}")
            return value
    
    return value