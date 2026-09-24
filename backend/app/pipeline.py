"""单张发票的完整处理：存文件 → 提取文本 → 字段解析 → 生成缩略图。"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from . import config
from .models import Invoice
from .parsers import extract, fields

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def detect_file_type(suffix: str) -> str | None:
    s = suffix.lower()
    if s == ".pdf":
        return "pdf"
    if s == ".ofd":
        return "ofd"
    if s in IMG_EXT:
        return "image"
    return None


def safe_name(name: str) -> str:
    name = re.sub(r"[^\w.\-（）()\u4e00-\u9fa5]+", "_", Path(name).name)
    return name[:80] or "file"


def process_upload(filename: str, content: bytes) -> Invoice:
    suffix = Path(filename).suffix.lower()
    ftype = detect_file_type(suffix)
    inv = Invoice(filename=filename, file_type=ftype or "")
    if ftype is None:
        inv.parse_ok = False
        inv.parse_msg = f"不支持的文件类型: {suffix or '(无后缀)'}"
        return inv
    if len(content) > config.MAX_UPLOAD_SIZE:
        inv.parse_ok = False
        inv.parse_msg = "文件超过 30MB"
        return inv

    stored = config.UPLOAD_DIR / f"{inv.id}_{safe_name(filename)}"
    stored.write_bytes(content)
    inv.stored_name = stored.name

    try:
        text = extract.extract_text(stored, ftype)
        inv.raw_text = text[:4000]
        vals = fields.parse_fields(text)
        for k, v in vals.items():
            setattr(inv, k, v)
        if vals["category"] == "other" and vals["item"]:
            inv.category = "travel"
        if not vals["invoice_no"] and not vals["amount"]:
            inv.parse_msg = "未识别出发票号码/金额，请人工核对"
    except Exception as e:  # 单张失败不影响整批
        inv.parse_ok = False
        inv.parse_msg = f"解析失败: {e}"

    ext = ".png" if ftype in ("pdf",) else stored.suffix.lower()
    if ftype == "image" and stored.suffix.lower() in (".jpg", ".jpeg"):
        ext = ".jpg"
    thumb = extract.make_thumb(stored, config.THUMB_DIR / f"{inv.id}{ext}")
    inv.thumb_name = thumb
    return inv
