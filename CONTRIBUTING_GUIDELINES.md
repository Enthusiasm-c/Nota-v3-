# Contributing Guidelines

## 1. Code Structure

This project follows a specific structure to maintain clarity and organization. Please adhere to these guidelines when adding or modifying code.

### 1.1. Project Root Directory

*   **`app/`**: Contains all the core application logic.
    *   **`assistants/`**: Logic related to AI assistants (e.g., OpenAI Assistant API client, thread management).
    *   **`core/`**: Core functionalities like OCR processing (though `app/core/ocr.py` was removed as a stub, new core logic could reside here if general enough).
    *   **`config/`**: Configuration files and settings.
    *   **`detectors/`**: Modules for detecting elements in images (e.g., table detection).
    *   **`edit/`**: Logic related to editing invoice data.
    *   **`formatters/`**: Modules for formatting data for display or export (e.g., `report.py`).
    *   **`fsm/`**: Finite State Machine definitions for conversation flows.
    *   **`handlers/`**: Aiogram message and callback query handlers.
    *   **`i18n/`**: Internationalization and localization files (e.g., YAML translation files).
    *   **`imgprep/`**: Image preparation utilities for OCR.
    *   **`keyboards/`**: Functions for generating UI keyboards for the bot. (Now `app/keyboards.py`)
    *   **`models/`**: Pydantic models for data structures.
    *   **`ocr_helpers/`**: Helper functions for the OCR pipeline.
    *   **`parsers/`**: Parsers for various data formats or user input.
    *   **`scripts/`**: Utility scripts related to the application, not part of the main bot logic.
    *   **`services/`**: Clients for interacting with external services (e.g., Syrve).
    *   **`utils/`**: General utility functions used across the application.
    *   **`validators/`**: Data validation logic.
    *   **`main.py` / `bot.py`**: Main application entry point (or similar).
*   **`tests/`**: Contains all automated tests.
    *   **`unit/`**: Unit tests for individual modules and functions. (Assuming this structure, if not present, recommend it)
    *   **`integration/`**: Integration tests for interactions between modules. (Assuming this structure)
    *   **`e2e/`**: End-to-end tests for full application flows.
*   **`scripts/`**: Standalone scripts for various tasks (e.g., deployment, maintenance, one-off tasks). (Note: There's also an `app/scripts/`, clarify if one is preferred or if they serve different purposes. Assuming root `scripts/` is for operational/dev tasks).
*   **`docs/`**: Project documentation.
*   **`prompts/`**: Prompt templates for AI models.
*   **`requirements.txt`**: Python package dependencies.
*   **`Dockerfile` / `docker-compose.yml`**: Files for Docker containerization.
*   **`.gitignore`**: Specifies intentionally untracked files that Git should ignore.
*   **`CONTRIBUTING_GUIDELINES.md`**: This file.

### 1.2. Module and File Organization

*   **Keep related logic together:** Group functions and classes that serve a common purpose within the same module (Python file).
*   **Clear Naming:**
    *   **Files:** Use lowercase with underscores for readability (e.g., `ocr_pipeline_optimized.py`, `user_handlers.py`).
    *   **Classes:** Use CamelCase (e.g., `OCRPipelineOptimized`, `InvoiceReviewStates`).
    *   **Functions and Variables:** Use lowercase with underscores (e.g., `process_image`, `user_input`).
*   **Handlers (`app/handlers/`):** Organize handlers by functionality or conversation flow if the number of handlers grows. For example, `invoice_handlers.py`, `user_management_handlers.py`.
*   **Utils (`app/utils/`):** Create specific utility modules if a set of helper functions is large and cohesive (e.g., `image_utils.py`, `text_processing_utils.py`) rather than putting everything into one large utils file.

### 1.3. General Principles

*   **Modularity:** Design components to be as modular and reusable as possible.
*   **Single Responsibility Principle (SRP):** Functions and classes should ideally have one primary responsibility.
*   **Readability:** Write clear, understandable code. Add comments where necessary to explain complex logic, but prioritize self-documenting code.
*   **Consistency:** Follow the existing code style and patterns within the project.

## 2. Technological Stack

This project utilizes the following core technologies:

*   **Programming Language:**
    *   Python 3.9+

*   **Main Frameworks & Libraries:**
    *   **Aiogram:** Asynchronous framework for Telegram Bot API.
    *   **Pydantic:** Data validation and settings management.
    *   **OpenAI Python SDK:** For interacting with OpenAI APIs (GPT models for assistance, OCR - Vision API).
    *   **PaddleOCR:** For table detection and optical character recognition.
    *   **NumPy:** For numerical operations, particularly with images.
    *   **Pillow (PIL):** For image manipulation.

*   **Databases & Caching:**
    *   **Redis:** Used for caching OCR results, assistant threads, and potentially other temporary data. (Specific use should be confirmed by checking environment variable usage or Redis client instantiation).

*   **Development & Operations:**
    *   **Docker & Docker Compose:** For containerization and consistent deployment environments.
    *   **Git & GitHub:** For version control and collaboration.
    *   **requirements.txt:** Manages Python dependencies. Ensure this file is kept up-to-date.

*   **IDE (Recommended):**
    *   **Cursor IDE:** While development can be done in any editor, these guidelines are tailored to facilitate work within Cursor IDE.

## 3. New Modules and Logic Duplication

To maintain code quality, prevent architectural drift, and ensure consistency, the following rules apply to the creation of new modules and the handling of existing logic:

### 3.1. Creating New Modules

*   **Prior Approval Required:** Before creating any new module (e.g., a new Python file `.py` intended to introduce a distinct set of functionalities, classes, or utilities), you **must** obtain explicit approval from the project maintainer(s) (User: denisdomashenko).
*   **Justification:** Prepare a brief justification for the new module, explaining:
    *   The problem it solves or the functionality it introduces.
    *   Why existing modules cannot accommodate this new logic.
    *   How it fits into the overall project architecture.
*   **Scope Definition:** Clearly define the scope and responsibilities of the proposed module.

### 3.2. Avoiding Logic Duplication

*   **Strict Prohibition:** Duplicating existing logic from other parts of the project is strictly prohibited without explicit prior authorization.
*   **Search First:** Before writing new code, thoroughly search the existing codebase (especially `app/utils/`, `app/ocr_helpers/`, and other relevant directories) to find functions or classes that might already provide the needed functionality.
*   **Refactor for Reusability:**
    *   If existing logic is similar but needs modification to suit a new use case, discuss with the project maintainer(s) about refactoring the existing code to make it more general and reusable.
    *   Do not copy-paste and modify. Instead, enhance the original module/function if feasible.
*   **Centralize Common Utilities:** Common helper functions that are applicable across multiple parts of the application should be placed in appropriate utility modules (e.g., under `app/utils/`) to promote reuse.

### 3.3. Refactoring Existing Logic

*   **Minor Refactorings:** Minor refactorings that improve clarity, performance, or maintainability of a specific piece of code you are working on are encouraged.
*   **Significant Refactorings:** If you plan a significant refactoring that might affect multiple components, change existing APIs, or alter core behavior, this must be discussed and approved by the project maintainer(s) beforehand.

## 4. Cursor IDE Guidelines

While these guidelines are generally applicable, working with Cursor IDE can be enhanced by following these practices:

*   **Leverage AI Features Responsibly:**
    *   Use Cursor's AI features (e.g., "Chat with code", "Generate code", "Edit with AI") to assist in understanding, generating, or refactoring code.
    *   **Critically review all AI-generated code.** Do not accept suggestions blindly. Ensure they align with the project's standards, logic, and the guidelines mentioned in this document.
    *   Prioritize clarity and maintainability over overly complex or obscure code, even if suggested by AI.

*   **Code Navigation and Understanding:**
    *   Utilize features like "Go to Definition", "Find Usages", and symbol search to understand existing code before making changes. This helps in identifying reusable components and avoiding duplication.

*   **Version Control Integration:**
    *   Use Cursor's built-in Git integration for committing changes. Write clear and descriptive commit messages.
    *   Keep your local branch up-to-date with the main repository to avoid merge conflicts.

*   **Linting and Formatting:**
    *   Ensure that appropriate linters (e.g., Flake8, Pylint) and formatters (e.g., Black, Ruff) are configured and used, either through Cursor's settings or project-level configurations (like `pyproject.toml` if used). This helps maintain code consistency.
    *   Format your code before committing.

*   **Workspace Configuration:**
    *   If there are project-specific settings or recommended extensions for Cursor IDE that benefit the team, document them here or in a `.vscode/settings.json` file (if applicable and sharable).

*   **Respect Project Structure:**
    *   When creating new files or folders (after approval, as per Section 3.1), do so in a way that respects the established project structure outlined in Section 1.
