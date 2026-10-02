# Spare Parts Readiness

**Which machines could we repair today?**

A plant layout where every machine is coloured by whether its spare parts are
covered. Hover a machine and a floating box lists its parts, worst first, with
stock in the Finnish and Swedish warehouses.

```
machine list   what is installed
parts list     what each machine needs        (intention)
stock          what is on the shelf           (truth)
gap            what to fix first
```

Same idea as [Campaign Readiness Monitor](https://github.com/Alleyfoo/Campaign-Readiness-Monitor):
the plan is the intention, the system is the truth, and the screen shows the gap.

## What it shows

| Colour | Meaning |
| --- | --- |
| green | every listed part covered |
| yellow | a wear part below one full change |
| red | a critical spare (★) at zero in both countries |
| grey | **no parts list**, or a part number missing from the item master |

Grey is deliberate. A machine nobody has listed parts for is not "fine". Its
needs are unknown, and that is the most common real situation. It is shown
rather than hidden.

## How a gap gets filled

1. An inspector records a part found on site. It becomes a **proposal**.
2. An approver accepts or rejects it. Only approved proposals reach the parts list.
3. Every step goes to an **audit log** (who, when, what).

In the demo, approving *SP-1601 ×3 on SC-01* turns the screw conveyor from
grey (unknown) to yellow (known gap: flights at zero stock).

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
python -m pytest -q
```

**Your own data:** download the Excel template from the sidebar (sheets
`machines`, `parts`, `bom`), fill it and upload it. Missing sheets or columns
are named, and the demo data is used until the file is complete.

## Data

All data is synthetic: a generic process plant with generic conveyor parts.
No company's machines, part numbers or stock.

## Known limitation

Details are picked from the machine list beside the layout. Click-to-select on
the chart was dropped: with Streamlit 1.50 and Plotly 6 the click reaches
Plotly but the selection reaches Streamlit empty.
