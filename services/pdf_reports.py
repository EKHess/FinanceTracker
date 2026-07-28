from datetime import datetime

from config import CATEGORY_CONFIG


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 44
INK = "10223b"
MUTED = "718096"
GREEN = "15975d"
RED = "d84e4e"
LINE = "e4eaf0"


def _rgb(hex_color):
    return tuple(int(hex_color[index:index + 2], 16) / 255 for index in (0, 2, 4))


def _escape_pdf_text(value):
    value = str(value).encode("cp1252", "replace").decode("cp1252")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(value):
    value = float(value or 0)
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


class PdfDocument:
    def __init__(self):
        self.pages = []

    def new_page(self):
        self.pages.append([])

    @property
    def page(self):
        return self.pages[-1]

    def text(self, x, y, value, size=10, color=INK, bold=False):
        r, g, b = _rgb(color)
        font = "F2" if bold else "F1"
        self.page.append(f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg {x:.1f} {y:.1f} Td ({_escape_pdf_text(value)}) Tj ET")

    def rect(self, x, y, width, height, fill="ffffff", stroke=LINE):
        fr, fg, fb = _rgb(fill)
        sr, sg, sb = _rgb(stroke)
        self.page.append(f"{fr:.3f} {fg:.3f} {fb:.3f} rg {sr:.3f} {sg:.3f} {sb:.3f} RG {x:.1f} {y:.1f} {width:.1f} {height:.1f} re B")

    def line(self, x1, y1, x2, y2, color=LINE):
        r, g, b = _rgb(color)
        self.page.append(f"{r:.3f} {g:.3f} {b:.3f} RG {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def globe(self, x, y, size=9, color=GREEN):
        """Draw a small globe marker using PDF paths, independent of fonts."""
        r, g, b = _rgb(color)
        radius = size / 2
        k = radius * .5523
        self.page.append(
            f"{r:.3f} {g:.3f} {b:.3f} RG 0.8 w "
            f"{x + radius:.1f} {y:.1f} m {x + radius:.1f} {y + k:.1f} {x + k:.1f} {y + radius:.1f} {x:.1f} {y + radius:.1f} c "
            f"{x - k:.1f} {y + radius:.1f} {x - radius:.1f} {y + k:.1f} {x - radius:.1f} {y:.1f} c "
            f"{x - radius:.1f} {y - k:.1f} {x - k:.1f} {y - radius:.1f} {x:.1f} {y - radius:.1f} c "
            f"{x + k:.1f} {y - radius:.1f} {x + radius:.1f} {y - k:.1f} {x + radius:.1f} {y:.1f} c S "
            f"{x - radius:.1f} {y:.1f} m {x + radius:.1f} {y:.1f} l S "
            f"{x:.1f} {y - radius:.1f} m {x:.1f} {y + radius:.1f} l S"
        )

    def render(self):
        objects = [None, "<< /Type /Catalog /Pages 2 0 R >>", None,
                   "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                   "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
        page_ids = []
        for commands in self.pages:
            page_id = len(objects)
            content_id = page_id + 1
            page_ids.append(page_id)
            objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>")
            stream = "\n".join(commands).encode("cp1252", "replace")
            objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        objects[2] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] >>"
        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for object_id, value in enumerate(objects[1:], 1):
            offsets.append(len(output))
            output.extend(f"{object_id} 0 obj\n".encode())
            output.extend(value if isinstance(value, bytes) else value.encode("cp1252"))
            output.extend(b"\nendobj\n")
        xref = len(output)
        output.extend(f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode())
        output.extend(f"trailer << /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
        return bytes(output)


def build_financial_reports_pdf(reports):
    pdf = PdfDocument()
    pdf.new_page()
    oldest = min(reports, key=lambda report: report["start_date"])
    latest = max(reports, key=lambda report: report["end_date"])
    pdf.text(82, 444, "FINANCE TRACKER", 11, GREEN, True)
    pdf.text(82, 392, "Financial Reports", 34, INK, True)
    pdf.line(82, 372, 530, 372, GREEN)
    pdf.text(82, 345, f"{oldest['start_date']}  to  {latest['end_date']}", 14, MUTED)
    pdf.text(82, 80, f"Generated {datetime.now().strftime('%B %d, %Y')}", 9, MUTED)

    for report in reports:
        _draw_report(pdf, report)
    return pdf.render()


def _draw_report(pdf, report):
    pdf.new_page()
    pdf.text(MARGIN, 748, report["name"], 22, INK, True)
    pdf.text(MARGIN, 728, f"{report['start_date']} - {report['end_date']}", 10, MUTED)
    card_width = (PAGE_WIDTH - MARGIN * 2 - 24) / 4
    primary = [("Total Spending", report["total_spending"], INK),
               ("Surplus / Deficit", report["surplus"], GREEN if report["surplus"] >= 0 else RED),
               ("Global Balance", report["global_balance"], GREEN if report["global_balance"] >= 0 else RED),
               ("Net Worth", report.get("net_worth") or 0, GREEN if (report.get("net_worth") or 0) >= 0 else RED)]
    for index, (label, value, color) in enumerate(primary):
        x = MARGIN + index * (card_width + 8)
        pdf.rect(x, 654, card_width, 58, "f8fbfa")
        pdf.text(x + 10, 690, label, 8, MUTED, True)
        pdf.text(x + 10, 670, _money(value), 16, color, True)

    pdf.text(MARGIN, 632, "SPENDING BY CATEGORY", 8, MUTED, True)
    category_width = (PAGE_WIDTH - MARGIN * 2 - 18) / 4
    for index, category in enumerate(report["categories"]):
        x = MARGIN + index * (category_width + 6)
        pdf.rect(x, 592, category_width, 30, "ffffff", category["color"].lstrip("#"))
        pdf.text(x + 7, 608, category["label"], 7, MUTED)
        pdf.text(x + 7, 597, _money(category["total"]), 9, INK, True)

    summary = report["summary"]
    largest = summary["largest_expense"]
    largest_category = summary["largest_category"]
    insights = [
        f"Largest expense: {largest['description']} ({_money(largest['amount'])}, {largest['category_label']})" if largest else "Largest expense: None",
        f"Largest category: {largest_category['label']} ({_money(largest_category['total'])})" if largest_category else "Largest category: None",
        f"Expenses: {summary['expense_count']}    Recurring: {summary['recurring_count']}    Recurring spending: {summary['recurring_percent']:.1f}%",
    ]
    y = 570
    for index, insight in enumerate(insights):
        pdf.text(MARGIN, y, insight, 9, INK, y == 570)
        if index == 0 and largest and largest.get("global_type") == "draw":
            pdf.globe(min(MARGIN + 5 + len(insight) * 4.5, PAGE_WIDTH - MARGIN - 6), y + 3, 8)
        y -= 15
    y -= 5

    for category in report["categories"]:
        has_global_draw = any(expense.get("global_type") == "draw" for expense in category["expenses"])
        required = 30 + max(len(category["expenses"]), 1) * 22 + (24 if has_global_draw else 0)
        if y - required < 45:
            pdf.new_page()
            pdf.text(MARGIN, 750, f"{report['name']} (continued)", 16, INK, True)
            y = 720
        color = category["color"].lstrip("#")
        pdf.rect(MARGIN, y - 24, PAGE_WIDTH - MARGIN * 2, 24, color, color)
        pdf.text(MARGIN + 10, y - 16, category["label"], 10, "ffffff", True)
        pdf.text(475, y - 16, _money(category["total"]), 10, "ffffff", True)
        y -= 24
        expenses = category["expenses"] or [None]
        for expense in expenses:
            if y - 22 < 45:
                pdf.new_page()
                pdf.text(MARGIN, 750, f"{report['name']} (continued)", 16, INK, True)
                y = 720
                pdf.rect(MARGIN, y - 24, PAGE_WIDTH - MARGIN * 2, 24, color, color)
                pdf.text(MARGIN + 10, y - 16, f"{category['label']} (continued)", 10, "ffffff", True)
                y -= 24
            pdf.line(MARGIN, y - 22, PAGE_WIDTH - MARGIN, y - 22)
            if expense:
                description = expense["description"][:58]
                pdf.text(MARGIN + 10, y - 15, description, 9, INK)
                if expense.get("global_type") == "draw":
                    pdf.globe(min(MARGIN + 15 + len(description) * 4.5, 375), y - 12, 8)
                pdf.text(390, y - 15, "Recurring" if expense["recurring"] else "One-time", 8, MUTED)
                pdf.text(485, y - 15, _money(expense["amount"]), 9, INK, True)
            else:
                pdf.text(MARGIN + 10, y - 15, "No expenses in this category", 9, MUTED)
            y -= 22
        if has_global_draw:
            pdf.globe(MARGIN + 14, y - 7, 8)
            pdf.text(MARGIN + 24, y - 10, "Marked expenses came from global surplus, not income in this workspace period.", 7, MUTED)
            y -= 24
        y -= 10
