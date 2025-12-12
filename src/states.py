from aiogram.fsm.state import State, StatesGroup

class SessionStates(StatesGroup):
    idle = State()
    in_session = State()

class MoodStates(StatesGroup):
    waiting_for_score = State()

class MailingStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirmation = State()