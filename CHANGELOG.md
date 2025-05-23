# CHANGELOG

## [0.6.0] - 2024-05-14

### Changed
- Refactored OCR pipeline for better testability while preserving functionality
- Extracted helper functions to `app/ocr_helpers.py` module with proper type hints
- Improved organization of code with clearer method boundaries and responsibilities

### Added
- Increased overall test coverage from ~63% to ≥75%
- Added property-based tests for the matcher module using Hypothesis
- Added integration tests for complex table layouts with merged cells
- Added tests for Vision-only fallback when PaddleOCR is disabled
- New test cases for edge cases in OCR processing

### Fixed
- Fixed failing unit tests for OCR pipeline
- Resolved issues with testing nested functions
- Improved error handling in OCR cell processing
- Enhanced test mocking approach for more reliable tests