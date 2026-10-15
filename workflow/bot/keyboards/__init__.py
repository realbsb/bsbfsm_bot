"""Все клавиатуры бота. Реэкспорт по тематическим модулям."""

from .client import client_project_kb
from .common import (
    back_kb,
    cancel_inline_kb,
    confirm_inline_kb,
    confirm_kb,
)
from .intake import form_actions_kb, form_kind_kb
from .main import (
    build_main_kb,
    cancel_kb,
    main_kb,
    phone_kb,
    price_keyboard,
    remove_kb,
    skip_kb,
)
from .profile import (
    lang_kb,
    org_intake_label_kb,
    org_kb,
    profile_kb,
    team_role_kb,
)
from .project import (
    project_kb,
    replacement_kb,
    report_kb,
    stage_actions_kb,
)
from .publish import publish_kb
from .purchase import (
    parse_fallback_kb,
    purchase_review_kb,
    shop_picker_kb,
    shopping_list_kb,
)
from .qr import qr_kind_kb
from .request import (
    request_confirm_kb,
    request_edit_menu_kb,
)
from .schedule import (
    date_kb,
    day_back_kb,
    day_kb,
    projects_multi_kb,
)
from .team import (
    invite_link_kb,
    position_edit_kb,
    position_flags_kb,
    position_pick_kb,
    positions_list_kb,
    team_checklist_kb,
    team_kb,
)

__all__ = [
    # common
    "back_kb",
    "cancel_inline_kb",
    "confirm_inline_kb",
    "confirm_kb",
    # main
    "build_main_kb",
    "cancel_kb",
    "main_kb",
    "phone_kb",
    "price_keyboard",
    "remove_kb",
    "skip_kb",
    # profile
    "lang_kb",
    "org_intake_label_kb",
    "org_kb",
    "profile_kb",
    "team_role_kb",
    # project
    "project_kb",
    "replacement_kb",
    "report_kb",
    "stage_actions_kb",
    # purchase
    "parse_fallback_kb",
    "purchase_review_kb",
    "shop_picker_kb",
    "shopping_list_kb",
    # publish
    "publish_kb",
    # qr
    "qr_kind_kb",
    # request
    "request_confirm_kb",
    "request_edit_menu_kb",
    # schedule
    "date_kb",
    "day_back_kb",
    "day_kb",
    "projects_multi_kb",
    # client
    "client_project_kb",
    # intake
    "form_actions_kb",
    "form_kind_kb",
    # team
    "invite_link_kb",
    "position_edit_kb",
    "position_flags_kb",
    "position_pick_kb",
    "positions_list_kb",
    "team_checklist_kb",
    "team_kb",
]
