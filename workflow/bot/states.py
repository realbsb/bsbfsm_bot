"""FSM-состояния."""

from aiogram.fsm.state import State, StatesGroup


class RequestFSM(StatesGroup):
    awaiting_details = State()
    confirm = State()
    edit_field = State()
    step_by_step = State()


class StageFSM(StatesGroup):
    awaiting_media = State()
    awaiting_calc = State()
    awaiting_confirm = State()
    awaiting_reason = State()


class VoiceFallbackFSM(StatesGroup):
    question = State()
    review = State()


class PriceFSM(StatesGroup):
    digits = State()
    confirm = State()


class ScheduleFSM(StatesGroup):
    pick_date = State()
    pick_projects = State()
    order = State()
    confirm = State()


class PurchaseFSM(StatesGroup):
    review_parsed = State()
    edit_item = State()
    pick_shop = State()
    add_item = State()


class ParseFSM(StatesGroup):
    review = State()
    manual = State()


class MediaFSM(StatesGroup):
    attaching = State()
    choosing_final = State()


class TeamFSM(StatesGroup):
    pick_role = State()
    pick_user = State()
    rename_position = State()
    new_position_name = State()


class ProjectFSM(StatesGroup):
    edit_field = State()
    edit_value = State()


class ProfileFSM(StatesGroup):
    radicale_url = State()
    radicale_username = State()
    radicale_password = State()


class FormFSM(StatesGroup):
    pick_title = State()
    edit_fields = State()


class OrgFSM(StatesGroup):
    intake_label = State()
