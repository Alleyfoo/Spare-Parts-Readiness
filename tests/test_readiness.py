import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from readiness import (  # noqa: E402
    CRITICAL, LOW, OK, UNKNOWN,
    apply_approved, demo_bom, demo_machines, demo_parts, fix_first,
    machine_readiness, missing_columns, new_proposal, part_lines,
)


@pytest.fixture
def plant():
    machines, parts, bom = demo_machines(), demo_parts(), demo_bom()
    lines = part_lines(machines, parts, bom)
    return machines, parts, bom, lines, machine_readiness(machines, lines)


def status(readiness, machine_id):
    return readiness.set_index("machine_id").loc[machine_id, "status"]


def test_no_parts_list_is_unknown_not_ok(plant):
    *_, readiness = plant
    assert status(readiness, "SC-01") == UNKNOWN
    assert status(readiness, "BE-01") == UNKNOWN


def test_a_critical_spare_at_zero_makes_the_machine_critical(plant):
    *_, lines, readiness = plant
    # BC-01's gearbox SP-1501 is critical and out of stock everywhere
    line = lines[(lines.machine_id == "BC-01") & (lines.part_no == "SP-1501")].iloc[0]
    assert line.status == CRITICAL
    assert status(readiness, "BC-01") == CRITICAL


def test_stock_in_either_country_counts(plant):
    *_, lines, _ = plant
    # SP-1203 drive pulley: 0 in Finland, 1 in Sweden, critical -> covered
    line = lines[lines.part_no == "SP-1203"].iloc[0]
    assert line.status == OK
    assert line.note == "stock in Sweden only"


def test_a_wear_part_below_one_full_change_is_low(plant):
    *_, lines, _ = plant
    # BC-01 needs 5 return idlers; 4 + 2 = 6 in stock -> fine
    # BC-02 impact idlers: 4 installed, 2 in stock -> low
    line = lines[(lines.machine_id == "BC-02") & (lines.part_no == "SP-1104")].iloc[0]
    assert line.status == LOW


def test_a_part_missing_from_the_item_master_is_said_aloud(plant):
    *_, lines, readiness = plant
    line = lines[lines.part_no == "SP-1999"].iloc[0]
    assert not line.in_item_master
    assert line.status == UNKNOWN
    assert "not in the item master" in line.note
    assert status(readiness, "BC-04") == UNKNOWN


def test_fix_first_lists_unknown_and_critical_before_low(plant):
    *_, lines, readiness = plant
    todo = fix_first(readiness, lines)
    order = list(todo["status"])
    assert order.index(UNKNOWN) < order.index(CRITICAL) < order.index(LOW)
    assert OK not in order
    assert {"SC-01", "BE-01"} <= set(todo[todo.issue == "no parts list recorded"].machine_id)


def test_a_proposal_changes_nothing_until_approved(plant):
    machines, parts, bom, *_ = plant
    p = new_proposal("SC-01", "sp-1601", 3, "worn flights", "Inspector")
    assert p["part_no"] == "SP-1601" and p["status"] == "pending"
    assert apply_approved(bom, [p]).equals(bom)

    p["status"] = "approved"
    updated = apply_approved(bom, [p])
    lines = part_lines(machines, parts, updated)
    readiness = machine_readiness(machines, lines)
    # SC-01 goes from unknown to a known gap: flights are a wear part with zero stock
    assert status(readiness, "SC-01") == LOW


def test_a_rejected_proposal_never_reaches_the_parts_list(plant):
    *_, bom, _, _ = plant
    p = new_proposal("SC-01", "SP-1601", 3, "", "Inspector")
    p["status"] = "rejected"
    assert apply_approved(bom, [p]).equals(bom)


def test_a_proposal_needs_who_and_what():
    with pytest.raises(ValueError):
        new_proposal("SC-01", "  ", 1, "", "Inspector")
    with pytest.raises(ValueError):
        new_proposal("SC-01", "SP-1", 1, "", "")


def test_upload_validation_names_what_is_missing():
    frames = {"machines": demo_machines(), "parts": demo_parts().drop(columns="stock_se")}
    problems = missing_columns(frames)
    assert "sheet 'bom' is missing" in problems
    assert any("stock_se" in p for p in problems)
    assert missing_columns({"machines": demo_machines(), "parts": demo_parts(),
                            "bom": demo_bom()}) == []


def test_every_machine_gets_exactly_one_status(plant):
    machines, *_, readiness = plant
    assert len(readiness) == len(machines)
    assert set(readiness["status"]) <= {OK, LOW, CRITICAL, UNKNOWN}
