"""Tests for app/assistants/client.py"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import json
import asyncio
from datetime import datetime

from app.assistants.client import (
    EditCommand, 
    parse_assistant_output,
    run_thread_safe_async,
    retry_openai_call,
    normalize_query_for_cache,
    adapt_cached_intent,
    parse_edit_command
)


class TestEditCommand:
    """Test EditCommand model validation"""
    
    def test_valid_edit_command(self):
        """Test creating valid EditCommand"""
        cmd = EditCommand(
            action="set_name",
            row=1,
            name="Test Product"
        )
        assert cmd.action == "set_name"
        assert cmd.row == 1
        assert cmd.name == "Test Product"
    
    def test_edit_command_requires_row_for_certain_actions(self):
        """Test that certain actions require row field"""
        # These actions require row
        actions_with_row = ["set_name", "set_qty", "set_unit", "set_price", "set_price_per_unit", "set_total_price"]
        
        for action in actions_with_row:
            # Should fail without row
            with pytest.raises(ValueError):
                EditCommand(action=action, name="Test")
            
            # Should fail with row < 1
            with pytest.raises(ValueError):
                EditCommand(action=action, row=0, name="Test")
            
            # Should succeed with valid row
            cmd = EditCommand(action=action, row=1, name="Test")
            assert cmd.row == 1
    
    def test_edit_command_optional_row_for_other_actions(self):
        """Test that other actions don't require row"""
        # These actions don't require row
        actions_without_row = ["set_date", "set_supplier", "delete_row", "add_row"]
        
        for action in actions_without_row:
            # Should succeed without row
            cmd = EditCommand(action=action, date="2024-01-01")
            assert cmd.row is None
    
    def test_edit_command_with_numeric_fields(self):
        """Test EditCommand with numeric fields"""
        cmd = EditCommand(
            action="set_qty",
            row=1,
            qty=10.5
        )
        assert cmd.qty == 10.5
        
        # Test with string numbers
        cmd = EditCommand(
            action="set_price",
            row=1,
            price="100.50"
        )
        assert cmd.price == "100.50"


class TestParseAssistantOutput:
    """Test parse_assistant_output function"""
    
    def test_parse_valid_json_output(self):
        """Test parsing valid JSON from assistant"""
        output = '{"commands": [{"action": "set_name", "row": 1, "name": "Test"}]}'
        result = parse_assistant_output(output)
        assert len(result) == 1
        assert result[0]["action"] == "set_name"
        assert result[0]["row"] == 1
        assert result[0]["name"] == "Test"
    
    def test_parse_json_with_text_around(self):
        """Test parsing JSON with surrounding text"""
        output = '''Here is the result:
        ```json
        {"commands": [{"action": "set_qty", "row": 2, "qty": 5}]}
        ```
        Done processing.'''
        result = parse_assistant_output(output)
        assert len(result) == 1
        assert result[0]["action"] == "set_qty"
        assert result[0]["qty"] == 5
    
    def test_parse_multiple_commands(self):
        """Test parsing multiple commands"""
        output = '''{
            "commands": [
                {"action": "set_name", "row": 1, "name": "Product A"},
                {"action": "set_qty", "row": 1, "qty": 10},
                {"action": "set_price", "row": 1, "price": 100}
            ]
        }'''
        result = parse_assistant_output(output)
        assert len(result) == 3
        assert result[0]["action"] == "set_name"
        assert result[1]["action"] == "set_qty"
        assert result[2]["action"] == "set_price"
    
    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty list"""
        output = "This is not JSON"
        result = parse_assistant_output(output)
        assert result == []
    
    def test_parse_json_without_commands_key(self):
        """Test parsing JSON without 'commands' key"""
        output = '{"action": "set_name", "row": 1, "name": "Test"}'
        result = parse_assistant_output(output)
        assert result == []
    
    def test_parse_empty_commands(self):
        """Test parsing empty commands array"""
        output = '{"commands": []}'
        result = parse_assistant_output(output)
        assert result == []


class TestParseEditCommand:
    """Test deprecated parse_edit_command function"""
    
    def test_deprecation_warning(self):
        """Test that function raises deprecation warning"""
        with pytest.warns(DeprecationWarning):
            parse_edit_command("test command")
    
    def test_empty_input(self):
        """Test empty input returns empty list"""
        with pytest.warns(DeprecationWarning):
            result = parse_edit_command("")
            assert result == []
            
            result = parse_edit_command("   ")
            assert result == []
    
    def test_typo_detection(self):
        """Test typo detection in commands"""
        with pytest.warns(DeprecationWarning):
            result = parse_edit_command("поставщиик Test")
            assert result == []
    
    def test_known_test_pattern(self):
        """Test known test pattern handling"""
        with pytest.warns(DeprecationWarning):
            result = parse_edit_command("строка 1 количество пять")
            assert len(result) == 1
            assert result[0]["action"] == "unknown"
            assert result[0]["error"] == "invalid_line_or_qty"


class TestRetryOpenAICall:
    """Test retry_openai_call function"""
    
    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Test successful API call without retries"""
        mock_func = AsyncMock(return_value="success")
        
        result = await retry_openai_call(mock_func, max_retries=3)
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self):
        """Test retry on rate limit error"""
        mock_func = AsyncMock()
        mock_func.side_effect = [
            Exception("Rate limit exceeded"),
            Exception("Rate limit exceeded"),
            "success"
        ]
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await retry_openai_call(mock_func, max_retries=3)
        
        assert result == "success"
        assert mock_func.call_count == 3
    
    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test max retries exceeded"""
        mock_func = AsyncMock()
        mock_func.side_effect = Exception("Rate limit exceeded")
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(Exception):
                await retry_openai_call(mock_func, max_retries=2)
        
        assert mock_func.call_count == 3  # Initial + 2 retries


class TestCacheFunctions:
    """Test cache-related functions"""
    
    def test_normalize_query_for_cache(self):
        """Test query normalization for caching"""
        # Test basic normalization
        query1 = "  Строка  1   название   Продукт  "
        normalized1 = normalize_query_for_cache(query1)
        assert normalized1 == "строка 1 название продукт"
        
        # Test with different spacing
        query2 = "СТРОКА    1    НАЗВАНИЕ    ПРОДУКТ"
        normalized2 = normalize_query_for_cache(query2)
        assert normalized2 == "строка 1 название продукт"
        
        # Both should produce same cache key
        assert normalized1 == normalized2
    
    def test_adapt_cached_intent(self):
        """Test adapting cached intent to current query"""
        cached_intent = {
            "action": "set_name",
            "row": 1,
            "name": "Old Product"
        }
        
        # Test adapting name
        query = "строка 2 название New Product"
        adapted = adapt_cached_intent(cached_intent, query)
        assert adapted["row"] == 1  # Row shouldn't change from cache
        assert adapted["name"] == "Old Product"  # Name shouldn't change
        
        # Test with price
        cached_price = {
            "action": "set_price",
            "row": 1,
            "price": 100
        }
        query_price = "строка 1 цена 200"
        adapted_price = adapt_cached_intent(cached_price, query_price)
        assert adapted_price["price"] == 200


@pytest.mark.asyncio
class TestRunThreadSafeAsync:
    """Test run_thread_safe_async function"""
    
    @patch('app.assistants.client.openai.beta.threads.messages.create')
    @patch('app.assistants.client.openai.beta.threads.runs.create_and_poll')
    @patch('app.assistants.client.openai.beta.threads.messages.list')
    @patch('app.assistants.client.get_thread')
    @patch('app.assistants.client.cache_get')
    @patch('app.assistants.client.cache_set')
    async def test_successful_run_with_cache_miss(
        self, 
        mock_cache_set,
        mock_cache_get, 
        mock_get_thread,
        mock_messages_list,
        mock_run_create,
        mock_message_create
    ):
        """Test successful run with cache miss"""
        # Setup mocks
        mock_cache_get.return_value = None  # Cache miss
        mock_get_thread.return_value = "thread-123"
        
        # Mock OpenAI responses
        mock_run = Mock()
        mock_run.status = "completed"
        mock_run_create.return_value = mock_run
        
        # Mock message response
        mock_message = Mock()
        mock_message.content = [
            Mock(text=Mock(value='{"commands": [{"action": "set_name", "row": 1, "name": "Test"}]}'))
        ]
        mock_messages_list.return_value = Mock(data=[mock_message])
        
        # Run function
        result = await run_thread_safe_async("строка 1 название Test", invoice_data={})
        
        # Verify result
        assert len(result) == 1
        assert result[0]["action"] == "set_name"
        assert result[0]["row"] == 1
        assert result[0]["name"] == "Test"
        
        # Verify cache was set
        mock_cache_set.assert_called_once()
    
    @patch('app.assistants.client.cache_get')
    async def test_cache_hit(self, mock_cache_get):
        """Test cache hit returns cached result"""
        cached_result = [{"action": "set_qty", "row": 2, "qty": 10}]
        mock_cache_get.return_value = json.dumps(cached_result)
        
        result = await run_thread_safe_async("строка 2 количество 10", invoice_data={})
        
        assert result == cached_result
        # No OpenAI calls should be made
    
    @patch('app.assistants.client.openai.beta.threads.runs.create_and_poll')
    @patch('app.assistants.client.get_thread')
    @patch('app.assistants.client.cache_get')
    async def test_failed_run_status(
        self,
        mock_cache_get,
        mock_get_thread,
        mock_run_create
    ):
        """Test handling of failed run status"""
        mock_cache_get.return_value = None
        mock_get_thread.return_value = "thread-123"
        
        mock_run = Mock()
        mock_run.status = "failed"
        mock_run_create.return_value = mock_run
        
        result = await run_thread_safe_async("test command", invoice_data={})
        
        assert result == []
    
    @patch('app.assistants.client.trace_openai')
    @patch('app.assistants.client.openai.beta.threads.messages.create')
    @patch('app.assistants.client.get_thread')
    @patch('app.assistants.client.cache_get')
    async def test_tracing_integration(
        self,
        mock_cache_get,
        mock_get_thread,
        mock_message_create,
        mock_trace
    ):
        """Test OpenAI tracing integration"""
        mock_cache_get.return_value = None
        mock_get_thread.return_value = "thread-123"
        
        # Mock trace context
        mock_trace.return_value.__enter__ = Mock(return_value=mock_trace)
        mock_trace.return_value.__exit__ = Mock(return_value=None)
        
        # Setup other mocks to make call fail early
        mock_message_create.side_effect = Exception("Test error")
        
        with pytest.raises(Exception):
            await run_thread_safe_async("test", invoice_data={})
        
        # Verify tracing was used
        mock_trace.assert_called()


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for the client module"""
    
    @patch('app.assistants.client.ASSISTANT_ID', 'test-assistant-id')
    async def test_empty_assistant_id(self):
        """Test behavior with empty assistant ID"""
        with patch('app.assistants.client.ASSISTANT_ID', ''):
            # Should handle gracefully
            result = await run_thread_safe_async("test", invoice_data={})
            assert isinstance(result, list)