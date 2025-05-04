# Changelog

## [Unreleased]

### Added
- Comprehensive API error handling system with standardized decorators
  - Added `app/utils/api_decorators.py` module with error handling decorators
  - Implemented `with_retry_backoff` for synchronous API calls
  - Implemented `with_async_retry_backoff` for asynchronous API calls
  - Implemented `with_progress_stages` for multi-stage operations
  - Added error classification system with user-friendly messages
- Unit tests for API error handling in `tests/test_api_decorators.py`
- Documentation for API error handling in `docs/api_error_handling.md`

### Changed
- Refactored `ocr.py` to use new error handling decorators
- Refactored `bot.py` with improved error handling:
  - Updated `ask_assistant` function to use async retry decorator
  - Updated `photo_handler` to use progress stages decorator
  - Updated `handle_field_edit` to use async retry decorator
- Improved error reporting with more user-friendly messages
- Standardized retry logic with exponential backoff across all API calls

### Fixed
- Fixed potential infinite retry loops in API error handling
- Improved error context in error messages to better identify failing stages
- Enhanced validation error handling with clearer error messages