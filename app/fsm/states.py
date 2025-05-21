from aiogram.fsm.state import StatesGroup, State

class EditFree(StatesGroup):
    awaiting_input = State()
    awaiting_free_edit = State()
    awaiting_pick_name = State()  # Added for fuzzy match feature
    
class NotaStates(StatesGroup):
    main_menu = State()
    awaiting_file = State()
    progress = State()
    editing = State()
    help = State()

class InvoiceReviewStates(StatesGroup):
    review = State()
    choose_line = State()
    edit_line = State()

class EditPosition(StatesGroup):
    waiting_field = State()
    waiting_name = State()
    waiting_qty = State()
    waiting_unit = State()
    waiting_price = State()
