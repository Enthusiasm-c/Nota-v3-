from aiogram.fsm.state import StatesGroup, State

class EditFree(StatesGroup):
    awaiting_input = State()
    awaiting_free_edit = State()
