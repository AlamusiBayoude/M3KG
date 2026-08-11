from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "pdf"
PDF_PATH = OUT_DIR / "M3KG_graphical_abstract.pdf"
SVG_PATH = OUT_DIR / "M3KG_graphical_abstract.svg"

W, H = 2656, 1062

PALETTE = {
    "bg": "#F7FAF5",
    "ink": "#0B2F25",
    "muted": "#5D6F68",
    "green": "#0F5A43",
    "green2": "#2E8B72",
    "mint": "#DFF3EB",
    "mint2": "#EEF9F4",
    "gold": "#D9A441",
    "red": "#B85C4A",
    "blue": "#5D7D8A",
    "purple": "#7B6AAE",
    "olive": "#6B8E23",
    "line": "#B8D5C9",
    "card": "#FFFFFF",
}


def c(hex_color: str) -> colors.Color:
    return colors.HexColor(hex_color)


def darker(hex_color: str, amount: float = 0.18) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{int(r * (1 - amount)):02X}{int(g * (1 - amount)):02X}{int(b * (1 - amount)):02X}"


class Svg:
    def __init__(self) -> None:
        self.parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
            "<defs>",
            '<marker id="arrow" markerWidth="7" markerHeight="7" refX="6.2" refY="3.5" orient="auto" markerUnits="strokeWidth">',
            f'<path d="M0.8,0.8 L6.2,3.5 L0.8,6.2 Z" fill="{PALETTE["green"]}"/>',
            "</marker>",
            '<filter id="softShadow" x="-15%" y="-15%" width="130%" height="130%">',
            '<feDropShadow dx="0" dy="9" stdDeviation="12" flood-color="#0F5A43" flood-opacity="0.10"/>',
            "</filter>",
            "</defs>",
        ]

    def add(self, text: str) -> None:
        self.parts.append(text)

    def rect(self, x, y, w, h, fill, stroke="none", sw=1, rx=18, opacity=1, filt=False) -> None:
        style = f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"'
        filt_attr = ' filter="url(#softShadow)"' if filt else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {style}{filt_attr}/>')

    def circle(self, x, y, r, fill, stroke="none", sw=1, opacity=1) -> None:
        self.add(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>'
        )

    def line(self, x1, y1, x2, y2, stroke, sw=4, dash=None, marker=False, opacity=1) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        marker_attr = ' marker-end="url(#arrow)"' if marker else ""
        self.add(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linecap="round" opacity="{opacity}"{dash_attr}{marker_attr}/>'
        )

    def path(self, d, fill="none", stroke="none", sw=1, opacity=1) -> None:
        self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>')

    def text(self, x, y, text, size, fill=None, weight="400", anchor="start", family="Arial, Helvetica, sans-serif") -> None:
        fill = fill or PALETTE["ink"]
        self.add(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{escape(text)}</text>'
        )

    def save(self, path: Path) -> None:
        self.add("</svg>")
        path.write_text("\n".join(self.parts), encoding="utf-8")


def round_rect_pdf(cv: canvas.Canvas, x, y, w, h, fill, stroke=None, sw=1, radius=18) -> None:
    cv.setFillColor(c(fill))
    cv.setStrokeColor(c(stroke or fill))
    cv.setLineWidth(sw)
    cv.roundRect(x, y, w, h, radius, fill=1, stroke=1 if stroke else 0)


def text_pdf(cv: canvas.Canvas, x, y, text, size, fill=None, bold=False, align="left") -> None:
    cv.setFillColor(c(fill or PALETTE["ink"]))
    cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    if align == "center":
        cv.drawCentredString(x, y, text)
    elif align == "right":
        cv.drawRightString(x, y, text)
    else:
        cv.drawString(x, y, text)


def line_pdf(cv: canvas.Canvas, x1, y1, x2, y2, stroke, sw=4, arrow=False) -> None:
    cv.setStrokeColor(c(stroke))
    cv.setLineWidth(sw)
    cv.setLineCap(1)
    cv.line(x1, y1, x2, y2)
    if arrow:
        angle = math.atan2(y2 - y1, x2 - x1)
        length = 18
        spread = 0.42
        p1 = (x2 - length * math.cos(angle - spread), y2 - length * math.sin(angle - spread))
        p2 = (x2 - length * math.cos(angle + spread), y2 - length * math.sin(angle + spread))
        cv.setFillColor(c(stroke))
        p = cv.beginPath()
        p.moveTo(x2, y2)
        p.lineTo(*p1)
        p.lineTo(*p2)
        p.close()
        cv.drawPath(p, fill=1, stroke=0)


def draw_logo_pdf(cv: canvas.Canvas, cx, cy, scale=1.0) -> None:
    r = 78 * scale
    cv.setFillColor(c(PALETTE["green"]))
    cv.circle(cx, cy, r, fill=1, stroke=0)
    text_pdf(cv, cx - 42 * scale, cy - 22 * scale, "M", 78 * scale, "#FFFFFF", bold=True)
    cv.setFillColor(c("#FFFFFF"))
    for ox, oy, rr in [(43, 45, 8), (67, 22, 8), (43, -1, 8), (41, -51, 7), (68, -34, 6), (72, -61, 6)]:
        cv.circle(cx + ox * scale, cy + oy * scale, rr * scale, fill=1, stroke=0)
    line_pdf(cv, cx + 43 * scale, cy + 45 * scale, cx + 67 * scale, cy + 22 * scale, "#FFFFFF", 4 * scale)
    line_pdf(cv, cx + 67 * scale, cy + 22 * scale, cx + 43 * scale, cy - 1 * scale, "#FFFFFF", 4 * scale)
    line_pdf(cv, cx + 41 * scale, cy - 51 * scale, cx + 68 * scale, cy - 34 * scale, "#FFFFFF", 3 * scale)
    line_pdf(cv, cx + 41 * scale, cy - 51 * scale, cx + 72 * scale, cy - 61 * scale, "#FFFFFF", 3 * scale)


def draw_logo_svg(svg: Svg, cx, cy, scale=1.0) -> None:
    r = 78 * scale
    svg.circle(cx, cy, r, PALETTE["green"])
    svg.text(cx - 42 * scale, cy + 25 * scale, "M", 78 * scale, "#FFFFFF", "700")
    for ox, oy, rr in [(43, -45, 8), (67, -22, 8), (43, 1, 8), (41, 51, 7), (68, 34, 6), (72, 61, 6)]:
        svg.circle(cx + ox * scale, cy + oy * scale, rr * scale, "#FFFFFF")
    svg.line(cx + 43 * scale, cy - 45 * scale, cx + 67 * scale, cy - 22 * scale, "#FFFFFF", 4 * scale)
    svg.line(cx + 67 * scale, cy - 22 * scale, cx + 43 * scale, cy + 1 * scale, "#FFFFFF", 4 * scale)
    svg.line(cx + 41 * scale, cy + 51 * scale, cx + 68 * scale, cy + 34 * scale, "#FFFFFF", 3 * scale)
    svg.line(cx + 41 * scale, cy + 51 * scale, cx + 72 * scale, cy + 61 * scale, "#FFFFFF", 3 * scale)


def draw_document_card_pdf(cv, x, y, w, h, title, subtitle, color_hex):
    round_rect_pdf(cv, x, y, w, h, "#FFFFFF", "#CFE6DC", 2, 18)
    cv.setFillColor(c(color_hex))
    cv.roundRect(x + 18, y + h - 48, 44, 34, 9, fill=1, stroke=0)
    cv.setFillColor(c("#FFFFFF"))
    cv.rect(x + 48, y + h - 25, 10, 10, fill=1, stroke=0)
    text_pdf(cv, x + 76, y + h - 38, title, 20, PALETTE["ink"], True)
    text_pdf(cv, x + 24, y + 22, subtitle, 15, PALETTE["muted"], False)


def draw_document_card_svg(svg, x, y, w, h, title, subtitle, color_hex):
    svg.rect(x, y, w, h, "#FFFFFF", "#CFE6DC", 2, 18)
    svg.rect(x + 18, y + 14, 44, 34, color_hex, rx=9)
    svg.path(f"M{x + 48},{y + 14} L{x + 62},{y + 28} L{x + 48},{y + 28} Z", "#FFFFFF")
    svg.text(x + 76, y + 38, title, 20, PALETTE["ink"], "700")
    svg.text(x + 24, y + h - 22, subtitle, 15, PALETTE["muted"])


def draw_node_pdf(cv, x, y, label, color_hex, r=52):
    cv.setFillColor(c(color_hex))
    cv.circle(x, y, r, fill=1, stroke=0)
    cv.setStrokeColor(c(darker(color_hex)))
    cv.setLineWidth(2)
    cv.circle(x, y, r, fill=0, stroke=1)
    text_pdf(cv, x, y - 7, label, 18, "#FFFFFF", True, "center")


def draw_node_svg(svg, x, y, label, color_hex, r=52):
    svg.circle(x, y, r, color_hex, darker(color_hex), 2)
    svg.text(x, y + 7, label, 18, "#FFFFFF", "700", "middle")


def draw_network_pdf(cv, cx, cy):
    nodes = [
        ("Taste", cx - 175, cy + 105, PALETTE["gold"]),
        ("Nature", cx + 20, cy + 160, PALETTE["red"]),
        ("Potency", cx + 195, cy + 55, PALETTE["blue"]),
        ("Function", cx + 165, cy - 115, PALETTE["green2"]),
        ("Indication", cx - 70, cy - 160, PALETTE["purple"]),
        ("Origin", cx - 210, cy - 40, PALETTE["olive"]),
    ]
    for _, x, y, col in nodes:
        line_pdf(cv, cx, cy, x, y, "#B8D5C9", 6)
    cv.setFillColor(c(PALETTE["mint"]))
    cv.circle(cx, cy, 82, fill=1, stroke=0)
    cv.setStrokeColor(c(PALETTE["green"]))
    cv.setLineWidth(3)
    cv.circle(cx, cy, 82, fill=0, stroke=1)
    draw_logo_pdf(cv, cx, cy + 6, 0.55)
    text_pdf(cv, cx, cy - 102, "M³KG", 27, PALETTE["green"], True, "center")
    for label, x, y, col in nodes:
        draw_node_pdf(cv, x, y, label, col)


def draw_network_svg(svg, cx, cy):
    nodes = [
        ("Taste", cx - 175, cy - 105, PALETTE["gold"]),
        ("Nature", cx + 20, cy - 160, PALETTE["red"]),
        ("Potency", cx + 195, cy - 55, PALETTE["blue"]),
        ("Function", cx + 165, cy + 115, PALETTE["green2"]),
        ("Indication", cx - 70, cy + 160, PALETTE["purple"]),
        ("Origin", cx - 210, cy + 40, PALETTE["olive"]),
    ]
    for _, x, y, _ in nodes:
        svg.line(cx, cy, x, y, "#B8D5C9", 6)
    svg.circle(cx, cy, 82, PALETTE["mint"], PALETTE["green"], 3)
    draw_logo_svg(svg, cx, cy - 6, 0.55)
    svg.text(cx, cy + 112, "M³KG", 27, PALETTE["green"], "700", "middle")
    for label, x, y, col in nodes:
        draw_node_svg(svg, x, y, label, col)


def draw_module_pdf(cv, x, y, w, h, title, color_hex):
    round_rect_pdf(cv, x, y, w, h, "#FFFFFF", "#D6E8DF", 2, 20)
    cv.setFillColor(c(color_hex))
    cv.circle(x + 38, y + h / 2, 15, fill=1, stroke=0)
    text_pdf(cv, x + 68, y + h / 2 - 7, title, 22, PALETTE["ink"], True)


def draw_module_svg(svg, x, y, w, h, title, color_hex):
    svg.rect(x, y, w, h, "#FFFFFF", "#D6E8DF", 2, 20)
    svg.circle(x + 38, y + h / 2, 15, color_hex)
    svg.text(x + 68, y + h / 2 + 8, title, 22, PALETTE["ink"], "700")


def draw_rule_pdf(cv, x, y, w, text, color_hex):
    round_rect_pdf(cv, x, y, w, 58, "#FFFDF6", color_hex, 2, 18)
    text_pdf(cv, x + 22, y + 21, text, 18, PALETTE["ink"], True)


def draw_rule_svg(svg, x, y, w, text, color_hex):
    svg.rect(x, y, w, 58, "#FFFDF6", color_hex, 2, 18)
    svg.text(x + 22, y + 37, text, 18, PALETTE["ink"], "700")


def draw_plant_pdf(cv, x, y):
    cv.setStrokeColor(c(PALETTE["green"]))
    cv.setLineWidth(7)
    cv.line(x, y - 90, x, y + 65)
    cv.setFillColor(c("#DFF3EB"))
    for dx, dy, sx, sy in [(-48, -15, -1, 1), (50, 20, 1, 1), (-42, 56, -1, 1), (36, 78, 1, 1)]:
        p = cv.beginPath()
        p.moveTo(x, y + dy)
        p.curveTo(x + sx * 40, y + dy + sy * 28, x + sx * 75, y + dy + sy * 28, x + dx, y + dy + sy * 78)
        p.curveTo(x + sx * 14, y + dy + sy * 42, x + sx * 2, y + dy + sy * 12, x, y + dy)
        p.close()
        cv.drawPath(p, fill=1, stroke=0)
    cv.setFillColor(c(PALETTE["green"]))
    cv.ellipse(x - 65, y - 112, x + 65, y - 82, fill=1, stroke=0)


def draw_plant_svg(svg, x, y):
    svg.line(x, y + 90, x, y - 65, PALETTE["green"], 7)
    for dx, dy, sx, sy in [(-48, 15, -1, -1), (50, -20, 1, -1), (-42, -56, -1, -1), (36, -78, 1, -1)]:
        d = (
            f"M{x},{y + dy} C{x + sx * 40},{y + dy + sy * 28} "
            f"{x + sx * 75},{y + dy + sy * 28} {x + dx},{y + dy + sy * 78} "
            f"C{x + sx * 14},{y + dy + sy * 42} {x + sx * 2},{y + dy + sy * 12} {x},{y + dy} Z"
        )
        svg.path(d, "#DFF3EB")
    svg.add(f'<ellipse cx="{x}" cy="{y + 97}" rx="65" ry="15" fill="{PALETTE["green"]}"/>')


def draw_molecule_network_pdf(cv, x, y):
    pts = [(x, y + 45), (x + 95, y + 75), (x + 170, y + 15), (x + 90, y - 55), (x - 15, y - 35)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (1, 3)]
    for a, b in edges:
        line_pdf(cv, pts[a][0], pts[a][1], pts[b][0], pts[b][1], "#B8D5C9", 5)
    for i, (px, py) in enumerate(pts):
        col = [PALETTE["gold"], PALETTE["green2"], PALETTE["blue"], PALETTE["purple"], PALETTE["red"]][i]
        cv.setFillColor(c(col))
        cv.circle(px, py, 22, fill=1, stroke=0)


def draw_molecule_network_svg(svg, x, y):
    pts = [(x, y - 45), (x + 95, y - 75), (x + 170, y - 15), (x + 90, y + 55), (x - 15, y + 35)]
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (1, 3)]:
        svg.line(pts[a][0], pts[a][1], pts[b][0], pts[b][1], "#B8D5C9", 5)
    for i, (px, py) in enumerate(pts):
        col = [PALETTE["gold"], PALETTE["green2"], PALETTE["blue"], PALETTE["purple"], PALETTE["red"]][i]
        svg.circle(px, py, 22, col)


def draw_cell_pdf(cv, x, y):
    cv.setFillColor(c("#FDEBE7"))
    p = cv.beginPath()
    p.moveTo(x - 95, y)
    p.curveTo(x - 85, y + 75, x - 10, y + 105, x + 58, y + 65)
    p.curveTo(x + 132, y + 20, x + 104, y - 78, x + 18, y - 88)
    p.curveTo(x - 76, y - 100, x - 125, y - 55, x - 95, y)
    cv.drawPath(p, fill=1, stroke=0)
    cv.setFillColor(c("#E8A398"))
    cv.circle(x + 8, y - 3, 31, fill=1, stroke=0)
    for label, dx, dy in [("TNF-a", -95, 105), ("IL-6", 88, 96), ("NO", 118, -80)]:
        round_rect_pdf(cv, x + dx - 36, y + dy - 18, 72, 36, "#FFFFFF", "#E8A398", 2, 18)
        text_pdf(cv, x + dx, y + dy - 6, label, 15, PALETTE["red"], True, "center")


def draw_cell_svg(svg, x, y):
    d = (
        f"M{x - 95},{y} C{x - 85},{y - 75} {x - 10},{y - 105} {x + 58},{y - 65} "
        f"C{x + 132},{y - 20} {x + 104},{y + 78} {x + 18},{y + 88} "
        f"C{x - 76},{y + 100} {x - 125},{y + 55} {x - 95},{y} Z"
    )
    svg.path(d, "#FDEBE7")
    svg.circle(x + 8, y + 3, 31, "#E8A398")
    for label, dx, dy in [("TNF-a", -95, -105), ("IL-6", 88, -96), ("NO", 118, 80)]:
        svg.rect(x + dx - 36, y + dy - 18, 72, 36, "#FFFFFF", "#E8A398", 2, 18)
        svg.text(x + dx, y + dy + 6, label, 15, PALETTE["red"], "700", "middle")


def build_pdf() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cv = canvas.Canvas(str(PDF_PATH), pagesize=(W, H))
    cv.setTitle("M³KG Graphical Abstract")
    cv.setAuthor("M³KG")
    cv.setFillColor(c(PALETTE["bg"]))
    cv.rect(0, 0, W, H, fill=1, stroke=0)

    text_pdf(cv, 92, H - 84, "M³KG: Prior Knowledge-Guided Discovery Framework for Mongolian Medicines", 45, PALETTE["ink"], True)
    text_pdf(
        cv,
        94,
        H - 126,
        "From curated Mongolian medicine data to explainable graph inference and phytomedicine-oriented validation",
        24,
        PALETTE["muted"],
    )

    panels = [
        (74, 168, 560, 736, "Curated Data", "D1-D6 data modules"),
        (704, 168, 592, 736, "M³KG Knowledge Graph", "Medicinal pieces linked to properties, terms and origins"),
        (1366, 168, 566, 736, "Prior Knowledge-Guided Inference", "Quantification, rule mining and explainable paths"),
        (2002, 168, 578, 736, "Phytomedicine Discovery", "Candidate prioritization and mechanistic validation"),
    ]
    for x, y, w, h, title, subtitle in panels:
        round_rect_pdf(cv, x, y, w, h, "#FFFFFF", "#D6E8DF", 2.5, 34)
        text_pdf(cv, x + 34, y + h - 58, title, 29, PALETTE["green"], True)
        text_pdf(cv, x + 34, y + h - 90, subtitle, 17, PALETTE["muted"])

    line_pdf(cv, 650, 536, 690, 536, PALETTE["green"], 8, True)
    line_pdf(cv, 1312, 536, 1352, 536, PALETTE["green"], 8, True)
    line_pdf(cv, 1948, 536, 1988, 536, PALETTE["green"], 8, True)

    docs = [
        ("D1 Terminology", "1132 curated terms", PALETTE["green2"]),
        ("D2 Medicinal pieces", "558 MMPs", PALETTE["green"]),
        ("D3 MMP-MMT", "5679 term links", PALETTE["blue"]),
        ("D4 Properties", "Taste, nature, potency", PALETTE["gold"]),
        ("D5 Origins", "390 taxonomy units", PALETTE["olive"]),
        ("D6 MMP-PO", "468 origin links", PALETTE["purple"]),
    ]
    for i, (title, subtitle, col) in enumerate(docs):
        row, col_idx = divmod(i, 2)
        draw_document_card_pdf(cv, 112 + col_idx * 258, 690 - row * 112, 230, 84, title, subtitle, col)
    for i, (num, lab) in enumerate([("558", "MMPs"), ("1132", "terms"), ("8805", "KG edges")]):
        x = 126 + i * 158
        round_rect_pdf(cv, x, 276, 132, 104, PALETTE["mint2"], "#CFE6DC", 2, 20)
        text_pdf(cv, x + 66, 331, num, 31, PALETTE["green"], True, "center")
        text_pdf(cv, x + 66, 302, lab, 16, PALETTE["muted"], False, "center")

    draw_network_pdf(cv, 1000, 536)

    module_y = [708, 606, 504]
    for y, title, col in [
        (module_y[0], "Taste/Nature scoring", PALETTE["red"]),
        (module_y[1], "Association rules", PALETTE["gold"]),
        (module_y[2], "Explainable graph paths", PALETTE["green2"]),
    ]:
        draw_module_pdf(cv, 1410, y, 468, 72, title, col)
    line_pdf(cv, 1644, 696, 1644, 681, PALETTE["line"], 4, True)
    line_pdf(cv, 1644, 594, 1644, 579, PALETTE["line"], 4, True)
    draw_rule_pdf(cv, 1414, 392, 458, "Bitter + Cold -> Heat-clearing / Detoxifying", PALETTE["gold"])
    draw_rule_pdf(cv, 1414, 318, 458, "Pungent + Warm -> Warming stomach / Digestion", PALETTE["red"])
    text_pdf(cv, 1416, 266, "Outputs: candidate rules, ranked hypotheses and traceable evidence paths", 17, PALETTE["muted"])

    cv.setFillColor(c(PALETTE["mint2"]))
    cv.circle(2158, 652, 118, fill=1, stroke=0)
    draw_plant_pdf(cv, 2158, 642)
    text_pdf(cv, 2158, 492, "Plant-derived", 22, PALETTE["green"], True, "center")
    text_pdf(cv, 2158, 465, "Mongolian medicines", 17, PALETTE["muted"], False, "center")

    line_pdf(cv, 2275, 638, 2333, 638, PALETTE["green"], 6, True)
    draw_molecule_network_pdf(cv, 2360, 642)
    text_pdf(cv, 2446, 492, "Compound-target", 22, PALETTE["green"], True, "center")
    text_pdf(cv, 2446, 465, "mechanism network", 17, PALETTE["muted"], False, "center")

    line_pdf(cv, 2385, 420, 2385, 378, PALETTE["green"], 6, True)
    draw_cell_pdf(cv, 2368, 360)
    text_pdf(cv, 2368, 230, "Experimental validation", 22, PALETTE["green"], True, "center")
    text_pdf(cv, 2368, 203, "anti-inflammatory readouts", 17, PALETTE["muted"], False, "center")

    round_rect_pdf(cv, 122, 54, 2412, 58, PALETTE["mint2"], "#CFE6DC", 2, 22)
    text_pdf(cv, 1328, 76, "Traceable evidence: curated tables | taxonomy IDs | KG paths | web explorer", 22, PALETTE["green"], True, "center")

    cv.showPage()
    cv.save()


def build_svg() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    svg = Svg()
    svg.rect(0, 0, W, H, PALETTE["bg"], rx=0)
    svg.text(92, 84, "M³KG: Prior Knowledge-Guided Discovery Framework for Mongolian Medicines", 45, PALETTE["ink"], "700")
    svg.text(
        94,
        126,
        "From curated Mongolian medicine data to explainable graph inference and phytomedicine-oriented validation",
        24,
        PALETTE["muted"],
    )
    panels = [
        (74, 158, 560, 736, "Curated Data", "D1-D6 data modules"),
        (704, 158, 592, 736, "M³KG Knowledge Graph", "Medicinal pieces linked to properties, terms and origins"),
        (1366, 158, 566, 736, "Prior Knowledge-Guided Inference", "Quantification, rule mining and explainable paths"),
        (2002, 158, 578, 736, "Phytomedicine Discovery", "Candidate prioritization and mechanistic validation"),
    ]
    for x, y, w, h, title, subtitle in panels:
        svg.rect(x, y, w, h, "#FFFFFF", "#D6E8DF", 2.5, 34, filt=True)
        svg.text(x + 34, y + 58, title, 29, PALETTE["green"], "700")
        svg.text(x + 34, y + 90, subtitle, 17, PALETTE["muted"])

    svg.line(650, 526, 690, 526, PALETTE["green"], 8, marker=True)
    svg.line(1312, 526, 1352, 526, PALETTE["green"], 8, marker=True)
    svg.line(1948, 526, 1988, 526, PALETTE["green"], 8, marker=True)

    docs = [
        ("D1 Terminology", "1132 curated terms", PALETTE["green2"]),
        ("D2 Medicinal pieces", "558 MMPs", PALETTE["green"]),
        ("D3 MMP-MMT", "5679 term links", PALETTE["blue"]),
        ("D4 Properties", "Taste, nature, potency", PALETTE["gold"]),
        ("D5 Origins", "390 taxonomy units", PALETTE["olive"]),
        ("D6 MMP-PO", "468 origin links", PALETTE["purple"]),
    ]
    for i, (title, subtitle, col) in enumerate(docs):
        row, col_idx = divmod(i, 2)
        draw_document_card_svg(svg, 112 + col_idx * 258, 288 + row * 112, 230, 84, title, subtitle, col)
    for i, (num, lab) in enumerate([("558", "MMPs"), ("1132", "terms"), ("8805", "KG edges")]):
        x = 126 + i * 158
        svg.rect(x, 682, 132, 104, PALETTE["mint2"], "#CFE6DC", 2, 20)
        svg.text(x + 66, 735, num, 31, PALETTE["green"], "700", "middle")
        svg.text(x + 66, 764, lab, 16, PALETTE["muted"], "400", "middle")

    draw_network_svg(svg, 1000, 526)

    for y, title, col in [
        (282, "Taste/Nature scoring", PALETTE["red"]),
        (384, "Association rules", PALETTE["gold"]),
        (486, "Explainable graph paths", PALETTE["green2"]),
    ]:
        draw_module_svg(svg, 1410, y, 468, 72, title, col)
    svg.line(1644, 354, 1644, 379, PALETTE["line"], 4, marker=True)
    svg.line(1644, 456, 1644, 481, PALETTE["line"], 4, marker=True)
    draw_rule_svg(svg, 1414, 612, 458, "Bitter + Cold -> Heat-clearing / Detoxifying", PALETTE["gold"])
    draw_rule_svg(svg, 1414, 686, 458, "Pungent + Warm -> Warming stomach / Digestion", PALETTE["red"])
    svg.text(1416, 822, "Outputs: candidate rules, ranked hypotheses and traceable evidence paths", 17, PALETTE["muted"])

    svg.circle(2158, 410, 118, PALETTE["mint2"])
    draw_plant_svg(svg, 2158, 420)
    svg.text(2158, 570, "Plant-derived", 22, PALETTE["green"], "700", "middle")
    svg.text(2158, 597, "Mongolian medicines", 17, PALETTE["muted"], "400", "middle")
    svg.line(2275, 424, 2333, 424, PALETTE["green"], 6, marker=True)
    draw_molecule_network_svg(svg, 2360, 420)
    svg.text(2446, 570, "Compound-target", 22, PALETTE["green"], "700", "middle")
    svg.text(2446, 597, "mechanism network", 17, PALETTE["muted"], "400", "middle")
    svg.line(2385, 642, 2385, 684, PALETTE["green"], 6, marker=True)
    draw_cell_svg(svg, 2368, 728)
    svg.text(2368, 852, "Experimental validation", 22, PALETTE["green"], "700", "middle")
    svg.text(2368, 879, "anti-inflammatory readouts", 17, PALETTE["muted"], "400", "middle")

    svg.rect(122, 950, 2412, 58, PALETTE["mint2"], "#CFE6DC", 2, 22)
    svg.text(1328, 986, "Traceable evidence: curated tables | taxonomy IDs | KG paths | web explorer", 22, PALETTE["green"], "700", "middle")
    svg.save(SVG_PATH)


def main() -> None:
    build_pdf()
    build_svg()
    print(PDF_PATH)
    print(SVG_PATH)


if __name__ == "__main__":
    main()
