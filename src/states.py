from aiogram.fsm.state import State, StatesGroup

class SessionStates(StatesGroup):
    idle = State()
    in_session = State()