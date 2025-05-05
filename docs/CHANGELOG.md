# Changelog

## [Unreleased]

### Added
- Single-button editing with simplified UX
  - Added `build_main_kb` function in `app/keyboards.py` for cleaner UI
  - Implemented free-form text command editing
  - Added `handle_free_edit_text` handler for processing edit commands
  - Intelligent fuzzy name matching with 82% threshold
  - Confirmation flow for suggested product names
  - Self-learning aliases with automatic storage
- New FSM states in `app/fsm/states.py` for free-form editing
- Comprehensive test coverage for new editing UX
  - Added `tests/test_keyboard_main_edit.py` for keyboard layout testing
  - Added `tests/test_fuzzy_confirm.py` for fuzzy matching confirmation
- Updated documentation in README.md and PROJECT_OVERVIEW.md

### Changed
- Completely refactored editing UX
  - Replaced per-line edit buttons with single main edit button
  - Improved mobile UX by reducing button clutter
  - Streamlined editing process with text commands
  - Updated `cb_edit_line` handler for new editing flow
- Enhanced editing workflow with improved error handling
- Updated keyboard generation to use the new simplified format

### Fixed
- Removed legacy code with per-line edit buttons to clean up UI
- Fixed edit mode state management for more reliable editing
- Improved user feedback during editing process
- Enhanced error context in error messages to better identify failing stages

## [2025-05-04]

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