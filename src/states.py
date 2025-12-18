from aiogram.fsm.state import State, StatesGroup

class SessionStates(StatesGroup):
    idle = State()
    in_session = State()

class MoodStates(StatesGroup):
    waiting_for_score = State()

class MailingStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirmation = State()

class OnboardingStates(StatesGroup):
    step1 = State()
    step2 = State()
    step3 = State()


class TestStates(StatesGroup):
    disclaimer = State()
    picking_test = State()
    picking_length = State()
    in_test = State()