"""导出 xlsx：与 Tracker list 原格式一致，支持融合上传的基准工作簿。

流程（与用户工作流对齐）：
  上传原始 Tracker list.xlsx（通常只有 Tracker list 表）
  → 上传发票解析
  → 导出时在基准文件的副本上生成/追加 Expenses report 与 Bills，
    Tracker list 等原有 sheet 原样保留，编号衔接已有最大编号。

Bills 贴图布局（防重叠）：左右两栏各约 9 列（A..I / J..R，每列 64px）。
每张发票等比缩放到「宽 ≤570px 且 高 ≤450px」，在半栏内水平居中：
左图锚 A 列、右图锚 J 列，块步进 23 行 —— 左右互不重叠，同块缝隙最小。
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.units import pixels_to_EMU

from .config import REPORT_TITLE, THUMB_DIR, UPLOAD_DIR
from .models import Invoice, sorted_invoices
from .parsers import extract

THIN = Side(style="thin")
BORDER_THIN = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")

HEADERS = ["Date:", "Item:", "Location:", "Amt (RMB):", "HK$", "Bill No."]
COL_WIDTHS = {"A": 14.6, "B": 17.0, "C": 26.4, "D": 16.6, "E": 13.2, "F": 17.3}

BLOCK_ROWS = 23                                # 每个编号占的行数（与原表一致）
BILL_MAX_W, BILL_MAX_H = 570, 430              # 半栏宽 9×64=576；块内可用高 440-4=436
HALF_COL_PX = 9 * 64
LEFT_IMG_COL, RIGHT_IMG_COL = 0, 9             # A / J
LEFT_LABEL_COL, RIGHT_LABEL_COL = 5, 14        # E / N


# ---------------------------------------------------------------- 贴图素材

def _image_for_bill(inv: Invoice) -> Path | None:
    """Bills 贴的是位图：图片用原文件（过大则压缩），PDF 渲染首页；
    OFD 无通用渲染器则放弃贴图（只保留编号）。结果按发票缓存。"""
    if not inv.stored_name:
        return None
    src = UPLOAD_DIR / inv.stored_name
    if not src.exists():
        return None
    try:
        if inv.file_type == "pdf":
            cached = THUMB_DIR / f"{inv.id}_bill.png"
            return extract.render_pdf_page(src, 1100, cached)
        if inv.file_type == "image":
            from PIL import Image
            with Image.open(src) as pil:
                pil.load()
                if pil.width > 1600:
                    cached = THUMB_DIR / f"{inv.id}_bill.jpg"
                    h = int(pil.height * 1600 / pil.width)
                    pil.resize((1600, h)).convert("RGB").save(cached, format="JPEG", quality=85)
                    return cached
            return src
    except Exception:
        import traceback
        traceback.print_exc()
        return None
    return None


def _place_image(ws, path: Path, idx: int) -> None:
    """第 idx 张发票（1 起）：等比缩放、半栏居中、锚到对应块。"""
    is_left = idx % 2 == 1
    col = LEFT_IMG_COL if is_left else RIGHT_IMG_COL
    block_row = 2 + ((idx - 1) // 2) * BLOCK_ROWS      # 1-based，标签所在行

    img = XLImage(str(path))
    scale = min(BILL_MAX_W / img.width, BILL_MAX_H / img.height, 1.0)
    w = max(1, int(img.width * scale))
    h = max(1, int(img.height * scale))

    col_off = max(0, (HALF_COL_PX - w) // 2)           # 半栏内水平居中
    marker = AnchorMarker(
        col=col, colOff=pixels_to_EMU(col_off),
        row=block_row, rowOff=pixels_to_EMU(4),        # 标签行下方 4px 起
    )
    img.anchor = OneCellAnchor(
        _from=marker,
        ext=XDRPositiveSize2D(pixels_to_EMU(w), pixels_to_EMU(h)),
    )
    ws.add_image(img)


# ---------------------------------------------------------------- Expenses report

def _find_header_row(ws) -> int | None:
    for row in ws.iter_rows(min_row=1, max_row=12):
        for c in row:
            if str(c.value).strip() == "Date:":
                return c.row
    return None


def _first_empty_row(ws, start: int) -> int:
    r = start
    while any(ws.cell(row=r, column=j).value not in (None, "") for j in range(1, 7)):
        r += 1
    return r


def _init_expense_sheet(ws) -> int:
    """确保标题+表头存在（已有表头则原样保留），返回数据起始行。"""
    for col, w in COL_WIDTHS.items():
        ws.column_dimensions[col].width = w
    header_row = _find_header_row(ws)
    if header_row is not None:
        return _first_empty_row(ws, header_row + 1)
    # 新 sheet / 空壳：写标题（A1）和表头（第 2 行）
    ws.merge_cells("A1:F1")
    ws["A1"] = REPORT_TITLE
    ws["A1"].font = Font(name="Calibri", size=18)
    ws["A1"].alignment = CENTER
    ws.row_dimensions[1].height = 23.4
    for j, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=2, column=j, value=h)
        cell.font = Font(name="Calibri", size=11, bold=True)
        cell.alignment = CENTER
        cell.border = BORDER_THIN
    ws.row_dimensions[2].height = 35
    return 3


def _append_expense_rows(ws, invoices: list[Invoice], start_row: int, no_offset: int) -> int:
    r = start_row
    written = 0
    for inv in invoices:
        if inv.category != "travel":
            continue
        if inv.no_bill:
            bill_no = inv.note.strip() or "（工厂已付）"
        else:
            bill_no = f"{no_offset + _bill_seq(invoices, inv)}#"
        dt = None
        if inv.date:
            try:
                dt = datetime.strptime(inv.date, "%Y-%m-%d")
            except ValueError:
                dt = None
        vals = [
            dt, inv.item, inv.location,
            inv.amount if inv.amount is not None else None,
            inv.hkd or None, bill_no,
        ]
        for j, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=j, value=v)
            cell.alignment = CENTER
            cell.border = BORDER_THIN
            cell.font = Font(name="宋体", size=11)
        ws.cell(row=r, column=1).number_format = "d-mmm"
        ws.row_dimensions[r].height = 24
        r += 1
        written += 1
    return written


def _bill_seq(ordered: list[Invoice], inv: Invoice) -> int:
    """该发票在「占编号发票」序列中的序号（1 起）。"""
    n = 0
    for i in ordered:
        if i.no_bill or not i.stored_name:
            continue
        n += 1
        if i.id == inv.id:
            return n
    return n


# ---------------------------------------------------------------- Bills

def _max_bill_no(ws) -> int:
    mx = 0
    for row in ws.iter_rows():
        for c in row:
            v = c.value
            if isinstance(v, str) and v.endswith("#") and v[:-1].isdigit():
                mx = max(mx, int(v[:-1]))
    return mx


def _append_bills(ws, invoices: list[Invoice], no_offset: int) -> int:
    n_pasted = 0
    for inv in invoices:
        if inv.no_bill or not inv.stored_name:
            continue
        idx = no_offset + _bill_seq(invoices, inv)
        is_left = idx % 2 == 1
        block_row = 2 + ((idx - 1) // 2) * BLOCK_ROWS
        lab = ws.cell(
            row=block_row,
            column=LEFT_LABEL_COL if is_left else RIGHT_LABEL_COL,
            value=f"{idx}#",
        )
        lab.font = Font(name="宋体", size=11)
        img_path = _image_for_bill(inv)
        if img_path is not None:
            _place_image(ws, img_path, idx)
        n_pasted += 1
    return n_pasted


# ---------------------------------------------------------------- 入口

def build_workbook(invoices: list[Invoice], tracker_path: Path | None = None):
    """在基准工作簿副本上融合；无基准时新建（仅两个模块 sheet）。"""
    invoices = sorted_invoices(invoices)

    if tracker_path and Path(tracker_path).exists():
        wb = load_workbook(str(tracker_path))
    else:
        wb = Workbook()
        wb.remove(wb.active)
        wb.properties.creator = "ZCode"

    # ---- Bills 先定位：Expenses report 的 Bill No. 要衔接已有编号 ----
    if "Bills" in wb.sheetnames:
        ws2 = wb["Bills"]
    else:
        ws2 = wb.create_sheet("Bills")
    no_offset = _max_bill_no(ws2)

    # ---- Expenses report ----
    if "Expenses report" in wb.sheetnames:
        ws = wb["Expenses report"]
    else:
        ws = wb.create_sheet("Expenses report")
    start_row = _init_expense_sheet(ws)
    travel_rows = _append_expense_rows(ws, invoices, start_row, no_offset)

    _append_bills(ws2, invoices, no_offset)

    # ---- sheet 顺序：原有 sheet 保持在前，两个模块在最后 ----
    others = [s for s in wb.sheetnames if s not in ("Expenses report", "Bills")]
    order = others + ["Expenses report", "Bills"]
    wb._sheets = [wb[name] for name in order]

    return wb, travel_rows


def to_xlsx_bytes(invoices: list[Invoice], tracker_path: Path | None = None) -> bytes:
    wb, _ = build_workbook(invoices, tracker_path)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
