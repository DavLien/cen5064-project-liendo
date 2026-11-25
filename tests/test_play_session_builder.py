import pytest

from domain.session import PlaySessionBuilder


def test_builder_creates_minimal_session_with_derived_hours():
    session = PlaySessionBuilder(
        game_id=1,
        date="November 25, 2026 11:30:00 AM",
        duration_seconds=5400.0,
    ).build()

    assert session.id is None
    assert session.game_id == 1
    assert session.duration_seconds == 5400.0
    assert session.duration_hours == 1.5
    assert session.subject == ""
    assert session.notes == ""


def test_builder_sets_optional_fields_and_trims_whitespace():
    session = (
        PlaySessionBuilder(
            game_id=2,
            date="November 25, 2026 12:00:00 PM",
            duration_seconds=1800.0,
        )
        .with_id(0)
        .with_subject("  Boss Fight  ")
        .with_notes("  Cleared phase two  ")
        .build()
    )

    assert session.id == 0
    assert session.duration_hours == 0.5
    assert session.subject == "Boss Fight"
    assert session.notes == "Cleared phase two"


def test_builder_rejects_non_positive_duration():
    with pytest.raises(ValueError, match="greater than zero"):
        PlaySessionBuilder(
            game_id=1,
            date="November 25, 2026 12:00:00 PM",
            duration_seconds=0.0,
        ).build()
