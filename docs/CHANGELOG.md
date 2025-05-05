# Changelog

## [Unreleased]

### Added
- GPT-3.5-turbo интеграция для интеллектуального разбора команд редактирования
  - Добавлен модуль `app/assistants/client.py` для взаимодействия с OpenAI API
  - Реализован безопасный запуск Thread с обработкой ошибок и таймаутом
  - Интеграция с GPT-3.5-turbo для разбора команд на естественном языке
- Новая архитектура редактирования с модульной структурой
  - Добавлен модуль `app/edit/apply_intent.py` для применения интентов к инвойсу
  - Реализованы функции `set_price`, `set_date`, `set_name` и другие для применения изменений
  - Система обработки и применения JSON-интентов от GPT
- Улучшенная организация кода с новым модулем `app/handlers/edit_flow.py`
- Comprehensive test coverage for new editing with GPT:
  - Added `tests/test_free_edit_price.py` for price editing flow
  - Added `tests/test_free_edit_date.py` for date editing flow
  - Added `tests/test_apply_intent.py` for intent application logic
- Single-button editing with simplified UX
  - Added `build_main_kb` function in `app/keyboards.py` for cleaner UI
  - Implemented free-form text command editing
  - Intelligent parsing with GPT-3.5-turbo
- New FSM states in `app/fsm/states.py` for free-form editing
- Updated documentation in README.md and PROJECT_OVERVIEW.md
- Added detailed test plan in TEST_PLAN.md

### Changed
- Completely refactored editing UX
  - Replaced per-line edit buttons with single main edit button
  - Improved mobile UX by reducing button clutter
  - Streamlined editing process with AI-powered text commands
  - Updated `cb_edit_line` handler for GPT-assisted editing flow
- Enhanced error handling system for OpenAI API взаимодействия
  - Добавлена функция `count_issues` для автоматического подсчёта ошибок
  - Улучшена обработка таймаутов и сетевых ошибок
- Updated keyboard generation to use the new simplified format
- Улучшена архитектура проекта с чётким разделением ответственностей
  - Логика обработки сообщений ↔ логика применения изменений ↔ вызов внешних API

### Fixed
- Удалён устаревший код с кнопками редактирования каждой строки
- Исправлена обработка состояний FSM для более надёжного редактирования
- Улучшены сообщения для пользователя во время процесса редактирования
- Добавлена дополнительная информация в логи для облегчения отладки
- Предотвращено падение приложения при ошибках OpenAI API
- Реализована TDD-методология разработки (тесты → код → тесты)

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