"""
Date validation module for invoice processing.

This module provides validation for invoice dates to ensure they are properly
extracted from OCR and reasonable for business use.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Union
from app.utils.data_utils import parse_date

logger = logging.getLogger(__name__)


class DateValidator:
    """
    Validates invoice dates for accuracy and business logic.
    
    Checks:
    1. Date presence and format
    2. Reasonable date ranges (not too far in past/future)
    3. Business day validation
    4. OCR date extraction issues
    """

    def __init__(self, 
                 max_days_past: int = 90,    # Max 3 months in past
                 max_days_future: int = 7,   # Max 1 week in future
                 warn_weekend: bool = False,  # Warn if invoice date is weekend
                 require_date: bool = True):  # Require date to be present
        """
        Initialize date validator.
        
        Args:
            max_days_past: Maximum days in the past to allow
            max_days_future: Maximum days in the future to allow
            warn_weekend: Whether to warn about weekend dates
            require_date: Whether to require date presence
        """
        self.max_days_past = max_days_past
        self.max_days_future = max_days_future
        self.warn_weekend = warn_weekend
        self.require_date = require_date

    def validate_invoice_date(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate invoice date from OCR data.
        
        Args:
            invoice_data: Invoice data dictionary
            
        Returns:
            Dictionary with validation results and any corrections
        """
        result = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "suggested_date": None,
            "confidence": "unknown",
            "fallback_used": False
        }
        
        # Extract date from various possible formats
        invoice_date = self._extract_date(invoice_data)
        
        if invoice_date is None:
            if self.require_date:
                result["valid"] = False
                result["errors"].append("Invoice date is missing or could not be extracted from OCR")
                result["suggested_date"] = date.today()
                result["fallback_used"] = True
                result["confidence"] = "low"
            else:
                result["warnings"].append("Invoice date not provided, will use current date")
                result["suggested_date"] = date.today()
                result["fallback_used"] = True
                result["confidence"] = "medium"
        else:
            # Validate the extracted date
            validation_result = self._validate_date_range(invoice_date)
            result.update(validation_result)
            
            # Additional business logic checks
            if self.warn_weekend and self._is_weekend(invoice_date):
                result["warnings"].append(f"Invoice date {invoice_date} is a weekend")
            
            # Check for suspicious date patterns
            self._check_suspicious_dates(invoice_date, result)
        
        return result

    def _extract_date(self, invoice_data: Dict[str, Any]) -> Optional[date]:
        """
        Extract date from invoice data in various formats.
        
        Args:
            invoice_data: Invoice data
            
        Returns:
            Extracted date or None if not found/invalid
        """
        # Try different field names
        date_fields = ["date", "invoice_date", "dateIncoming", "date_incoming"]
        
        for field in date_fields:
            date_value = invoice_data.get(field)
            if date_value:
                parsed_date = parse_date(date_value)
                if parsed_date:
                    return parsed_date
        
        # Try nested structures (positions, etc.)
        positions = invoice_data.get("positions", [])
        if positions and isinstance(positions, list) and len(positions) > 0:
            first_pos = positions[0]
            if isinstance(first_pos, dict):
                for field in date_fields:
                    date_value = first_pos.get(field)
                    if date_value:
                        parsed_date = parse_date(date_value)
                        if parsed_date:
                            return parsed_date
        
        return None


    def _validate_date_range(self, invoice_date: date) -> Dict[str, Any]:
        """
        Validate if date is within reasonable business range.
        
        Args:
            invoice_date: Date to validate
            
        Returns:
            Validation results
        """
        result = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "confidence": "high"
        }
        
        today = date.today()
        days_diff = (invoice_date - today).days
        
        # Check if too far in past
        if days_diff < -self.max_days_past:
            result["valid"] = False
            result["errors"].append(
                f"Invoice date {invoice_date} is too far in the past "
                f"({abs(days_diff)} days ago, max allowed: {self.max_days_past})"
            )
            result["confidence"] = "low"
        elif days_diff < -30:  # Warn if more than 30 days old
            result["warnings"].append(
                f"Invoice date {invoice_date} is {abs(days_diff)} days old"
            )
            result["confidence"] = "medium"
        
        # Check if too far in future
        if days_diff > self.max_days_future:
            result["valid"] = False
            result["errors"].append(
                f"Invoice date {invoice_date} is too far in the future "
                f"({days_diff} days ahead, max allowed: {self.max_days_future})"
            )
            result["confidence"] = "low"
        elif days_diff > 1:  # Warn if more than 1 day in future
            result["warnings"].append(
                f"Invoice date {invoice_date} is {days_diff} days in the future"
            )
            result["confidence"] = "medium"
        
        return result

    def _is_weekend(self, invoice_date: date) -> bool:
        """Check if date falls on weekend."""
        return invoice_date.weekday() >= 5  # Saturday=5, Sunday=6

    def _check_suspicious_dates(self, invoice_date: date, result: Dict[str, Any]) -> None:
        """
        Check for suspicious date patterns that might indicate OCR errors.
        
        Args:
            invoice_date: Date to check
            result: Result dictionary to update
        """
        # Check for obviously wrong years
        current_year = date.today().year
        if invoice_date.year < 2020 or invoice_date.year > current_year + 1:
            result["warnings"].append(
                f"Suspicious year in date: {invoice_date.year}. "
                f"OCR might have misread the date."
            )
            result["confidence"] = "low"
        
        # Check for suspicious day/month combinations
        if invoice_date.day > 28 and invoice_date.month == 2:
            # February with day > 28 is suspicious unless it's a leap year
            if not (invoice_date.year % 4 == 0 and (invoice_date.year % 100 != 0 or invoice_date.year % 400 == 0)):
                result["warnings"].append(
                    f"Suspicious date: February {invoice_date.day} in non-leap year {invoice_date.year}"
                )
                result["confidence"] = "low"
        
        # Check for obviously swapped day/month (common OCR error)
        if invoice_date.day <= 12 and invoice_date.month > 12:
            result["warnings"].append(
                "Date might have swapped day/month due to OCR error"
            )
            result["confidence"] = "low"


def validate_invoice_dates(invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to validate invoice dates.
    
    Args:
        invoice_data: Invoice data dictionary
        
    Returns:
        Enhanced invoice data with date validation results
    """
    validator = DateValidator()
    
    # Validate main invoice date
    date_validation = validator.validate_invoice_date(invoice_data)
    
    # Update invoice data
    result = invoice_data.copy()
    result["date_validation"] = date_validation
    
    # Add date validation warnings to overall validation
    if date_validation.get("warnings") or date_validation.get("errors"):
        existing_warnings = result.get("validation_warnings", [])
        
        # Add date-specific warnings
        for warning in date_validation.get("warnings", []):
            existing_warnings.append(f"Date: {warning}")
        
        for error in date_validation.get("errors", []):
            existing_warnings.append(f"Date Error: {error}")
        
        result["validation_warnings"] = existing_warnings
        
        # Mark as validation failed if there are errors
        if date_validation.get("errors"):
            result["validation_passed"] = False
    
    # If date is missing or invalid, suggest using current date
    if date_validation.get("fallback_used"):
        suggested_date = date_validation.get("suggested_date")
        if suggested_date:
            result["suggested_date"] = suggested_date.isoformat()
            
            # Add to validation warnings
            existing_warnings = result.get("validation_warnings", [])
            existing_warnings.append(
                f"Missing invoice date - suggest using {suggested_date.isoformat()} or manually correct"
            )
            result["validation_warnings"] = existing_warnings
    
    return result


class DateCorrectionHelper:
    """Helper class for date correction suggestions."""
    
    @staticmethod
    def suggest_date_corrections(date_str: str) -> List[Dict[str, Any]]:
        """
        Suggest possible date corrections for ambiguous or problematic dates.
        
        Args:
            date_str: Original date string from OCR
            
        Returns:
            List of possible date interpretations
        """
        suggestions = []
        
        if not date_str or not isinstance(date_str, str):
            return suggestions
        
        # Clean the string
        cleaned = date_str.strip()
        
        # Try to find number patterns
        import re
        numbers = re.findall(r'\d+', cleaned)
        
        if len(numbers) >= 3:
            # We have at least 3 numbers - try different interpretations
            num1, num2, num3 = map(int, numbers[:3])
            
            today = date.today()
            current_year = today.year
            
            # Try different year positions
            year_candidates = []
            for num in [num1, num2, num3]:
                if num > 31:  # Likely a year
                    year_candidates.append(num)
                elif num < 100:  # Two-digit year
                    if num <= 30:  # 2000s
                        year_candidates.append(2000 + num)
                    else:  # 1900s
                        year_candidates.append(1900 + num)
            
            if not year_candidates:
                # No obvious year, assume current year or nearby
                year_candidates = [current_year, current_year - 1]
            
            # Generate combinations
            for year in year_candidates:
                remaining_nums = [n for n in [num1, num2, num3] if n != year and n <= 31]
                
                if len(remaining_nums) >= 2:
                    day, month = remaining_nums[:2]
                    
                    # Try DD/MM/YYYY
                    if 1 <= day <= 31 and 1 <= month <= 12:
                        try:
                            suggested_date = date(year, month, day)
                            suggestions.append({
                                "date": suggested_date,
                                "format": "DD/MM/YYYY",
                                "confidence": 0.8,
                                "description": f"{day:02d}/{month:02d}/{year}"
                            })
                        except ValueError:
                            pass
                    
                    # Try MM/DD/YYYY
                    if 1 <= month <= 31 and 1 <= day <= 12:
                        try:
                            suggested_date = date(year, day, month)
                            suggestions.append({
                                "date": suggested_date,
                                "format": "MM/DD/YYYY",
                                "confidence": 0.7,
                                "description": f"{month:02d}/{day:02d}/{year}"
                            })
                        except ValueError:
                            pass
        
        # Remove duplicates and sort by confidence
        seen_dates = set()
        unique_suggestions = []
        
        for suggestion in suggestions:
            date_key = suggestion["date"].isoformat()
            if date_key not in seen_dates:
                seen_dates.add(date_key)
                unique_suggestions.append(suggestion)
        
        # Sort by confidence (highest first)
        unique_suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        
        return unique_suggestions[:3]  # Return top 3 suggestions