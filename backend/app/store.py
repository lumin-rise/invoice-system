"""本地会话存储：invoices 保存在 data/session.json，原文件在 data/uploads。"""
from __future__ import annotations

import json
import threading
from typing import Optional

from .config import SESSION_FILE
from .models import Invoice

_lock = threading.Lock()


def load_invoices() -> list[Invoice]:
    if not SESSION_FILE.exists():
        return []
    try:
        items = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        return [Invoice(**it) for it in items]
    except Exception:
        return []


def save_invoices(invoices: list[Invoice]) -> None:
    with _lock:
        SESSION_FILE.write_text(
            json.dumps([i.model_dump() for i in invoices], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )


def get_invoice(inv_id: str) -> Optional[Invoice]:
    for inv in load_invoices():
        if inv.id == inv_id:
            return inv
    return None


def upsert(inv: Invoice) -> None:
    invoices = load_invoices()
    for i, old in enumerate(invoices):
        if old.id == inv.id:
            invoices[i] = inv
            break
    else:
        invoices.append(inv)
    save_invoices(invoices)


def remove(inv_id: str) -> bool:
    invoices = load_invoices()
    keep = [i for i in invoices if i.id != inv_id]
    if len(keep) == len(invoices):
        return False
    save_invoices(keep)
    return True


def clear() -> None:
    save_invoices([])
