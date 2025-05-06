from aiogram.fsm.state import StatesGroup, State

class EditFree(StatesGroup):
    awaiting_input = State()
    awaiting_free_edit = State()
    awaiting_pick_name = State()  # Added for fuzzy match feature
    
class NotaStates(StatesGroup):
    lang = State()
    main_menu = State()
    awaiting_file = State()
    progress = State()
    editing = State()
    help = State()
