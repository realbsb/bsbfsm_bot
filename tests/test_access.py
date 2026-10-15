"""Тесты прав доступа."""

from __future__ import annotations

from workflow.services.access import (
    can_see_agreed_price,
    can_see_final_media,
    can_see_internal_price,
    can_see_stage_media,
)


def test_internal_price_only_manager_supplier():
    assert can_see_internal_price({"manager"})
    assert can_see_internal_price({"supplier"})
    assert not can_see_internal_price({"executor"})
    assert not can_see_internal_price({"secretary"})
    assert not can_see_internal_price(set())


def test_agreed_price_for_all_staff_and_client():
    assert can_see_agreed_price({"executor"}, is_client=False)
    assert can_see_agreed_price(set(), is_client=True)
    assert not can_see_agreed_price(set(), is_client=False)


def test_stage_media_manager_executor():
    assert can_see_stage_media({"manager"})
    assert can_see_stage_media({"executor"})
    assert not can_see_stage_media({"supplier"})
    assert not can_see_stage_media({"secretary"})


def test_final_media_modes():
    assert can_see_final_media(set(), is_client=False, mode="public")
    assert can_see_final_media(set(), is_client=False, mode="delivery_public")
    assert can_see_final_media(set(), is_client=True, mode="client")
    assert not can_see_final_media(set(), is_client=False, mode="denied")
