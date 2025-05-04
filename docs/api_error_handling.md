# API Error Handling in Nota-v3

This document describes the standardized approach to API error handling implemented in Nota-v3.

## Table of Contents
- [Overview](#overview)
- [Decorators and Utilities](#decorators-and-utilities)
- [Usage Examples](#usage-examples)
- [Error Classification](#error-classification)
- [Benefits](#benefits)

## Overview

The Nota-v3 bot communicates with multiple external APIs (mainly OpenAI's Vision and Assistant APIs) that may fail for various reasons:
- Network issues
- Rate limiting
- Server errors
- Authentication problems
- Timeouts
- Validation errors

To handle these errors consistently across the codebase, we've implemented a decorator-based approach that standardizes:
- Error classification
- Retry logic with exponential backoff
- User-friendly error messages
- Progress tracking for multi-stage operations

## Decorators and Utilities

The following components have been implemented in `app/utils/api_decorators.py`:

1. **ErrorType** - Enumeration of standardized error categories:
   - `TIMEOUT`: Request timeouts
   - `RATE_LIMIT`: API rate limiting
   - `VALIDATION`: Invalid request format
   - `AUTHENTICATION`: Authentication errors
   - `SERVER`: Server-side errors
   - `CLIENT`: Client-side errors
   - `NETWORK`: Network connectivity issues
   - `UNKNOWN`: Other unexpected errors

2. **with_retry_backoff** - Decorator for synchronous functions that adds retry logic with exponential backoff.

3. **with_async_retry_backoff** - Decorator for asynchronous functions that adds retry logic with exponential backoff.

4. **with_progress_stages** - Decorator for tracking multi-stage processes and providing user feedback.

5. **update_stage** - Utility for updating the progress of a multi-stage operation.

6. **classify_error** - Utility function that categorizes errors and generates user-friendly messages.

## Usage Examples

### Synchronous API Call with Retries

```python
from app.utils.api_decorators import with_retry_backoff

@with_retry_backoff(max_retries=3, initial_backoff=1.0, backoff_factor=2.0)
def call_ocr_api(image_bytes):
    """
    Calls the OCR API with automatic retries and error handling.
    Will retry up to 3 times with exponential backoff.
    """
    client = get_api_client()
    response = client.process_image(image_bytes)
    return response.data
```

### Asynchronous API Call with Retries

```python
from app.utils.api_decorators import with_async_retry_backoff

@with_async_retry_backoff(max_retries=2, initial_backoff=1.0, backoff_factor=2.0)
async def send_message_to_assistant(thread_id, message):
    """
    Sends a message to the assistant API with automatic retries and error handling.
    Will retry up to 2 times with exponential backoff.
    """
    client = get_assistant_client()
    response = await client.send_message(thread_id, message)
    return response.content
```

### Multi-stage Operation with Progress Tracking

```python
from app.utils.api_decorators import with_progress_stages, update_stage

# Define stages with user-friendly descriptions
STAGES = {
    "download": "Downloading image",
    "ocr": "Processing with OCR",
    "matching": "Matching products",
    "report": "Generating report"
}

@with_progress_stages(stages=STAGES)
async def process_invoice(image, **kwargs):
    """
    Process an invoice image through multiple stages.
    Shows progress to the user and provides targeted error messages.
    """
    # Stage 1: Download
    image_data = await download_image(image)
    update_stage("download", kwargs)
    
    # Stage 2: OCR
    text_data = await ocr_service.extract_text(image_data)
    update_stage("ocr", kwargs)
    
    # Stage 3: Matching
    products = match_products(text_data)
    update_stage("matching", kwargs)
    
    # Stage 4: Report
    report = generate_report(products)
    update_stage("report", kwargs)
    
    return report
```

## Error Classification

Errors are classified into categories to provide consistent handling:

| Category | Examples | Default Behavior |
|----------|----------|-----------------|
| TIMEOUT | Request timeouts, slow responses | Retry with small delay |
| RATE_LIMIT | Too many requests, quota exceeded | Retry with exponential backoff |
| VALIDATION | Invalid inputs, wrong format | Do not retry |
| AUTHENTICATION | Invalid API keys, expired tokens | Do not retry |
| SERVER | 5xx errors, service unavailable | Retry with delay |
| CLIENT | 4xx errors, bad requests | Depends on specific error |
| NETWORK | Connection issues, DNS failures | Retry with delay |
| UNKNOWN | Unexpected errors | Retry once |

## Benefits

This standardized approach provides several benefits:

1. **Consistency**: Error handling is consistent across all API calls
2. **Reliability**: Retries with backoff increase success rates for transient errors
3. **User Experience**: Friendly error messages based on error type
4. **Development**: Reduced code duplication and boilerplate
5. **Maintenance**: Centralized error handling logic is easier to update

The implementation reduces the chances of API calls failing due to transient issues and improves the overall user experience by providing meaningful error messages.