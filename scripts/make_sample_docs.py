"""
Regenerates the sample documents in ./sample-docs.

They are deliberately built to exercise every path in the pipeline: ruled
tables (structured-fact extraction), an embedded block diagram (figure
extraction), multi-page prose (deep retrieval), two datasheets that disagree
(cross-document comparison), and a requirements doc whose limits conflict with
one of them. Nothing in them mentions CAN bus, Modbus, or USB - those make
good "does it admit what it doesn't know" probes.

    python -m scripts.make_sample_docs
"""
import fitz
from docx import Document
from docx.shared import Pt
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample-docs"
OUT.mkdir(parents=True, exist_ok=True)


def block_diagram_png(path):
    """Render a real block diagram to PNG so figure extraction has something true to find."""
    d = fitz.open()
    p = d.new_page(width=420, height=260)
    boxes = [(20, 60, 110, 110, "24V INPUT"), (150, 60, 250, 110, "PC-42 LDO"),
             (290, 60, 400, 110, "3V3 LOGIC RAIL"), (150, 160, 250, 210, "THERMAL\nSHUTDOWN")]
    for x0, y0, x1, y1, label in boxes:
        p.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0.1, 0.2, 0.5), width=1.5)
        for i, line in enumerate(label.split("\n")):
            p.insert_text((x0 + 8, y0 + 22 + i * 12), line, fontsize=8)
    for a, b in [((110, 85), (150, 85)), ((250, 85), (290, 85)), ((200, 110), (200, 160))]:
        p.draw_line(fitz.Point(*a), fitz.Point(*b), color=(0, 0, 0), width=1.2)
    p.insert_text((20, 240), "Figure 1: PC-42 power subsystem block diagram", fontsize=9)
    pix = p.get_pixmap(matrix=fitz.Matrix(2, 2))
    pix.save(path)
    d.close()


def ruled_table(page, x0, y0, rows, col_w=(230, 150)):
    """Draw a ruled table so PyMuPDF's find_tables() detects it."""
    rh = 22
    for r, row in enumerate(rows):
        y = y0 + r * rh
        x = x0
        for c, cell in enumerate(row):
            w = col_w[c]
            page.draw_rect(fitz.Rect(x, y, x + w, y + rh), color=(0.3, 0.3, 0.3), width=0.8)
            page.insert_text((x + 6, y + 15), cell, fontsize=9,
                             fontname="hebo" if r == 0 else "helv")
            x += w
    return y0 + len(rows) * rh


# ---------- Datasheet A: PC-42 LDO regulator (PDF, 3 pages, table + figure) ----------
doc = fitz.open()
p = doc.new_page()
p.insert_text((60, 70), "PowerCell PC-42", fontsize=22)
p.insert_text((60, 95), "Low-Dropout Linear Regulator - Datasheet Rev C", fontsize=11)
p.insert_textbox(fitz.Rect(60, 120, 540, 260),
    "The PowerCell PC-42 is a low-dropout linear regulator designed for noise-sensitive "
    "analog and mixed-signal rails in industrial control equipment. It accepts a wide "
    "6 V to 24 V input and delivers a fixed 3.3 V output at up to 1.5 A continuous. "
    "Dropout voltage is 310 mV at full load. The device integrates thermal shutdown, "
    "current limiting, and reverse-polarity protection.\n\n"
    "Because the PC-42 is a linear topology, power dissipation is the input-to-output "
    "differential multiplied by load current. At 24 V input and 1.5 A load the device "
    "dissipates 31 W, which exceeds the package rating without a heatsink; the "
    "recommended maximum input for continuous full-load operation is 12 V.", fontsize=10)
p.insert_text((60, 300), "Table 1: Absolute Maximum Ratings", fontsize=11)
ruled_table(p, 60, 315, [
    ("Parameter", "Value"),
    ("Input voltage range", "6 V to 24 V"),
    ("Output voltage", "3.3 V fixed"),
    ("Continuous output current", "1.5 A"),
    ("Dropout voltage at 1.5 A", "310 mV"),
    ("Thermal shutdown threshold", "150 C"),
    ("Quiescent current", "45 uA"),
    ("Operating temperature range", "-40 C to +125 C"),
])

p2 = doc.new_page()
p2.insert_text((60, 70), "Figure 1: PC-42 power subsystem block diagram", fontsize=11)
png = OUT / ".blockdiagram.tmp.png"
block_diagram_png(str(png))
p2.insert_image(fitz.Rect(60, 90, 480, 350), filename=str(png))
p2.insert_textbox(fitz.Rect(60, 370, 540, 520),
    "The 24 V bulk rail enters through a reverse-polarity FET and is regulated down to "
    "the 3V3 logic rail. The thermal shutdown block monitors junction temperature and "
    "disables the pass element at 150 C, re-enabling with 15 C of hysteresis.\n\n"
    "Efficiency at nominal 12 V input and 3.3 V output is 27 percent, which is inherent "
    "to linear regulation and not a defect of this part.", fontsize=10)

p3 = doc.new_page()
p3.insert_text((60, 70), "Application Notes", fontsize=14)
p3.insert_textbox(fitz.Rect(60, 95, 540, 400),
    "Output capacitor selection: the PC-42 requires a minimum 10 uF ceramic output "
    "capacitor with ESR below 100 mOhm for stability. X7R dielectric is recommended "
    "over Y5V because of Y5V's bias-voltage derating.\n\n"
    "Layout: keep the feedback trace away from the switching node of any upstream "
    "converter. The exposed pad must be tied to the ground plane with at least nine "
    "thermal vias.\n\n"
    "Qualification: the PC-42 is AEC-Q100 Grade 1 qualified and carries a 10-year "
    "supply commitment from the date of Rev C release.", fontsize=10)
doc.save(str(OUT / "PC-42_datasheet.pdf"))
doc.close()

# ---------- Datasheet B: VE-9 switching regulator (PDF, 2 pages, table) ----------
doc = fitz.open()
p = doc.new_page()
p.insert_text((60, 70), "VoltEdge VE-9", fontsize=22)
p.insert_text((60, 95), "Synchronous Buck Regulator - Datasheet Rev A", fontsize=11)
p.insert_textbox(fitz.Rect(60, 120, 540, 250),
    "The VoltEdge VE-9 is a synchronous buck converter targeting the same 3.3 V logic "
    "rails as traditional linear parts, but at substantially higher efficiency. It "
    "accepts 4.5 V to 36 V input and delivers up to 3 A continuous at 94 percent peak "
    "efficiency, switching at 500 kHz.\n\n"
    "Unlike a linear regulator, the VE-9 injects switching ripple onto the output rail: "
    "35 mV peak-to-peak typical at full load. Noise-sensitive analog sections may "
    "require post-regulation or additional filtering.", fontsize=10)
p.insert_text((60, 290), "Table 1: Electrical Characteristics", fontsize=11)
ruled_table(p, 60, 305, [
    ("Parameter", "Value"),
    ("Input voltage range", "4.5 V to 36 V"),
    ("Output voltage", "3.3 V adjustable"),
    ("Continuous output current", "3 A"),
    ("Peak efficiency", "94 percent"),
    ("Switching frequency", "500 kHz"),
    ("Output ripple at full load", "35 mV pp"),
    ("Thermal shutdown threshold", "165 C"),
    ("Quiescent current", "12 uA"),
])
p2 = doc.new_page()
p2.insert_text((60, 70), "Reliability and Supply", fontsize=14)
p2.insert_textbox(fitz.Rect(60, 95, 540, 320),
    "The VE-9 is qualified to AEC-Q100 Grade 2 only, and is not rated for the -40 C to "
    "+125 C ambient range required by Grade 1 designs. Sustained operation above +105 C "
    "ambient is outside the datasheet envelope.\n\n"
    "The VE-9 entered volume production in Q1 and carries a 5-year supply commitment. "
    "Lead time is currently 22 weeks.", fontsize=10)
doc.save(str(OUT / "VE-9_datasheet.pdf"))
doc.close()

# ---------- DOCX: system requirements with tables ----------
d = Document()
d.add_heading("Orion Controller - Power Subsystem Requirements", level=1)
d.add_paragraph("This document captures the binding requirements for the Orion "
                "industrial controller power subsystem. Any regulator selected for "
                "the 3.3 V logic rail must satisfy every requirement in Table 1.")
d.add_heading("Table 1: Binding Requirements", level=2)
t = d.add_table(rows=0, cols=2)
for label, value in [
    ("Requirement ID prefix", "ORN-PWR"),
    ("Logic rail voltage", "3.3 V plus or minus 2 percent"),
    ("Minimum continuous current", "2.0 A"),
    ("Maximum output ripple", "20 mV pp"),
    ("Required qualification", "AEC-Q100 Grade 1"),
    ("Required supply commitment", "10 years minimum"),
    ("Maximum lead time", "16 weeks"),
    ("Ambient temperature range", "-40 C to +125 C"),
]:
    row = t.add_row()
    row.cells[0].text, row.cells[1].text = label, value
d.add_heading("Notes", level=2)
d.add_paragraph("The 20 mV ripple limit is driven by the 16-bit ADC on the sensor "
                "board. Requirement ORN-PWR-014 states that any switching regulator "
                "must be followed by post-regulation if this limit cannot be met "
                "directly.")
d.save(str(OUT / "Orion_requirements.docx"))

png.unlink(missing_ok=True)  # intermediate used to build the PDF, not a sample

for f in sorted(OUT.glob("*")):
    print(f"  {f.name}  ({f.stat().st_size//1024} KB)")
