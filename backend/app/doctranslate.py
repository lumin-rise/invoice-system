"""文档翻译：PDF / Word → 中文 Word。

- PDF：pdfplumber 逐页提取「表格 + 表格外文本」，大字号文本识别为标题
- Word：python-docx 按文档顺序遍历段落与表格
- 输出：.docx（保留标题层级与表格结构，正文全部翻译为中文）
"""
from __future__ import annotations

import re

import pdfplumber
import docx
from docx import Document

from . import translators


def _needs_translation(t: str) -> bool:
    """空串/纯数字符号不用翻译。"""
    t = (t or "").strip()
    if not t:
        return False
    return bool(re.search(r"[A-Za-z\u00c0-\u024f]", t))


def _collect(blocks: list[tuple]) -> list[str]:
    texts: list[str] = []
    for kind, *rest in blocks:
        if kind == "table":
            for row in rest[0]:
                for cell in row:
                    if _needs_translation(cell or ""):
                        texts.append(cell.strip())
        else:
            t = rest[0]
            if _needs_translation(t):
                texts.append(t.strip())
    return texts


def _apply(blocks: list[tuple], mapping: dict[str, str]) -> list[tuple]:
    out = []
    for kind, *rest in blocks:
        if kind == "table":
            new_rows = [[mapping.get((c or "").strip(), c or "") for c in row] for row in rest[0]]
            out.append(("table", new_rows))
        else:
            t = rest[0]
            out.append((kind, mapping.get(t.strip(), t), *rest[1:]))
    return out


# ---------------------------------------------------------------- PDF 提取

def extract_pdf(path: str) -> list[tuple]:
    blocks: list[tuple] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            tboxes = [(t.bbox[1], t.bbox[3]) for t in tables]

            def in_table(word) -> bool:
                mid = (word["top"] + word["bottom"]) / 2
                return any(t0 - 2 <= mid <= t1 + 2 for t0, t1 in tboxes)

            # 表格外的文本：按行分组，大字号当标题
            words = [w for w in page.extract_words(extra_attrs=["size"]) if not in_table(w)]
            lines: dict[int, list] = {}
            for w in words:
                lines.setdefault(round(w["top"] / 4), []).append(w)
            for key in sorted(lines):
                ws = sorted(lines[key], key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in ws).strip()
                if not text:
                    continue
                size = max(w.get("size", 10) for w in ws)
                if size >= 16:
                    blocks.append(("heading", text, 1))
                elif size >= 12.5:
                    blocks.append(("heading", text, 2))
                else:
                    blocks.append(("para", text))

            for t in tables:
                rows = t.extract()
                rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in rows]
                if any(any(r) for r in rows):
                    blocks.append(("table", rows))
    return blocks


# ---------------------------------------------------------------- Word 提取

def extract_docx(path: str) -> list[tuple]:
    doc = docx.Document(path)
    blocks: list[tuple] = []
    try:
        items = list(doc.iter_inner_content())
    except AttributeError:                     # 旧版 python-docx：退化为先段落后台账
        items = list(doc.paragraphs) + list(doc.tables)
    for item in items:
        if isinstance(item, docx.table.Table):
            rows = [[(c.text or "").replace("\n", " ").strip() for c in row.cells]
                    for row in item.rows]
            if rows:
                blocks.append(("table", rows))
        else:
            text = item.text.strip()
            if not text:
                continue
            style = (item.style.name or "").lower()
            m = re.search(r"heading (\d)", style)
            if m:
                blocks.append(("heading", text, int(m.group(1))))
            elif "title" in style:
                blocks.append(("heading", text, 1))
            else:
                blocks.append(("para", text))
    return blocks


# ---------------------------------------------------------------- 生成 docx

def build_docx(blocks: list[tuple], out_path: str) -> None:
    doc = Document()
    doc.add_heading("文档中文翻译", level=0)
    for kind, *rest in blocks:
        if kind == "heading":
            doc.add_heading(rest[0], level=min(rest[1] or 1, 3))
        elif kind == "para":
            doc.add_paragraph(rest[0])
        elif kind == "table":
            rows = rest[0]
            cols = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=cols)
            table.style = "Table Grid"
            for i, row in enumerate(rows):
                for j in range(cols):
                    table.cell(i, j).text = row[j] if j < len(row) else ""
            doc.add_paragraph()
    doc.save(out_path)


# ---------------------------------------------------------------- 入口

def translate_document(src: str, out_path: str, source_type: str) -> int:
    """翻译文档并输出中文 docx，返回处理的块数。"""
    blocks = extract_pdf(src) if source_type == "pdf" else extract_docx(src)
    texts = _collect(blocks)
    mapping = dict(zip(texts, translators.translate_many(texts)))
    blocks = _apply(blocks, mapping)
    build_docx(blocks, out_path)
    return len(blocks)
