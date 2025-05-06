"""
Helper module for registering all handlers with the dispatcher.
"""

from aiogram import Dispatcher
from app.handlers.edit_flow import router as edit_flow_router
from app.handlers.name_picker import router as name_picker_router


def register_handlers(dp: Dispatcher):
    """
    Registers all handlers with the dispatcher.
    
    Args:
        dp: Aiogram dispatcher
    """
    # Initialize set for tracking registered routers if not exists
    if not hasattr(dp, '_registered_routers'):
        dp._registered_routers = set()
    
    # Register name_picker router
    if 'name_picker_router' not in dp._registered_routers:
        dp.include_router(name_picker_router)
        dp._registered_routers.add('name_picker_router')
    
    # Register edit_flow router
    if 'edit_flow_router' not in dp._registered_routers:
        dp.include_router(edit_flow_router)
        dp._registered_routers.add('edit_flow_router')
    
    # Add other routers as needed