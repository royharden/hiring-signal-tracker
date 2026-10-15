"""App inventory synchronization is separate from portable library conformance."""

from typing import get_args

from hiring_signals.contracts import FIELD_IDS, SKILL_IDS
from hiring_signals.shared.aggregate_privacy.models import Metric
from hiring_signals.shared.skill_dictionary.core import CATALOG


def test_app_skill_inventory_matches_portable_dictionary():
    """Catches app taxonomy additions silently missing from dictionary output."""
    assert tuple(entry.skill_id for entry in CATALOG) == SKILL_IDS


def test_app_field_inventory_matches_portable_privacy_partitions():
    """Catches app fields being omitted from the bounded privacy inventory."""
    assert get_args(Metric) == FIELD_IDS
