import pytest
import asyncio
import contextvars
from app.trace_context import get_request_id, set_request_id, reset_request_id, request_id_var


class TestRequestIdContext:
    """Test request ID context management."""

    def setup_method(self):
        """Reset context before each test."""
        reset_request_id()

    def test_default_request_id_is_none(self):
        """Test that default request ID is None."""
        assert get_request_id() is None

    def test_set_and_get_request_id(self):
        """Test setting and getting request ID."""
        test_id = "test-request-123"
        set_request_id(test_id)
        
        assert get_request_id() == test_id

    def test_reset_request_id(self):
        """Test resetting request ID."""
        # Set a request ID
        set_request_id("test-id")
        assert get_request_id() == "test-id"
        
        # Reset it
        reset_request_id()
        assert get_request_id() is None

    def test_overwrite_request_id(self):
        """Test overwriting existing request ID."""
        set_request_id("first-id")
        assert get_request_id() == "first-id"
        
        set_request_id("second-id")
        assert get_request_id() == "second-id"

    def test_empty_string_request_id(self):
        """Test setting empty string as request ID."""
        set_request_id("")
        assert get_request_id() == ""

    def test_numeric_string_request_id(self):
        """Test setting numeric string as request ID."""
        set_request_id("123456")
        assert get_request_id() == "123456"

    def test_uuid_like_request_id(self):
        """Test setting UUID-like string as request ID."""
        uuid_id = "123e4567-e89b-12d3-a456-426614174000"
        set_request_id(uuid_id)
        assert get_request_id() == uuid_id

    def test_special_characters_in_request_id(self):
        """Test request ID with special characters."""
        special_id = "req-123_test.id"
        set_request_id(special_id)
        assert get_request_id() == special_id


class TestContextVarBehavior:
    """Test context variable behavior."""

    def setup_method(self):
        """Reset context before each test."""
        reset_request_id()

    @pytest.mark.asyncio
    async def test_context_isolation_between_tasks(self):
        """Test that context is isolated between async tasks."""
        results = []
        
        async def task_with_id(task_id: str, expected_id: str):
            set_request_id(expected_id)
            # Simulate some async work
            await asyncio.sleep(0.01)
            # Context should be preserved
            actual_id = get_request_id()
            results.append((task_id, expected_id, actual_id))
        
        # Run multiple tasks concurrently
        await asyncio.gather(
            task_with_id("task1", "id-1"),
            task_with_id("task2", "id-2"),
            task_with_id("task3", "id-3")
        )
        
        # Each task should have its own context
        assert len(results) == 3
        for task_id, expected_id, actual_id in results:
            assert actual_id == expected_id, f"Task {task_id} context leaked"

    def test_context_inheritance_in_threads(self):
        """Test that context is inherited but isolated."""
        import threading
        
        results = []
        
        def thread_function(thread_id: str):
            # Each thread should start with the parent context
            initial_id = get_request_id()
            
            # Set a new ID in this thread
            new_id = f"thread-{thread_id}"
            set_request_id(new_id)
            
            results.append((thread_id, initial_id, get_request_id()))
        
        # Set ID in main thread
        set_request_id("main-thread")
        
        # Create threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=thread_function, args=(str(i),))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Main thread context should be unchanged
        assert get_request_id() == "main-thread"
        
        # Each thread should have had its own context
        assert len(results) == 3
        for thread_id, initial_id, final_id in results:
            # Context vars don't inherit across threads by default
            assert initial_id is None  # New threads start with default
            assert final_id == f"thread-{thread_id}"  # Set in thread

    def test_context_var_direct_access(self):
        """Test direct access to context variable."""
        # Test setting through context variable directly
        request_id_var.set("direct-set")
        assert get_request_id() == "direct-set"
        
        # Test getting through context variable directly  
        set_request_id("function-set")
        assert request_id_var.get() == "function-set"

    def test_context_var_default_value(self):
        """Test context variable default value."""
        # Reset context
        reset_request_id()
        
        # Direct access should return None (default)
        assert request_id_var.get() is None
        # When context var already has a value (None), get with default returns that value, not the default
        # This is expected behavior for ContextVar
        assert request_id_var.get("custom-default") is None


class TestTraceContextIntegration:
    """Integration tests for trace context module."""

    def setup_method(self):
        """Reset context before each test."""
        reset_request_id()

    def test_request_lifecycle_simulation(self):
        """Test simulating a complete request lifecycle."""
        # Start of request - no ID
        assert get_request_id() is None
        
        # Middleware sets request ID
        request_id = "req-2024-001"
        set_request_id(request_id)
        
        # Throughout request processing, ID should be available
        assert get_request_id() == request_id
        
        # Simulate nested function calls
        def process_data():
            return get_request_id()
        
        def handle_request():
            return process_data()
        
        assert handle_request() == request_id
        
        # End of request - reset ID
        reset_request_id()
        assert get_request_id() is None

    @pytest.mark.asyncio
    async def test_async_request_handling(self):
        """Test async request handling with context."""
        async def async_handler(req_id: str):
            set_request_id(req_id)
            
            # Simulate async operations
            await asyncio.sleep(0.001)
            
            # Context should persist
            assert get_request_id() == req_id
            
            # Simulate nested async calls
            async def nested_operation():
                await asyncio.sleep(0.001)
                return get_request_id()
            
            result = await nested_operation()
            assert result == req_id
            
            return req_id
        
        # Process multiple async requests
        tasks = [
            async_handler("async-req-1"),
            async_handler("async-req-2"),
            async_handler("async-req-3")
        ]
        
        results = await asyncio.gather(*tasks)
        expected = ["async-req-1", "async-req-2", "async-req-3"]
        assert sorted(results) == sorted(expected)

    def test_context_error_handling(self):
        """Test context handling during errors."""
        set_request_id("error-test")
        
        try:
            # Simulate error during request processing
            assert get_request_id() == "error-test"
            raise ValueError("Test error")
        except ValueError:
            # Context should still be available during error handling
            assert get_request_id() == "error-test"
        
        # Context persists after error
        assert get_request_id() == "error-test"

    def test_multiple_context_operations(self):
        """Test multiple context operations in sequence."""
        operations = [
            ("op-1", "request-1"),
            ("op-2", "request-2"),
            ("op-3", "request-3"),
            ("reset", None),
            ("op-4", "request-4")
        ]
        
        for operation, expected_value in operations:
            if operation == "reset":
                reset_request_id()
            else:
                set_request_id(expected_value)
            
            assert get_request_id() == expected_value


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def setup_method(self):
        """Reset context before each test."""
        reset_request_id()

    def test_very_long_request_id(self):
        """Test with very long request ID."""
        long_id = "a" * 1000  # Very long string
        set_request_id(long_id)
        assert get_request_id() == long_id

    def test_unicode_request_id(self):
        """Test with Unicode characters in request ID."""
        unicode_id = "req-тест-🚀-123"
        set_request_id(unicode_id)
        assert get_request_id() == unicode_id

    def test_none_request_id_explicit(self):
        """Test explicitly setting None as request ID."""
        set_request_id("test")
        assert get_request_id() == "test"
        
        # Explicitly set None
        set_request_id(None)
        assert get_request_id() is None

    def test_repeated_operations(self):
        """Test repeated get/set operations."""
        test_id = "repeated-test"
        
        # Set and get multiple times
        for i in range(10):
            set_request_id(f"{test_id}-{i}")
            assert get_request_id() == f"{test_id}-{i}"
        
        # Reset multiple times
        for i in range(5):
            reset_request_id()
            assert get_request_id() is None 
 