import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cogs.economy import format_remaining, time_until_ready


def test_time_until_ready_when_never_claimed():
    assert time_until_ready(None, timedelta(hours=24), datetime.utcnow()) is None  # noqa: DTZ003


def test_time_until_ready_when_cooldown_expired():
    now = datetime.utcnow()  # noqa: DTZ003
    last_claim = now - timedelta(hours=25)
    assert time_until_ready(last_claim, timedelta(hours=24), now) is None


def test_time_until_ready_when_still_on_cooldown():
    now = datetime.utcnow()  # noqa: DTZ003
    last_claim = now - timedelta(hours=5)
    remaining = time_until_ready(last_claim, timedelta(hours=24), now)
    assert remaining == timedelta(hours=19)


def test_time_until_ready_exact_boundary():
    now = datetime.utcnow()  # noqa: DTZ003
    last_claim = now - timedelta(hours=24)
    # Exactly at the cooldown boundary should be ready
    assert time_until_ready(last_claim, timedelta(hours=24), now) is None


def test_format_remaining_days_hours_minutes():
    remaining = timedelta(days=1, hours=3, minutes=12)
    assert format_remaining(remaining) == "1d 3h 12m"


def test_format_remaining_hours_only():
    remaining = timedelta(hours=2, minutes=30)
    assert format_remaining(remaining) == "2h 30m"


def test_format_remaining_minutes_only():
    remaining = timedelta(minutes=45)
    assert format_remaining(remaining) == "45m"
