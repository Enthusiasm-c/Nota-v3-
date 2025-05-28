"""
Date correction interface for Telegram bot.

Provides user-friendly date correction functionality when OCR fails to
extract invoice date properly.
"""

import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.validators.date_validator import DateCorrectionHelper
from app.edit.apply_intent import set_date

logger = logging.getLogger(__name__)


class DateCorrectionInterface:
    """
    Interface for correcting invoice dates when OCR extraction fails.
    """

    @staticmethod
    def create_date_warning_keyboard(current_date: Optional[str] = None) -> InlineKeyboardMarkup:
        """
        Create keyboard for date correction warning.
        
        Args:
            current_date: Current date that will be used (formatted as DD.MM.YYYY)
            
        Returns:
            Inline keyboard with correction options
        """
        buttons = [
            [
                InlineKeyboardButton(
                    text="✅ Use current date", 
                    callback_data="date:use_current"
                ),
                InlineKeyboardButton(
                    text="✏️ Correct date", 
                    callback_data="date:correct"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel sending", 
                    callback_data="date:cancel"
                )
            ]
        ]
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def create_date_suggestion_keyboard(suggestions: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        """
        Create keyboard with date suggestions based on OCR text.
        
        Args:
            suggestions: List of date suggestions from DateCorrectionHelper
            
        Returns:
            Inline keyboard with date options
        """
        buttons = []
        
        # Add suggested dates
        for i, suggestion in enumerate(suggestions[:3]):  # Max 3 suggestions
            date_obj = suggestion["date"]
            formatted_date = date_obj.strftime("%d.%m.%Y")
            confidence = suggestion["confidence"]
            
            # Create button text with confidence indicator
            if confidence >= 0.8:
                confidence_emoji = "🎯"
            elif confidence >= 0.6:
                confidence_emoji = "👍"
            else:
                confidence_emoji = "🤔"
            
            button_text = f"{confidence_emoji} {formatted_date}"
            callback_data = f"date:select:{date_obj.isoformat()}"
            
            buttons.append([InlineKeyboardButton(
                text=button_text, 
                callback_data=callback_data
            )])
        
        # Add manual input option
        buttons.append([InlineKeyboardButton(
            text="✏️ Enter date manually", 
            callback_data="date:manual"
        )])
        
        # Add cancel option
        buttons.append([InlineKeyboardButton(
            text="❌ Cancel", 
            callback_data="date:cancel"
        )])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def parse_manual_date_input(user_input: str) -> Optional[date]:
        """
        Parse manual date input from user.
        
        Args:
            user_input: User's date input string
            
        Returns:
            Parsed date or None if parsing failed
        """
        from app.validators.date_validator import DateValidator
        
        validator = DateValidator()
        return validator._parse_date(user_input)

    @staticmethod
    def format_date_for_display(date_obj: date) -> str:
        """
        Format date for user-friendly display.
        
        Args:
            date_obj: Date object to format
            
        Returns:
            Formatted date string (DD.MM.YYYY)
        """
        return date_obj.strftime("%d.%m.%Y")

    @staticmethod
    def format_date_for_system(date_obj: date) -> str:
        """
        Format date for system use (ISO format).
        
        Args:
            date_obj: Date object to format
            
        Returns:
            ISO formatted date string (YYYY-MM-DD)
        """
        return date_obj.isoformat()

    @staticmethod
    def suggest_dates_from_ocr_text(ocr_text: str) -> List[Dict[str, Any]]:
        """
        Generate date suggestions from OCR text.
        
        Args:
            ocr_text: Original OCR text that might contain date
            
        Returns:
            List of date suggestions
        """
        return DateCorrectionHelper.suggest_date_corrections(ocr_text)

    @staticmethod
    def apply_date_correction(invoice_data: Dict[str, Any], new_date: date) -> Dict[str, Any]:
        """
        Apply date correction to invoice data.
        
        Args:
            invoice_data: Original invoice data
            new_date: New date to apply
            
        Returns:
            Updated invoice data
        """
        # Use the existing set_date function from apply_intent
        return set_date(invoice_data, new_date.isoformat())

    @staticmethod
    def create_date_confirmation_message(
        original_ocr_date: Optional[str],
        suggested_date: date,
        confidence: str = "medium"
    ) -> str:
        """
        Create confirmation message for date correction.
        
        Args:
            original_ocr_date: Original date from OCR (if any)
            suggested_date: Suggested date to use
            confidence: Confidence level of the suggestion
            
        Returns:
            Formatted confirmation message
        """
        formatted_date = DateCorrectionInterface.format_date_for_display(suggested_date)
        
        if original_ocr_date:
            message = (
                f"📅 <b>Invoice date correction</b>\n\n"
                f"OCR recognized: {original_ocr_date}\n"
                f"We suggest using: <b>{formatted_date}</b>\n\n"
            )
        else:
            message = (
                f"📅 <b>Invoice date not found</b>\n\n"
                f"We suggest using: <b>{formatted_date}</b>\n\n"
            )
        
        # Add confidence indicator
        if confidence == "high":
            message += "🎯 <i>High confidence in date accuracy</i>"
        elif confidence == "medium":
            message += "👍 <i>Medium confidence in date accuracy</i>"
        else:
            message += "🤔 <i>Low confidence - recommend verification</i>"
        
        return message

    @staticmethod
    def validate_date_correction(date_obj: date) -> Dict[str, Any]:
        """
        Validate corrected date for business logic.
        
        Args:
            date_obj: Date to validate
            
        Returns:
            Validation results
        """
        from app.validators.date_validator import DateValidator
        
        validator = DateValidator()
        return validator._validate_date_range(date_obj)


def generate_date_correction_suggestions(
    invoice_data: Dict[str, Any], 
    ocr_raw_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate comprehensive date correction suggestions for an invoice.
    
    Args:
        invoice_data: Invoice data from OCR
        ocr_raw_text: Raw OCR text for better date extraction
        
    Returns:
        Dictionary with correction suggestions and metadata
    """
    result = {
        "needs_correction": False,
        "suggestions": [],
        "current_date": None,
        "confidence": "unknown",
        "raw_ocr_date": None
    }
    
    # Check if date is missing or problematic
    invoice_date = invoice_data.get("date")
    
    if not invoice_date or invoice_date == "" or invoice_date is None:
        result["needs_correction"] = True
        result["confidence"] = "low"
        
        # Try to extract date from raw OCR text if available
        if ocr_raw_text:
            suggestions = DateCorrectionInterface.suggest_dates_from_ocr_text(ocr_raw_text)
            result["suggestions"] = suggestions
            result["raw_ocr_date"] = ocr_raw_text
        
        # Always suggest current date as fallback
        today = date.today()
        result["suggestions"].append({
            "date": today,
            "format": "Current date",
            "confidence": 0.9,
            "description": f"Current date: {today.strftime('%d.%m.%Y')}"
        })
    
    else:
        # Date exists, validate it
        try:
            if isinstance(invoice_date, str):
                parsed_date = DateCorrectionInterface.parse_manual_date_input(invoice_date)
            elif isinstance(invoice_date, date):
                parsed_date = invoice_date
            else:
                parsed_date = None
            
            if parsed_date:
                validation = DateCorrectionInterface.validate_date_correction(parsed_date)
                if not validation.get("valid", True) or validation.get("warnings"):
                    result["needs_correction"] = True
                    result["confidence"] = validation.get("confidence", "medium")
                    result["current_date"] = parsed_date
                    
                    # Suggest alternative dates
                    today = date.today()
                    result["suggestions"].append({
                        "date": today,
                        "format": "Current date",
                        "confidence": 0.9,
                        "description": f"Current date: {today.strftime('%d.%m.%Y')}"
                    })
            else:
                result["needs_correction"] = True
                result["confidence"] = "low"
        
        except Exception as e:
            logger.error(f"Error validating invoice date: {e}")
            result["needs_correction"] = True
            result["confidence"] = "low"
    
    return result