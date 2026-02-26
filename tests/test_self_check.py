from timetable_amplify.qubo_builder import ideal_block_counts
from timetable_amplify.time_utils import duration_to_slots, slot_to_time, time_to_slot


def test_ideal_block_counts() -> None:
    assert ideal_block_counts(6) == (2, 2, 2)
    assert ideal_block_counts(7) == (2, 2, 3)
    assert ideal_block_counts(8) == (2, 3, 3)


def test_slot_conversion_roundtrip() -> None:
    slot = time_to_slot("12:10", "11:40", 5)
    assert slot == 6
    assert slot_to_time(slot, "11:40", 5) == "12:10"


def test_duration_to_slots() -> None:
    assert duration_to_slots(15, 5) == 3
