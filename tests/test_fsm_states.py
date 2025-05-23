"""Tests for app/fsm/states.py"""

import pytest
from aiogram.fsm.state import State, StatesGroup

from app.fsm.states import (
    EditFree,
    NotaStates,
    InvoiceReviewStates,
    EditPosition
)


class TestEditFreeStates:
    """Test EditFree state group"""
    
    def test_edit_free_is_states_group(self):
        """Test that EditFree is a proper StatesGroup"""
        assert issubclass(EditFree, StatesGroup)
    
    def test_edit_free_states_exist(self):
        """Test that all EditFree states exist"""
        assert hasattr(EditFree, 'awaiting_input')
        assert hasattr(EditFree, 'awaiting_free_edit')
        assert hasattr(EditFree, 'awaiting_pick_name')
    
    def test_edit_free_states_are_state_instances(self):
        """Test that EditFree attributes are State instances"""
        assert isinstance(EditFree.awaiting_input, State)
        assert isinstance(EditFree.awaiting_free_edit, State)
        assert isinstance(EditFree.awaiting_pick_name, State)
    
    def test_edit_free_states_have_unique_names(self):
        """Test that each state has a unique state name"""
        states = [
            EditFree.awaiting_input,
            EditFree.awaiting_free_edit,
            EditFree.awaiting_pick_name
        ]
        state_names = [state.state for state in states]
        assert len(state_names) == len(set(state_names))
    
    def test_edit_free_state_naming_convention(self):
        """Test that state names follow the expected pattern"""
        assert EditFree.awaiting_input.state == "EditFree:awaiting_input"
        assert EditFree.awaiting_free_edit.state == "EditFree:awaiting_free_edit"
        assert EditFree.awaiting_pick_name.state == "EditFree:awaiting_pick_name"


class TestNotaStates:
    """Test NotaStates state group"""
    
    def test_nota_states_is_states_group(self):
        """Test that NotaStates is a proper StatesGroup"""
        assert issubclass(NotaStates, StatesGroup)
    
    def test_nota_states_exist(self):
        """Test that all NotaStates exist"""
        expected_states = [
            'main_menu',
            'awaiting_file',
            'progress',
            'editing',
            'help'
        ]
        for state_name in expected_states:
            assert hasattr(NotaStates, state_name)
    
    def test_nota_states_are_state_instances(self):
        """Test that NotaStates attributes are State instances"""
        assert isinstance(NotaStates.main_menu, State)
        assert isinstance(NotaStates.awaiting_file, State)
        assert isinstance(NotaStates.progress, State)
        assert isinstance(NotaStates.editing, State)
        assert isinstance(NotaStates.help, State)
    
    def test_nota_states_unique(self):
        """Test that NotaStates are unique"""
        states = [
            NotaStates.main_menu,
            NotaStates.awaiting_file,
            NotaStates.progress,
            NotaStates.editing,
            NotaStates.help
        ]
        state_names = [state.state for state in states]
        assert len(state_names) == len(set(state_names))


class TestInvoiceReviewStates:
    """Test InvoiceReviewStates state group"""
    
    def test_invoice_review_states_is_states_group(self):
        """Test that InvoiceReviewStates is a proper StatesGroup"""
        assert issubclass(InvoiceReviewStates, StatesGroup)
    
    def test_invoice_review_states_exist(self):
        """Test that all InvoiceReviewStates exist"""
        assert hasattr(InvoiceReviewStates, 'review')
        assert hasattr(InvoiceReviewStates, 'choose_line')
        assert hasattr(InvoiceReviewStates, 'edit_line')
    
    def test_invoice_review_states_are_state_instances(self):
        """Test that InvoiceReviewStates attributes are State instances"""
        assert isinstance(InvoiceReviewStates.review, State)
        assert isinstance(InvoiceReviewStates.choose_line, State)
        assert isinstance(InvoiceReviewStates.edit_line, State)
    
    def test_invoice_review_state_flow(self):
        """Test the logical flow of invoice review states"""
        # States should have different values
        assert InvoiceReviewStates.review.state != InvoiceReviewStates.choose_line.state
        assert InvoiceReviewStates.choose_line.state != InvoiceReviewStates.edit_line.state
        assert InvoiceReviewStates.review.state != InvoiceReviewStates.edit_line.state


class TestEditPosition:
    """Test EditPosition state group"""
    
    def test_edit_position_is_states_group(self):
        """Test that EditPosition is a proper StatesGroup"""
        assert issubclass(EditPosition, StatesGroup)
    
    def test_edit_position_states_exist(self):
        """Test that all EditPosition states exist"""
        expected_states = [
            'waiting_field',
            'waiting_name',
            'waiting_qty',
            'waiting_unit',
            'waiting_price'
        ]
        for state_name in expected_states:
            assert hasattr(EditPosition, state_name)
    
    def test_edit_position_states_are_state_instances(self):
        """Test that EditPosition attributes are State instances"""
        assert isinstance(EditPosition.waiting_field, State)
        assert isinstance(EditPosition.waiting_name, State)
        assert isinstance(EditPosition.waiting_qty, State)
        assert isinstance(EditPosition.waiting_unit, State)
        assert isinstance(EditPosition.waiting_price, State)
    
    def test_edit_position_states_match_fields(self):
        """Test that EditPosition states correspond to editable fields"""
        # Each waiting state should correspond to a field that can be edited
        field_states = [
            EditPosition.waiting_name,
            EditPosition.waiting_qty,
            EditPosition.waiting_unit,
            EditPosition.waiting_price
        ]
        
        # All should be distinct states
        state_values = [state.state for state in field_states]
        assert len(state_values) == len(set(state_values))
        
        # waiting_field should be different from all specific field states
        assert EditPosition.waiting_field.state not in state_values


class TestStateGroupsIntegration:
    """Test integration between different state groups"""
    
    def test_all_state_groups_are_distinct(self):
        """Test that all state groups are distinct classes"""
        state_groups = [EditFree, NotaStates, InvoiceReviewStates, EditPosition]
        assert len(state_groups) == len(set(state_groups))
    
    def test_no_state_name_collisions(self):
        """Test that there are no state name collisions across groups"""
        all_states = []
        
        # Collect all states from all groups
        for attr in dir(EditFree):
            obj = getattr(EditFree, attr)
            if isinstance(obj, State):
                all_states.append(obj.state)
        
        for attr in dir(NotaStates):
            obj = getattr(NotaStates, attr)
            if isinstance(obj, State):
                all_states.append(obj.state)
        
        for attr in dir(InvoiceReviewStates):
            obj = getattr(InvoiceReviewStates, attr)
            if isinstance(obj, State):
                all_states.append(obj.state)
        
        for attr in dir(EditPosition):
            obj = getattr(EditPosition, attr)
            if isinstance(obj, State):
                all_states.append(obj.state)
        
        # Check for uniqueness
        assert len(all_states) == len(set(all_states))
    
    def test_state_groups_inherit_from_states_group(self):
        """Test that all custom state groups inherit from StatesGroup"""
        state_groups = [EditFree, NotaStates, InvoiceReviewStates, EditPosition]
        for group in state_groups:
            assert issubclass(group, StatesGroup)
    
    def test_state_string_representation(self):
        """Test that states have meaningful string representations"""
        # Test a few states to ensure they have proper string format
        assert "EditFree" in str(EditFree.awaiting_input.state)
        assert "NotaStates" in str(NotaStates.main_menu.state)
        assert "InvoiceReviewStates" in str(InvoiceReviewStates.review.state)
        assert "EditPosition" in str(EditPosition.waiting_field.state)