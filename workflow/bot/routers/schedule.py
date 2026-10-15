"""«Мой день»: задачи на сегодня / завтра / другой день."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import or_, select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import (
    CalendarEvent,
    CalendarKind,
    CalendarProvider,
    CalendarStatus,
    Project,
    ProjectStageAssignee,
    Stage,
    User,
    UserCalendarPref,
)
from ...services.day import (
    get_day_tasks,
    get_manager_id_for,
    get_planned_project_ids,
    is_day_off,
    sort_tasks,
)
from ..keyboards import date_kb, day_back_kb, day_kb, projects_multi_kb
from ..states import ScheduleFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="schedule")

WEEKDAYS_RU = ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


# ============================================================
# Вход
# ============================================================


@router.message(Command("day"))
@trace
async def day_cmd(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await _show_day(msg, state, user, session, locale, date.today())


@router.message(F.text == "📅 Мой день")
@trace
async def day_btn(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await _show_day(msg, state, user, session, locale, date.today())


@router.callback_query(F.data == "day:today")
@trace
async def day_cb_today(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await _show_day(cb.message, state, user, session, locale, date.today(), edit=True)
    await cb.answer()


@router.callback_query(F.data == "day:tomorrow")
@trace
async def day_cb_tomorrow(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    target = date.today() + timedelta(days=1)
    await _show_day(cb.message, state, user, session, locale, target, edit=True)
    await cb.answer()


@router.callback_query(F.data == "day:other")
@trace
async def day_cb_other(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await cb.message.edit_text(t("day.pick_date", locale), reply_markup=date_kb())
    await cb.answer()


# ============================================================
# Рендер «Мой день»
# ============================================================


async def _show_day(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
    target: date,
    edit: bool = False,
) -> None:
    manager_id = await get_manager_id_for(session, user)
    day_off = await is_day_off(session, manager_id, target)

    day_tasks, overdue_tasks = await get_day_tasks(session, user, target)
    day_tasks = await sort_tasks(session, day_tasks)
    overdue_tasks = await sort_tasks(session, overdue_tasks)

    text = await _render_day(
        session,
        target,
        day_off,
        overdue_tasks,
        day_tasks,
        locale,
    )

    kb = day_kb() if target == date.today() else day_back_kb()

    if edit:
        try:
            await msg.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await msg.answer(text, reply_markup=kb)


async def _render_day(
    session,
    target: date,
    day_off: bool,
    overdue: list[Project],
    tasks: list[Project],
    locale: str,
) -> str:
    today = date.today()
    if target == today:
        header = t(
            "day.header_today",
            locale,
            date=target.strftime("%d.%m"),
            weekday=WEEKDAYS_RU[target.isoweekday()],
        )
    elif target == today + timedelta(days=1):
        header = t(
            "day.header_tomorrow",
            locale,
            date=target.strftime("%d.%m"),
            weekday=WEEKDAYS_RU[target.isoweekday()],
        )
    else:
        header = t(
            "day.header_date",
            locale,
            date=target.strftime("%d.%m"),
            weekday=WEEKDAYS_RU[target.isoweekday()],
        )

    lines = [header]

    if day_off:
        lines.append("")
        lines.append(t("day.day_off", locale))

    if not overdue and not tasks:
        lines.append("")
        lines.append(t("day.rest", locale))
        return "\n".join(lines)

    if overdue:
        lines.append("")
        lines.append(t("day.overdue_title", locale))
        for p in overdue:
            lines.append(await _render_task_line(session, p, locale))

    if tasks:
        lines.append("")
        for p in tasks:
            lines.append(await _render_task_line(session, p, locale))

    return "\n".join(lines)


async def _render_task_line(session, p: Project, locale: str) -> str:
    stage = await session.get(Stage, p.stage_id)
    stage_name = t(stage.name_i18n_key, locale) if stage else "—"

    a = (
        (
            await session.execute(
                select(ProjectStageAssignee).where(
                    ProjectStageAssignee.project_id == p.id,
                    ProjectStageAssignee.active_slot == 1,
                )
            )
        )
        .scalars()
        .first()
    )
    percent = a.progress_percent if a else None

    marker = "🔧" if p.current_assignee_id else "•"
    title = p.address_text or p.client_name or f"#{p.id}"

    parts = [f"{marker} #{p.id} — {title}"]
    if percent is not None:
        parts.append(f"   {stage_name}, {percent}%")
    else:
        parts.append(f"   {stage_name}")

    if p.lat is not None and p.lon is not None:
        parts.append(f"   📍 {p.lat}, {p.lon}")

    return "\n".join(parts)


# ============================================================
# Выбор другого дня
# ============================================================


@router.callback_query(F.data.startswith("date:"))
@trace
async def on_date_pick(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    date_iso = cb.data.split(":")[1]
    target = date.fromisoformat(date_iso)
    await _show_day(cb.message, state, user, session, locale, target, edit=True)
    await cb.answer()


# ============================================================
# Перепланирование (упрощённое)
# ============================================================


@router.callback_query(F.data == "day:reschedule")
@trace
async def reschedule_start(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    target = date.today() + timedelta(days=1)
    await state.set_state(ScheduleFSM.pick_projects)
    await state.update_data(date=target.isoformat(), selected=[])

    projects = await _unplanned_projects(session, user)
    if not projects:
        await cb.message.edit_text(t("schedule.no_projects", locale))
        await state.clear()
        await cb.answer()
        return

    text = t("schedule.pick_projects", locale, date=target.strftime("%d.%m"))
    try:
        await cb.message.edit_text(
            text,
            reply_markup=projects_multi_kb(projects, set()),
        )
    except Exception:
        await cb.message.answer(
            text,
            reply_markup=projects_multi_kb(projects, set()),
        )
    await cb.answer()


async def _unplanned_projects(session, user: User) -> list[Project]:
    """Проекты пользователя, ещё не запланированные на сегодня/завтра."""
    planned_today = await get_planned_project_ids(session, user.id, date.today())
    planned_tomorrow = await get_planned_project_ids(
        session,
        user.id,
        date.today() + timedelta(days=1),
    )
    exclude = planned_today | planned_tomorrow

    q = (
        select(Project)
        .where(Project.closed_at.is_(None))
        .where(
            or_(
                Project.current_assignee_id == user.id,
                Project.manager_id == user.id,
            )
        )
    )
    all_active = (await session.execute(q)).scalars().all()
    return [p for p in all_active if p.id not in exclude]


@router.callback_query(ScheduleFSM.pick_projects, F.data.startswith("pick:"))
@trace
async def reschedule_pick(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    pid = int(cb.data.split(":")[1])
    data = await state.get_data()
    sel = set(data.get("selected", []))
    sel.symmetric_difference_update({pid})
    await state.update_data(selected=list(sel))

    projects = await _unplanned_projects(session, user)
    try:
        await cb.message.edit_reply_markup(
            reply_markup=projects_multi_kb(projects, sel),
        )
    except Exception:
        pass
    await cb.answer()


@router.callback_query(ScheduleFSM.pick_projects, F.data == "plan_confirm")
@trace
async def reschedule_confirm(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    data = await state.get_data()
    selected = data.get("selected", [])
    target = date.fromisoformat(data["date"])

    from ...integrations.caldav_client import CaldavClient, is_configured

    pref = (
        (await session.execute(select(UserCalendarPref).where(UserCalendarPref.user_id == user.id)))
        .scalars()
        .first()
    )
    if pref is None:
        pref = UserCalendarPref(user_id=user.id)
        session.add(pref)
        await session.flush()

    caldav = CaldavClient(settings)
    created = 0

    for pid in selected:
        project = await session.get(Project, pid)
        if project is None:
            continue

        start = datetime.combine(target, datetime.min.time()).replace(hour=9)
        end = start + timedelta(hours=8)

        external_uid: str | None = None
        if pref.meetings_enabled and is_configured(pref):
            external_uid = await caldav.create_event(
                pref=pref,
                kind="work",
                project_id=pid,
                start=start,
                duration_minutes=480,
                summary=f"Работы по проекту #{pid}",
                group_uid=f"work-{user.id}-{pid}",
            )

        session.add(
            CalendarEvent(
                group_uid=f"work-{user.id}-{pid}-{int(start.timestamp())}",
                project_id=pid,
                kind=CalendarKind.WORK,
                initiator_id=user.id,
                approver_id=None,
                owner_id=user.id,
                provider=CalendarProvider.RADICALE,
                external_uid=external_uid,
                start_at=start,
                end_at=end,
                status=CalendarStatus.PROPOSED,
            )
        )
        created += 1

    await session.commit()
    await state.clear()
    try:
        await cb.message.edit_text(t("schedule.saved", locale, count=created))
    except Exception:
        await cb.message.answer(t("schedule.saved", locale, count=created))
    await cb.answer()
