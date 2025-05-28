"""
Validation pipeline for invoice data.
"""

import logging
from typing import Any, Dict, List

from .arithmetic_validator import ArithmeticValidator
from .context_validator import validate_prices_with_context
from .date_validator import validate_invoice_dates

logger = logging.getLogger(__name__)


class ValidationPipeline:
    """
    Pipeline for validating invoice data.
    Checks arithmetic consistency and business rules.
    """

    def __init__(self, arithmetic_tolerance: float = 0.02, auto_fix: bool = True):
        """
        Initialize validation pipeline.
        
        Args:
            arithmetic_tolerance: Tolerance for arithmetic validation (default 2%)
            auto_fix: Whether to automatically fix detected errors
        """
        self.arithmetic_validator = ArithmeticValidator(
            tolerance=arithmetic_tolerance, 
            auto_fix=auto_fix
        )
        self.validators = [self.arithmetic_validator]

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate invoice data through multiple validation stages.

        Args:
            data: Invoice data to validate

        Returns:
            Validated data with validation results and any fixes applied
        """
        if data is None:
            return {
                "status": "error",
                "issues": ["Input data is None"],
                "validated": False,
                "validation_passed": False
            }

        # Convert to dict if it's a Pydantic model
        if hasattr(data, 'model_dump'):
            data_dict = data.model_dump()
        elif hasattr(data, 'dict'):
            data_dict = data.dict()
        else:
            data_dict = data.copy() if isinstance(data, dict) else {}

        # Initialize result structure
        result = data_dict.copy()
        all_issues = []
        validation_status = "success"

        # Run all validators
        for validator in self.validators:
            try:
                validator_result = validator.validate(data_dict)
                
                # Update data with any fixes from validator
                if "lines" in validator_result:
                    result["lines"] = validator_result["lines"]
                if "positions" in validator_result:
                    result["positions"] = validator_result["positions"]
                
                # Collect issues
                validator_issues = validator_result.get("issues", [])
                all_issues.extend(validator_issues)
                
                # Determine overall status (error > warning > success)
                for issue in validator_issues:
                    if issue.get("severity") == "error":
                        validation_status = "error"
                    elif issue.get("severity") == "warning" and validation_status != "error":
                        validation_status = "warning"
                        
            except Exception as e:
                logger.error(f"Validator {type(validator).__name__} failed: {str(e)}")
                all_issues.append({
                    "type": "VALIDATOR_ERROR",
                    "message": f"Exception in {type(validator).__name__}: {str(e)}",
                    "severity": "error"
                })
                validation_status = "error"

        # Apply context-aware price validation
        try:
            result = validate_prices_with_context(result)
        except Exception as e:
            logger.error(f"Context validation failed: {str(e)}")
            all_issues.append({
                "type": "CONTEXT_VALIDATION_ERROR",
                "message": f"Context validation error: {str(e)}",
                "severity": "warning"
            })

        # Apply date validation
        try:
            result = validate_invoice_dates(result)
        except Exception as e:
            logger.error(f"Date validation failed: {str(e)}")
            all_issues.append({
                "type": "DATE_VALIDATION_ERROR",
                "message": f"Date validation error: {str(e)}",
                "severity": "warning"
            })

        # Add validation metadata
        result.update({
            "status": validation_status,
            "issues": all_issues,
            "validated": True,
            "validation_passed": validation_status in ["success", "warning"] and result.get("validation_passed", True)
        })

        return result
