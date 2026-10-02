"""Spare Parts Readiness: hover a machine, see what it needs and what we have.

    streamlit run app.py

All data is synthetic. See readiness.py for the logic.
"""

from html import escape
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from readiness import (
    CRITICAL, LABEL, LOW, OK, UNKNOWN, REQUIRED_COLUMNS,
    apply_approved, demo_bom, demo_machines, demo_parts, fix_first,
    machine_readiness, missing_columns, new_proposal, part_lines,
)

COLOUR = {OK: "#2e7d32", LOW: "#e0a100", CRITICAL: "#c62828", UNKNOWN: "#9e9e9e"}
DOT = {OK: "●", LOW: "●", CRITICAL: "●", UNKNOWN: "○"}
AREA_COLOUR = "rgba(120,130,150,0.07)"
MAX_HOVER_LINES = 9

st.set_page_config(page_title="Spare Parts Readiness", layout="wide")


# -- data ---------------------------------------------------------------------


def workbook(frames: dict[str, pd.DataFrame]) -> bytes:
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return out.getvalue()


def load_data() -> tuple[dict[str, pd.DataFrame], str]:
    demo = {"machines": demo_machines(), "parts": demo_parts(), "bom": demo_bom()}
    st.sidebar.download_button(
        "Download data as Excel template", workbook(demo),
        file_name="spare_parts_readiness_template.xlsx",
        help="Three sheets: machines, parts, bom. Fill with your own and upload.",
    )
    upload = st.sidebar.file_uploader("Or upload your own workbook", type=["xlsx"])
    if upload is None:
        return demo, "Synthetic demo plant"
    try:
        frames = pd.read_excel(upload, sheet_name=None)
    except Exception as exc:  # a bad file must not take the app down
        st.sidebar.error(f"Could not read the file: {exc}")
        return demo, "Synthetic demo plant (upload failed)"
    problems = missing_columns(frames)
    if problems:
        st.sidebar.error("Upload not used:\n- " + "\n- ".join(problems))
        return demo, "Synthetic demo plant (upload incomplete)"
    return {k: frames[k] for k in REQUIRED_COLUMNS}, upload.name


# -- plant layout -------------------------------------------------------------


def hover_text(machine: pd.Series, mine: pd.DataFrame) -> str:
    head = (f"<b>{escape(machine['machine_id'])}  {escape(machine['name'])}</b><br>"
            f"{escape(machine['type'])} · criticality {machine['criticality']}<br>"
            f"<span style='color:{COLOUR[machine['status']]}'><b>{LABEL[machine['status']]}</b></span><br>")
    if mine.empty:
        return head + "<br><i>No parts list recorded for this machine.<br>We cannot say what it needs.</i>"
    rows = []
    worst_first = mine.assign(_s=mine["status"].map({UNKNOWN: 0, CRITICAL: 1, LOW: 2, OK: 3})).sort_values("_s")
    for _, line in worst_first.head(MAX_HOVER_LINES).iterrows():
        name = line["description"] if line["in_item_master"] else f"{line['part_no']} (not in item master)"
        stock = ("" if not line["in_item_master"]
                 else f"  FI {int(line['stock_fi'])} / SE {int(line['stock_se'])}")
        flag = " ★" if line["critical"] else ""
        rows.append(f"<span style='color:{COLOUR[line['status']]}'>{DOT[line['status']]}</span> "
                    f"{escape(str(name))[:42]}{flag} ×{int(line['qty_installed'])}{stock}")
    more = len(mine) - MAX_HOVER_LINES
    tail = f"<br>… and {more} more" if more > 0 else ""
    return head + "<br>" + "<br>".join(rows) + tail + "<br><br><i>★ critical spare</i>"


def plant_figure(readiness: pd.DataFrame, lines: pd.DataFrame, selected: str | None) -> go.Figure:
    fig = go.Figure()
    for area, group in readiness.groupby("area", sort=False):
        xs = pd.concat([group["x0"], group["x1"]])
        ys = pd.concat([group["y0"], group["y1"]])
        fig.add_shape(type="rect", x0=xs.min() - 0.5, x1=xs.max() + 0.5,
                      y0=-0.6, y1=5.8,
                      fillcolor=AREA_COLOUR, line=dict(width=0), layer="below")
        fig.add_annotation(x=xs.min() - 0.4, y=-0.45, text=area.upper(),
                           showarrow=False, xanchor="left", yanchor="bottom",
                           font=dict(size=10, color="#7a8090"))

    for _, m in readiness.iterrows():
        width = 14 if m["machine_id"] == selected else 9
        fig.add_trace(go.Scatter(
            x=[m["x0"], m["x1"]], y=[m["y0"], m["y1"]], mode="lines",
            line=dict(color=COLOUR[m["status"]], width=width), hoverinfo="skip",
            showlegend=False,
        ))

    mid_x = (readiness["x0"] + readiness["x1"]) / 2
    mid_y = (readiness["y0"] + readiness["y1"]) / 2
    texts = [hover_text(m, lines[lines["machine_id"] == m["machine_id"]])
             for _, m in readiness.iterrows()]
    fig.add_trace(go.Scatter(
        x=mid_x, y=mid_y, mode="markers+text",
        marker=dict(size=26, color="white",
                    line=dict(width=3, color=[COLOUR[s] for s in readiness["status"]]),
                    symbol="square"),
        text=readiness["machine_id"], textposition="top center",
        textfont=dict(size=11, color="#30343c"),
        customdata=readiness[["machine_id"]].values,
        hovertext=texts, hovertemplate="%{hovertext}<extra></extra>",
        showlegend=False,
    ))
    for status in (OK, LOW, CRITICAL, UNKNOWN):  # legend only
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=LABEL[status],
                                 line=dict(color=COLOUR[status], width=8)))
    fig.update_layout(
        height=470, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
        xaxis=dict(visible=False, range=[-0.6, 23.4]),
        yaxis=dict(visible=False, range=[-0.8, 6.0]),
        hoverlabel=dict(bgcolor="white", align="left", font_size=12,
                        bordercolor="#c9ced8"),
        legend=dict(orientation="h", y=-0.02, x=0),
    )
    return fig


# -- proposals ----------------------------------------------------------------


def proposals_panel(machines: pd.DataFrame) -> None:
    proposals = st.session_state.setdefault("proposals", [])
    audit = st.session_state.setdefault("audit", [])

    with st.expander("Inspector: record a part found on site"):
        st.caption("A finding becomes a proposal. It changes no parts list until someone approves it.")
        with st.form("propose", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 1.2, 0.8])
            machine = c1.selectbox("Machine", machines["machine_id"] + "  " + machines["name"])
            part_no = c2.text_input("Part number", placeholder="SP-1601")
            qty = c3.number_input("Installed", min_value=1, value=1)
            note = st.text_input("Note", placeholder="Seen during inspection, flight worn")
            who = st.text_input("Your name", placeholder="Inspector")
            if st.form_submit_button("Propose"):
                try:
                    p = new_proposal(machine.split()[0], part_no, int(qty), note, who)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    proposals.append(p)
                    audit.append({"when": p["proposed_at"], "who": p["proposed_by"],
                                  "action": "proposed", "what": f"{p['part_no']} ×{p['qty_installed']} on {p['machine_id']}"})
                    st.success("Proposed. Waiting for approval.")

    pending = [p for p in proposals if p["status"] == "pending"]
    with st.expander(f"Approver: {len(pending)} pending"):
        st.caption("In production this is a separate role with its own login.")
        for i, p in enumerate(proposals):
            if p["status"] != "pending":
                continue
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.write(f"**{p['part_no']}** ×{p['qty_installed']} on **{p['machine_id']}**, "
                     f"by {p['proposed_by']}. {p['note']}")
            for col, verdict in ((c2, "approved"), (c3, "rejected")):
                if col.button(verdict[:-1].capitalize(), key=f"{verdict}-{i}"):
                    p["status"] = verdict
                    audit.append({"when": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
                                  "who": "Approver", "action": verdict,
                                  "what": f"{p['part_no']} ×{p['qty_installed']} on {p['machine_id']}"})
                    st.rerun()
        if audit:
            st.markdown("**Audit log**")
            st.dataframe(pd.DataFrame(audit), hide_index=True, use_container_width=True)


# -- page -----------------------------------------------------------------------


def main() -> None:
    st.sidebar.title("Spare Parts Readiness")
    data, source = load_data()
    st.sidebar.caption(f"Data: {source}")
    st.sidebar.caption("All demo data is synthetic: a generic plant with generic conveyor parts.")

    bom = apply_approved(data["bom"], st.session_state.get("proposals", []))
    lines = part_lines(data["machines"], data["parts"], bom)
    readiness = machine_readiness(data["machines"], lines)

    st.markdown("### Which machines could we repair today?")
    st.caption("Machine list = what is installed · parts list = what it needs · "
               "stock = what is on the shelf. Hover a machine; pick it on the right for details.")

    counts = readiness["status"].value_counts()
    k = st.columns(5)
    k[0].metric("Machines", len(readiness))
    for col, status in zip(k[1:], (OK, LOW, CRITICAL, UNKNOWN)):
        col.metric(LABEL[status], int(counts.get(status, 0)))

    left, right = st.columns([3, 2], gap="large")
    with left:
        selected = st.session_state.get("selected")
        st.plotly_chart(plant_figure(readiness, lines, selected), key="plant",
                        use_container_width=True, config={"displayModeBar": False})

    with right:
        ids = list(readiness["machine_id"])
        current = st.session_state.get("selected") or ids[0]
        choice = st.selectbox("Machine", ids, index=ids.index(current),
                              format_func=lambda i: f"{i}  {readiness.set_index('machine_id').loc[i, 'name']}")
        st.session_state["selected"] = choice
        m = readiness.set_index("machine_id").loc[choice]
        st.markdown(f"<span style='color:{COLOUR[m['status']]};font-weight:600'>"
                    f"{LABEL[m['status']]}</span> · {m['type']} · {m['area']} · "
                    f"criticality {m['criticality']}", unsafe_allow_html=True)
        source_note = m.get("parts_list_source")
        if isinstance(source_note, str):
            st.caption(f"Parts list source: {source_note}")
        mine = lines[lines["machine_id"] == choice]
        if mine.empty:
            st.warning("No parts list recorded. This machine's needs are unknown, "
                       "which is not the same as covered. An inspection can fill it in.")
        else:
            table = mine.assign(
                part=mine["description"].fillna("(not in item master)"),
                state=mine["status"].map(LABEL),
                critical=mine["critical"].map({True: "★", False: ""}),
            )[["part_no", "part", "critical", "qty_installed", "stock_fi", "stock_se",
               "lead_time_days", "state", "note"]]
            st.dataframe(table, hide_index=True, use_container_width=True,
                         column_config={"qty_installed": "installed", "stock_fi": "FI",
                                        "stock_se": "SE", "lead_time_days": "lead (d)"})

    st.markdown("#### Fix first")
    todo = fix_first(readiness, lines)
    if todo.empty:
        st.success("Every listed part is covered.")
    else:
        st.dataframe(todo.assign(status=todo["status"].map(LABEL)), hide_index=True,
                     use_container_width=True)

    proposals_panel(data["machines"])


main()
