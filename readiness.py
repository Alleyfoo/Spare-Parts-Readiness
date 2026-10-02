"""Spare parts readiness: which machines could we fix today?

The machine list says what is installed. The parts list (BOM) says what each
machine needs. Stock says what is on the shelf. The gap is the answer.

    intention   the machine's parts list: what it would need to be repaired
    truth       stock in the Finnish and Swedish warehouses
    gap         a critical spare at zero, a wear part running low,
                or no parts list at all

A machine with no parts list is not "fine". It is unknown, and it is shown as
unknown. That is the most common real situation and the most useful thing to
see.

Pure functions over pandas frames, so the logic is testable without Streamlit.
All data is synthetic: a generic process plant with generic conveyor parts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

# Status order matters: the worst one wins for a machine.
OK, LOW, CRITICAL, UNKNOWN = "ok", "low", "critical", "unknown"
SEVERITY = {UNKNOWN: 3, CRITICAL: 2, LOW: 1, OK: 0}
LABEL = {
    OK: "Parts covered",
    LOW: "Wear part running low",
    CRITICAL: "Critical spare at zero",
    UNKNOWN: "No parts list",
}

REQUIRED_COLUMNS = {
    "machines": ["machine_id", "name", "type", "area", "criticality", "x0", "y0", "x1", "y1"],
    "parts": ["part_no", "description", "category", "wear_part", "lead_time_days",
              "stock_fi", "stock_se"],
    "bom": ["machine_id", "part_no", "qty_installed", "critical"],
}


# -- synthetic plant ------------------------------------------------------


def demo_machines() -> pd.DataFrame:
    """A generic plant: raw material in, crushing, screening, storage, boiler feed."""
    rows = [
        # id, name, type, area, criticality, x0, y0, x1, y1, parts list source
        ("BC-01", "Receiving conveyor", "Belt conveyor", "Receiving", "A", 0.5, 4, 3.5, 4, "Inspection 03/2026"),
        ("CR-01", "Primary crusher", "Crusher", "Crushing", "A", 5.2, 4, 6.2, 4, "OEM manual"),
        ("BC-02", "Crusher discharge conveyor", "Belt conveyor", "Crushing", "A", 6.9, 4, 8.8, 2, "Inspection 03/2026"),
        ("SC-01", "Screen feed screw", "Screw conveyor", "Screening", "B", 10.3, 2, 11.7, 2, None),
        ("BC-03", "Screen oversize return", "Belt conveyor", "Screening", "B", 12.3, 2, 13.7, 4.6, "Inspection 03/2026"),
        ("BC-04", "Stockpile conveyor", "Belt conveyor", "Storage", "B", 15.3, 2, 17.7, 0.6, "Inspection 11/2025"),
        ("BE-01", "Boiler feed elevator", "Bucket elevator", "Boiler feed", "A", 19.5, 0.6, 19.5, 4.6, None),
        ("BC-05", "Boiler day-bin conveyor", "Belt conveyor", "Boiler feed", "A", 20.2, 4.6, 22.8, 4.6, "OEM manual"),
    ]
    cols = ["machine_id", "name", "type", "area", "criticality",
            "x0", "y0", "x1", "y1", "parts_list_source"]
    return pd.DataFrame(rows, columns=cols)


def demo_parts() -> pd.DataFrame:
    """Generic conveyor spares. Stock is shared by every machine that uses a part."""
    rows = [
        # part_no, description, category, wear, lead days, stock FI, stock SE
        ("SP-1001", "Conveyor belt EP630/4, 800 mm, per m", "Belt", True, 42, 60, 0),
        ("SP-1002", "Conveyor belt EP800/4, 1000 mm, per m", "Belt", True, 49, 0, 25),
        ("SP-1101", "Carrying idler 3-roll set, 800 mm", "Idler", True, 14, 18, 6),
        ("SP-1102", "Return idler, 800 mm", "Idler", True, 14, 4, 2),
        ("SP-1103", "Carrying idler 3-roll set, 1000 mm", "Idler", True, 21, 0, 8),
        ("SP-1104", "Impact idler set, 1000 mm", "Idler", True, 28, 2, 0),
        ("SP-1201", "Drive pulley, lagged, 500 mm", "Pulley", False, 70, 0, 0),
        ("SP-1202", "Tail pulley, 400 mm", "Pulley", False, 56, 1, 0),
        ("SP-1203", "Drive pulley, lagged, 630 mm", "Pulley", False, 84, 0, 1),
        ("SP-1301", "Spherical roller bearing 22216", "Bearing", True, 7, 6, 4),
        ("SP-1302", "Plummer block housing SNL 516", "Bearing", False, 10, 2, 1),
        ("SP-1303", "Spherical roller bearing 22220", "Bearing", True, 7, 0, 0),
        ("SP-1401", "Primary belt scraper blade, 800 mm", "Scraper", True, 10, 3, 0),
        ("SP-1402", "Primary belt scraper blade, 1000 mm", "Scraper", True, 10, 0, 2),
        ("SP-1501", "Helical bevel gearbox, 15 kW", "Drive", False, 98, 0, 0),
        ("SP-1502", "Electric motor 15 kW IE3", "Drive", False, 35, 1, 0),
        ("SP-1503", "Flexible coupling, size 5", "Drive", True, 14, 2, 2),
        ("SP-1601", "Screw flight section, 400 mm", "Screw", True, 45, 0, 0),
        ("SP-1701", "Elevator bucket, 300 mm", "Elevator", True, 30, 40, 0),
        ("SP-1702", "Elevator belt, per m", "Elevator", True, 60, 0, 0),
        ("SP-1801", "Crusher jaw plate, fixed", "Crusher", True, 63, 1, 0),
        ("SP-1802", "Crusher jaw plate, moving", "Crusher", True, 63, 0, 0),
        ("SP-1803", "Crusher V-belt set", "Crusher", True, 5, 4, 0),
    ]
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS["parts"])


def demo_bom() -> pd.DataFrame:
    """Which parts each machine uses. SC-01 and BE-01 have none recorded."""
    rows = [
        ("BC-01", "SP-1001", 18, False), ("BC-01", "SP-1101", 12, False),
        ("BC-01", "SP-1102", 5, False), ("BC-01", "SP-1201", 1, True),
        ("BC-01", "SP-1202", 1, False), ("BC-01", "SP-1301", 4, True),
        ("BC-01", "SP-1401", 1, False), ("BC-01", "SP-1501", 1, True),
        ("CR-01", "SP-1801", 1, True), ("CR-01", "SP-1802", 1, True),
        ("CR-01", "SP-1803", 1, False), ("CR-01", "SP-1303", 2, True),
        ("BC-02", "SP-1002", 14, False), ("BC-02", "SP-1103", 9, False),
        ("BC-02", "SP-1104", 4, False), ("BC-02", "SP-1203", 1, True),
        ("BC-02", "SP-1301", 4, True), ("BC-02", "SP-1402", 1, False),
        ("BC-02", "SP-1502", 1, True),
        ("BC-03", "SP-1001", 12, False), ("BC-03", "SP-1101", 8, False),
        ("BC-03", "SP-1102", 3, False), ("BC-03", "SP-1202", 1, False),
        ("BC-03", "SP-1301", 2, True),
        ("BC-04", "SP-1001", 9, False), ("BC-04", "SP-1101", 6, False),
        ("BC-04", "SP-1102", 2, False), ("BC-04", "SP-1503", 1, True),
        ("BC-04", "SP-1999", 1, False),  # not in the item master: a broken reference
        ("BC-05", "SP-1001", 8, False), ("BC-05", "SP-1101", 5, False),
        ("BC-05", "SP-1401", 1, False), ("BC-05", "SP-1301", 2, True),
        ("BC-05", "SP-1503", 1, True),
    ]
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS["bom"])


# -- validation ------------------------------------------------------------


def missing_columns(frames: dict[str, pd.DataFrame]) -> list[str]:
    """What an uploaded workbook lacks, sheet by sheet. Empty means usable."""
    problems = []
    for sheet, required in REQUIRED_COLUMNS.items():
        if sheet not in frames:
            problems.append(f"sheet '{sheet}' is missing")
            continue
        absent = [c for c in required if c not in frames[sheet].columns]
        if absent:
            problems.append(f"sheet '{sheet}' lacks: {', '.join(absent)}")
    return problems


# -- readiness ---------------------------------------------------------------


def part_lines(machines: pd.DataFrame, parts: pd.DataFrame, bom: pd.DataFrame) -> pd.DataFrame:
    """One row per machine and part, with stock and a status per line."""
    lines = bom.merge(parts, on="part_no", how="left", indicator=True)
    lines["in_item_master"] = lines["_merge"] == "both"
    lines = lines.drop(columns="_merge")
    lines["stock_total"] = lines["stock_fi"].fillna(0) + lines["stock_se"].fillna(0)
    lines["status"] = lines.apply(_line_status, axis=1)
    lines["note"] = lines.apply(_line_note, axis=1)
    order = machines[["machine_id"]].reset_index().rename(columns={"index": "_m"})
    return lines.merge(order, on="machine_id").sort_values(["_m", "part_no"]).drop(columns="_m")


def _line_status(line) -> str:
    if not line["in_item_master"]:
        return UNKNOWN
    if line["critical"] and line["stock_total"] <= 0:
        return CRITICAL
    if line["wear_part"] and line["stock_total"] < line["qty_installed"]:
        return LOW
    return OK


def _line_note(line) -> str:
    if not line["in_item_master"]:
        return "part number not in the item master"
    if line["critical"] and line["stock_total"] <= 0:
        return f"none in stock, lead time {int(line['lead_time_days'])} days"
    if line["wear_part"] and line["stock_total"] < line["qty_installed"]:
        return f"{int(line['stock_total'])} in stock, {int(line['qty_installed'])} installed"
    if line["stock_fi"] <= 0 < line["stock_se"]:
        return "stock in Sweden only"
    return ""


@dataclass(frozen=True)
class MachineReadiness:
    machine_id: str
    status: str
    critical_gaps: int
    low_lines: int
    unknown_lines: int
    parts_listed: int


def machine_readiness(machines: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """The worst line wins. No parts list at all is UNKNOWN, never OK."""
    rows = []
    for machine_id in machines["machine_id"]:
        mine = lines[lines["machine_id"] == machine_id]
        if mine.empty:
            status = UNKNOWN
        else:
            status = max(mine["status"], key=SEVERITY.get)
        rows.append(MachineReadiness(
            machine_id=machine_id,
            status=status,
            critical_gaps=int((mine["status"] == CRITICAL).sum()),
            low_lines=int((mine["status"] == LOW).sum()),
            unknown_lines=int((mine["status"] == UNKNOWN).sum()),
            parts_listed=len(mine),
        ).__dict__)
    return machines.merge(pd.DataFrame(rows), on="machine_id")


def fix_first(readiness: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """Everything a person should look at, worst first, A-criticality machines first."""
    items = []
    for _, m in readiness.iterrows():
        if m["parts_listed"] == 0:
            items.append({"machine_id": m["machine_id"], "machine": m["name"],
                          "criticality": m["criticality"], "status": UNKNOWN,
                          "part_no": "", "issue": "no parts list recorded"})
    for _, line in lines[lines["status"] != OK].iterrows():
        m = readiness[readiness["machine_id"] == line["machine_id"]].iloc[0]
        items.append({"machine_id": line["machine_id"], "machine": m["name"],
                      "criticality": m["criticality"], "status": line["status"],
                      "part_no": line["part_no"],
                      "issue": f"{line['description'] if line['in_item_master'] else line['part_no']}: {line['note']}"})
    if not items:
        return pd.DataFrame(columns=["machine_id", "machine", "criticality", "status", "part_no", "issue"])
    out = pd.DataFrame(items)
    out["_s"] = out["status"].map(SEVERITY)
    return out.sort_values(["_s", "criticality", "machine_id"], ascending=[False, True, True]).drop(columns="_s")


# -- proposals: how a gap gets filled ----------------------------------------


def new_proposal(machine_id: str, part_no: str, qty: int, note: str, proposed_by: str) -> dict:
    """An inspector's finding becomes a proposal. It changes no parts list by itself."""
    if not machine_id or not part_no.strip() or qty < 1 or not proposed_by.strip():
        raise ValueError("a proposal needs a machine, a part number, a quantity and a name")
    return {
        "machine_id": machine_id,
        "part_no": part_no.strip().upper(),
        "qty_installed": int(qty),
        "note": note.strip(),
        "proposed_by": proposed_by.strip(),
        "proposed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "pending",
    }


def apply_approved(bom: pd.DataFrame, proposals: list[dict]) -> pd.DataFrame:
    """Only approved proposals reach the parts list, and only as non-critical lines."""
    approved = [p for p in proposals if p["status"] == "approved"]
    if not approved:
        return bom
    added = pd.DataFrame([{"machine_id": p["machine_id"], "part_no": p["part_no"],
                           "qty_installed": p["qty_installed"], "critical": False}
                          for p in approved])
    return pd.concat([bom, added], ignore_index=True)
