"""
OCR Pre-validation module for early detection of arithmetic inconsistencies.

This module provides validation logic that can be applied immediately after OCR
to catch obvious mathematical errors before further processing.
"""

import logging
from typing import Any, Dict, List, Optional
from app.utils.data_utils import clean_number

logger = logging.getLogger(__name__)


class OCRPreValidator:
    """
    Pre-validator for OCR results to catch mathematical inconsistencies early.
    
    This validator focuses on:
    1. Basic arithmetic validation (qty × price = total_price)
    2. Order of magnitude checks
    3. Typical price range validation for Indonesian market
    4. Format consistency checks
    """

    def __init__(self, 
                 tolerance: float = 0.05,  # 5% tolerance for arithmetic checks
                 min_unit_price: float = 500,  # Minimum reasonable unit price in IDR
                 max_unit_price: float = 1_000_000,  # Maximum reasonable unit price in IDR
                 min_total_invoice: float = 10_000,  # Minimum reasonable total invoice
                 max_total_invoice: float = 10_000_000):  # Maximum reasonable total invoice
        """
        Initialize OCR pre-validator.
        
        Args:
            tolerance: Allowable percentage difference for arithmetic validation
            min_unit_price: Minimum reasonable unit price in IDR
            max_unit_price: Maximum reasonable unit price in IDR
            min_total_invoice: Minimum reasonable total invoice amount
            max_total_invoice: Maximum reasonable total invoice amount
        """
        self.tolerance = tolerance
        self.min_unit_price = min_unit_price
        self.max_unit_price = max_unit_price
        self.min_total_invoice = min_total_invoice
        self.max_total_invoice = max_total_invoice

    def validate_positions(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate individual positions for arithmetic consistency and reasonable values.
        
        Args:
            positions: List of position dictionaries from OCR
            
        Returns:
            List of positions with validation warnings added where appropriate
        """
        validated_positions = []
        
        for i, pos in enumerate(positions):
            validated_pos = pos.copy()
            warnings = []
            
            # Extract values with safe conversion
            qty = clean_number(pos.get('qty', 0))
            price = clean_number(pos.get('price', 0))
            total_price = clean_number(pos.get('total_price', 0))
            
            # Skip validation if critical values are missing
            if not qty or not price:
                warnings.append("Missing quantity or price - cannot validate")
                validated_pos['validation_warnings'] = warnings
                validated_positions.append(validated_pos)
                continue
            
            # 1. Arithmetic validation
            expected_total = qty * price
            if total_price > 0:
                relative_error = abs(expected_total - total_price) / max(expected_total, total_price)
                if relative_error > self.tolerance:
                    warnings.append(
                        f"Math error: {qty} × {price} = {expected_total:.0f}, "
                        f"but total_price = {total_price:.0f} "
                        f"(error: {relative_error*100:.1f}%)"
                    )
            else:
                # Auto-calculate if total_price is missing
                validated_pos['total_price'] = expected_total
                warnings.append(f"Calculated missing total_price: {expected_total:.0f}")
            
            # 2. Price range validation
            if price < self.min_unit_price:
                warnings.append(
                    f"Suspiciously low price: {price:.0f} IDR "
                    f"(< {self.min_unit_price:.0f}) - possible OCR error"
                )
            elif price > self.max_unit_price:
                warnings.append(
                    f"Suspiciously high price: {price:.0f} IDR "
                    f"(> {self.max_unit_price:.0f}) - possible OCR error"
                )
            
            # 3. Quantity validation
            if qty <= 0:
                warnings.append(f"Invalid quantity: {qty}")
            elif qty > 1000:  # Unlikely to order more than 1000 of anything
                warnings.append(f"Unusually large quantity: {qty} - possible OCR error")
            
            # 4. Check for common OCR errors in numbers
            self._check_common_ocr_errors(pos, warnings)
            
            # Add warnings to position
            if warnings:
                validated_pos['validation_warnings'] = warnings
                logger.warning(f"Position {i+1} ({pos.get('name', 'unknown')}): {'; '.join(warnings)}")
            
            validated_positions.append(validated_pos)
        
        return validated_positions

    def validate_invoice_total(self, positions: List[Dict[str, Any]], 
                             total_price: Optional[float]) -> Dict[str, Any]:
        """
        Validate the total invoice amount against sum of positions.
        
        Args:
            positions: List of validated positions
            total_price: Total invoice amount from OCR
            
        Returns:
            Dictionary with validation results and any corrections
        """
        result = {
            'total_price': total_price,
            'warnings': [],
            'calculated_total': 0.0,
            'validation_passed': True
        }
        
        # Calculate expected total from positions
        calculated_total = 0.0
        for pos in positions:
            pos_total = clean_number(pos.get('total_price', 0))
            calculated_total += pos_total
        
        result['calculated_total'] = calculated_total
        
        # Validate against provided total
        if total_price and total_price > 0:
            relative_error = abs(calculated_total - total_price) / max(calculated_total, total_price)
            if relative_error > self.tolerance:
                result['warnings'].append(
                    f"Invoice total mismatch: sum of positions = {calculated_total:.0f}, "
                    f"but total_price = {total_price:.0f} (error: {relative_error*100:.1f}%)"
                )
                result['validation_passed'] = False
        else:
            # Use calculated total if invoice total is missing
            result['total_price'] = calculated_total
            result['warnings'].append(f"Calculated missing invoice total: {calculated_total:.0f}")
        
        # Sanity check on total amount
        final_total = result['total_price']
        if final_total < self.min_total_invoice:
            result['warnings'].append(
                f"Suspiciously low invoice total: {final_total:.0f} IDR "
                f"(< {self.min_total_invoice:.0f})"
            )
        elif final_total > self.max_total_invoice:
            result['warnings'].append(
                f"Suspiciously high invoice total: {final_total:.0f} IDR "
                f"(> {self.max_total_invoice:.0f})"
            )
        
        if result['warnings']:
            logger.warning(f"Invoice total validation: {'; '.join(result['warnings'])}")
        
        return result


    def _check_common_ocr_errors(self, position: Dict[str, Any], warnings: List[str]) -> None:
        """
        Check for common OCR errors in numeric values.
        
        Args:
            position: Position dictionary
            warnings: List to append warnings to
        """
        # Check if price looks like it might have decimal point error
        price = clean_number(position.get('price', 0))
        qty = clean_number(position.get('qty', 0))
        
        # Check for suspiciously round numbers that might indicate OCR errors
        if price > 0:
            # If price is suspiciously round (like 10000, 20000), might be missing decimal
            if price >= 10000 and price % 1000 == 0:
                # Check if dividing by 100 or 1000 gives more reasonable price
                reasonable_price_100 = price / 100
                reasonable_price_1000 = price / 1000
                
                if self.min_unit_price <= reasonable_price_100 <= self.max_unit_price:
                    warnings.append(
                        f"Price {price:.0f} might be missing decimal point - "
                        f"consider {reasonable_price_100:.0f}"
                    )
                elif self.min_unit_price <= reasonable_price_1000 <= self.max_unit_price:
                    warnings.append(
                        f"Price {price:.0f} might have extra zeros - "
                        f"consider {reasonable_price_1000:.0f}"
                    )
        
        # Check quantity for obvious errors
        if qty > 0:
            # Very large quantities might indicate decimal point errors
            if qty > 100:
                warnings.append(f"Large quantity {qty} - verify this is correct")
            
            # Check if quantity has suspicious precision (like 1.000000)
            if isinstance(position.get('qty'), str):
                qty_str = position.get('qty', '')
                if '.' in qty_str and len(qty_str.split('.')[-1]) > 3:
                    warnings.append(f"Quantity {qty_str} has unusual precision - possible OCR error")


def validate_ocr_result(ocr_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to validate complete OCR result.
    
    Args:
        ocr_data: OCR result dictionary
        
    Returns:
        Validated OCR data with warnings and corrections
    """
    validator = OCRPreValidator()
    
    # Validate positions
    positions = ocr_data.get('positions', [])
    validated_positions = validator.validate_positions(positions)
    
    # Validate invoice total
    total_validation = validator.validate_invoice_total(
        validated_positions,
        ocr_data.get('total_price')
    )
    
    # Combine results
    result = ocr_data.copy()
    result['positions'] = validated_positions
    result['total_price'] = total_validation['total_price']
    
    # Collect all warnings
    all_warnings = total_validation['warnings'].copy()
    for pos in validated_positions:
        pos_warnings = pos.get('validation_warnings', [])
        all_warnings.extend([f"{pos.get('name', 'unknown')}: {w}" for w in pos_warnings])
    
    result['validation_warnings'] = all_warnings
    result['validation_passed'] = total_validation['validation_passed'] and len(all_warnings) == 0
    
    return result