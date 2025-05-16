# CHANGELOG

## [0.6.0] - 2024-05-14

### Changed
- Refactored OCR pipeline for better testability while preserving functionality
- Extracted helper functions to `app/ocr_helpers.py` module with proper type hints
- Improved organization of code with clearer method boundaries and responsibilities
- Updated model Position: added fields for price validation (price_mismatch, mismatch_type, expected_total)
- Updated report format: added price mismatch display
- Updated post-processing data OCR for price validation

### Added
- Increased overall test coverage from ~63% to ≥75%
- Added property-based tests for the matcher module using Hypothesis
- Added integration tests for complex table layouts with merged cells
- Added tests for Vision-only fallback when PaddleOCR is disabled
- New test cases for edge cases in OCR processing
- Added price validation in invoices:
  - Automatic check for price consistency between unit price, quantity, and total amount
  - Visual highlighting of discrepancies in the report (symbol 💰)
  - Displaying expected values for incorrect sums
  - Added tests for new functionality

### Fixed
- Fixed failing unit tests for OCR pipeline
- Resolved issues with testing nested functions
- Improved error handling in OCR cell processing
- Enhanced test mocking approach for more reliable tests
- Fixed status display in report
- Improved price comparison error handling