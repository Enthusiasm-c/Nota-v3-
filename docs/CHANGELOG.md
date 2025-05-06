# Changelog

## [2025-05-06] - Sprint C-5: GPT-3.5-turbo Dialogue Editing

### Added
- Robust GPT-3.5-turbo integration for natural language command processing
  - Created new module `app/assistants/client.py` for OpenAI Assistant API interaction
  - Implemented thread-safe execution with error handling and timeouts
  - Integrated with GPT-3.5-turbo for parsing commands in natural language
- Advanced intent adapter middleware
  - Created new module `app/assistants/intent_adapter.py` for normalizing API responses
  - Implemented field validation and format standardization
  - Added JSON extraction from text responses and recovery mechanisms
- Modular command processing architecture
  - Created module `app/edit/apply_intent.py` for applying intents to invoice data
  - Implemented functions `set_price`, `set_date`, `set_name` and others for applying changes
  - Built a system for processing and applying JSON intents from GPT
- Improved code organization with `app/handlers/edit_flow.py` for UI interactions
- Comprehensive test coverage for GPT-based editing:
  - Added `tests/test_free_edit_price.py` for price editing flow
  - Added `tests/test_free_edit_date.py` for date editing flow
  - Added `tests/test_apply_intent.py` for intent application logic
- Enhanced interactive UI
  - Added loading indicators during API requests
  - Implemented interactive fuzzy matching with confirmation buttons
  - Created user-friendly error messages for all failure scenarios
- Documentation and prompts
  - Added specialized prompts in `prompts/edit_assistant_v1.0.txt`
  - Created module documentation in `app/assistants/README.md`
  - Added detailed sprint changelog in `docs/SPRINT_C5_CHANGELOG.md`
  - Updated project overview in `docs/PROJECT_OVERVIEW.md`

### Changed
- Completely refactored editing UX
  - Replaced regex-based parsing with GPT-powered natural language understanding
  - Improved mobile UX with clearer feedback and confirmation flows
  - Streamlined editing process with AI-powered text commands
  - Updated interaction handlers for the GPT-assisted editing flow
- Enhanced error handling system for OpenAI API
  - Added specific error types for different failure scenarios
  - Improved handling of timeouts and network errors
  - Added user-friendly error messages for each error type
  - Implemented progressive fallback strategies
- Improved project architecture with clear separation of concerns:
  - UI logic ↔ Intent application logic ↔ External API calls ↔ Format adaptation

### Fixed
- Removed outdated code with per-line edit buttons
- Fixed FSM state management for more reliable editing
- Improved user messages during the editing process
- Added detailed logging for easier debugging
- Prevented application crashes during OpenAI API errors
- Implemented TDD methodology (tests → code → refactor)
- Normalized response formats for consistent handling

## [2025-05-04] - API Error Handling System

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