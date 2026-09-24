"""从 PDF / OFD / 图片中提取文本，并生成预览缩略图。

- PDF：pdfplumber 抽取内嵌文字（电子发票都是文字型）；抽不到字（扫描件）
  则用 pypdfium2 渲染成位图后走 OCR。
- OFD：国产电子发票格式，本质是 zip+XML，直接抽取 TextObject 文本。
- 图片：RapidOCR（onnxruntime，中文识别，CPU 可用）。
"""
from __future__ import annotations

import io
import re
import threading
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_ocr_engine = None
_ocr_lock = threading.Lock()
# PDFium 不是线程安全的：批量上传时多线程同时渲染会偶发原生崩溃，
# 所有 PDFium 调用统一走这把全局锁。
PDF_LOCK = threading.Lock()


def get_ocr():
    """懒加载 RapidOCR 单例（首次调用会加载模型，约 1-2 秒）。"""
    global _ocr_engine
    if _ocr_engine is None:
        with _ocr_lock:
            if _ocr_engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_image_bytes(img_bytes: bytes) -> list[str]:
    """对图片字节做 OCR，返回按版面顺序排列的文本行。"""
    engine = get_ocr()
    result, _ = engine(img_bytes)
    if not result:
        return []
    return [line[1] for line in result]


# ---------------------------------------------------------------- PDF

def _render_pdf_pages(path: Path, scale: float = 3.0) -> list[bytes]:
    import pypdfium2 as pdfium
    out = []
    with PDF_LOCK:
        pdf = pdfium.PdfDocument(str(path))
        try:
            for page in pdf:
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                out.append(buf.getvalue())
        finally:
            pdf.close()
    return out


def render_pdf_page(path: Path, target_w: int, dest: Path) -> Path | None:
    """把 PDF 第一页渲染成宽约 target_w 的 PNG，写到 dest。失败返回 None。"""
    if dest.exists():
        return dest
    try:
        import pypdfium2 as pdfium
        with PDF_LOCK:
            pdf = pdfium.PdfDocument(str(path))
            try:
                page = pdf[0]
                w = page.get_size()[0]
                bitmap = page.render(scale=max(target_w / w, 1.5))
                pil = bitmap.to_pil()
            finally:
                pdf.close()
        dest.parent.mkdir(parents=True, exist_ok=True)
        pil.save(dest, format="PNG")
        return dest
    except Exception:
        import traceback
        traceback.print_exc()
        return None


def pdf_text(path: Path) -> str:
    """提取 PDF 文本；文字太少（扫描件）时渲染成图后走 OCR。"""
    import pdfplumber
    texts = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    joined = "\n".join(texts).strip()
    if len(re.sub(r"\s", "", joined)) >= 12:      # 文字型 PDF
        return joined
    lines: list[str] = []
    for png in _render_pdf_pages(path):
        lines.extend(ocr_image_bytes(png))
    return "\n".join(lines)


# ---------------------------------------------------------------- OFD

def _ofd_text_objects(path: Path) -> list[str]:
    """OFD 文本都在各 Page 的 Content.xml 的 TextObject/TextCode 里。"""
    lines: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".xml"):
                continue
            if not ("/pages/" in name.lower().replace("\\", "/")):
                continue
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            for el in root.iter():
                tag = el.tag.split("}")[-1]
                if tag == "TextObject":
                    parts = [
                        t.text or ""
                        for t in el.iter()
                        if t.tag.split("}")[-1] == "TextCode"
                    ]
                    text = "".join(parts).strip()
                    if text:
                        lines.append(text)
    return lines


def ofd_text(path: Path) -> str:
    lines = _ofd_text_objects(path)
    if lines:
        return "\n".join(lines)
    # 个别 OFD 结构特殊时退化为暴力抓取全部 XML 文本
    chunks: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".xml"):
                try:
                    root = ET.fromstring(zf.read(name))
                except ET.ParseError:
                    continue
                for el in root.iter():
                    if el.text and el.text.strip():
                        chunks.append(el.text.strip())
    return "\n".join(chunks)


# ---------------------------------------------------------------- 图片

def image_text(path: Path) -> str:
    return "\n".join(ocr_image_bytes(path.read_bytes()))


# ---------------------------------------------------------------- 缩略图

def make_thumb(stored: Path, thumb_path: Path, max_w: int = 480) -> Optional[str]:
    """PDF 取首页渲染；图片直接缩放。成功返回 thumb_path 名字。"""
    try:
        pil = None
        if stored.suffix.lower() == ".pdf":
            rendered = render_pdf_page(stored, 960, thumb_path.with_suffix(".png"))
            if rendered is None:
                return None
            from PIL import Image
            pil = Image.open(rendered)
            pil.load()
        else:
            from PIL import Image
            pil = Image.open(stored)
            pil.load()
        if pil is None:
            return None
        if pil.width > max_w:
            h = int(pil.height * max_w / pil.width)
            pil = pil.resize((max_w, h))
        pil.convert("RGB").save(thumb_path, format="JPEG", quality=82)
        return thumb_path.name
    except Exception:
        return None


def extract_text(path: Path, file_type: str) -> str:
    if file_type == "pdf":
        return pdf_text(path)
    if file_type == "ofd":
        return ofd_text(path)
    return image_text(path)
