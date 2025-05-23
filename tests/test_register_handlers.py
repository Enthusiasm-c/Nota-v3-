"""Tests for app/register_handlers.py"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from app.register_handlers import register_handlers


class TestRegisterHandlers:
    """Test register_handlers function"""
    
    def test_register_handlers_first_time(self):
        """Test registering handlers for the first time"""
        # Create mock dispatcher
        dp = Mock()
        dp.include_router = Mock()
        
        # Ensure _registered_routers doesn't exist
        assert not hasattr(dp, '_registered_routers')
        
        # Register handlers
        register_handlers(dp)
        
        # Check that _registered_routers was created
        assert hasattr(dp, '_registered_routers')
        assert isinstance(dp._registered_routers, set)
        
        # Check all routers were registered
        assert 'name_picker_router' in dp._registered_routers
        assert 'edit_flow_router' in dp._registered_routers
        assert 'review_router' in dp._registered_routers
        
        # Check include_router was called for each router
        assert dp.include_router.call_count == 3
    
    def test_register_handlers_idempotent(self):
        """Test that registering handlers multiple times is idempotent"""
        # Create mock dispatcher
        dp = Mock()
        dp.include_router = Mock()
        
        # First registration
        register_handlers(dp)
        first_call_count = dp.include_router.call_count
        
        # Second registration
        register_handlers(dp)
        second_call_count = dp.include_router.call_count
        
        # Should not register routers again
        assert first_call_count == second_call_count
        assert first_call_count == 3
    
    def test_register_handlers_partial_registration(self):
        """Test registering handlers when some are already registered"""
        # Create mock dispatcher with some routers already registered
        dp = Mock()
        dp.include_router = Mock()
        dp._registered_routers = {'name_picker_router'}  # Only one router registered
        
        # Register handlers
        register_handlers(dp)
        
        # Should only register the missing routers
        assert dp.include_router.call_count == 2
        assert 'edit_flow_router' in dp._registered_routers
        assert 'review_router' in dp._registered_routers
        assert len(dp._registered_routers) == 3
    
    @patch('app.register_handlers.edit_flow_router')
    @patch('app.register_handlers.name_picker_router')
    @patch('app.register_handlers.review_router')
    def test_register_handlers_with_actual_routers(
        self, 
        mock_review_router,
        mock_name_picker_router,
        mock_edit_flow_router
    ):
        """Test registering handlers with actual router objects"""
        # Create mock dispatcher
        dp = Mock()
        dp.include_router = Mock()
        
        # Register handlers
        register_handlers(dp)
        
        # Verify each router was passed to include_router
        dp.include_router.assert_any_call(mock_name_picker_router)
        dp.include_router.assert_any_call(mock_edit_flow_router)
        dp.include_router.assert_any_call(mock_review_router)
    
    def test_register_handlers_preserves_existing_attributes(self):
        """Test that register_handlers preserves existing dispatcher attributes"""
        # Create mock dispatcher with existing attributes
        dp = Mock()
        dp.include_router = Mock()
        dp.some_attribute = "test_value"
        dp.another_attribute = 123
        
        # Register handlers
        register_handlers(dp)
        
        # Check that existing attributes are preserved
        assert dp.some_attribute == "test_value"
        assert dp.another_attribute == 123
        assert hasattr(dp, '_registered_routers')
    
    def test_register_handlers_router_tracking(self):
        """Test that router tracking works correctly"""
        # Create mock dispatcher
        dp = Mock()
        dp.include_router = Mock()
        
        # Simulate include_router failure for one router
        def side_effect(router):
            if dp.include_router.call_count == 2:  # Fail on second router
                raise Exception("Router registration failed")
            
        dp.include_router.side_effect = side_effect
        
        # Register handlers (should fail)
        with pytest.raises(Exception):
            register_handlers(dp)
        
        # Check that only the first router was tracked
        assert hasattr(dp, '_registered_routers')
        assert 'name_picker_router' in dp._registered_routers
        assert 'edit_flow_router' not in dp._registered_routers
        assert 'review_router' not in dp._registered_routers