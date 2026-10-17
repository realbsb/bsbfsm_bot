"""Проверки доступа к карточке проекта."""

from workflow.bot.routers.project import _can_access_project
from workflow.models import Project, User


def test_project_access_is_limited_to_participants() -> None:
    project = Project(
        manager_id=1,
        secretary_id=2,
        supplier_id=3,
        executor_id=4,
        current_assignee_id=5,
        client_user_id=6,
    )

    for user_id in range(1, 7):
        assert _can_access_project(project, User(id=user_id, tg_id=user_id))

    assert not _can_access_project(project, User(id=7, tg_id=7))
