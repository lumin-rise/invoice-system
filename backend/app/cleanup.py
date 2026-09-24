"""每日自动清理。

策略（保留期默认 30 天，可用环境变量 RETENTION_DAYS 调整）：
- 每天凌晨 03:00 执行一次：
  1. 上传时间超过保留期的发票：记录 + 原文件 + 缩略图 + Bills 渲染图一起删除
  2. 孤儿文件：uploads/thumbs 里不被任何记录引用、且修改时间超过 24h 的文件删除
- 服务启动时先做一次孤儿清理（秒级，防止反复上传积累的副本占磁盘）
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta

from . import config, store

RETENTION_DAYS = max(1, int(os.environ.get("RETENTION_DAYS", "30")))


def derived_names(inv) -> set[str]:
    """一条记录占用的所有文件名。"""
    names = {inv.stored_name, inv.thumb_name,
             f"{inv.id}_bill.png", f"{inv.id}_bill.jpg"}
    return {n for n in names if n}


def referenced_names() -> set[str]:
    refs: set[str] = set()
    for inv in store.load_invoices():
        refs |= derived_names(inv)
    return refs


def _unlink(path) -> bool:
    try:
        if path.exists():
            path.unlink()
            return True
    except Exception:
        pass
    return False


def full_cleanup() -> dict:
    cutoff = time.time() - RETENTION_DAYS * 86400
    removed_records = 0
    for inv in store.load_invoices():
        if inv.created_at < cutoff:
            if inv.stored_name:
                _unlink(config.UPLOAD_DIR / inv.stored_name)
            if inv.thumb_name:
                _unlink(config.THUMB_DIR / inv.thumb_name)
            _unlink(config.THUMB_DIR / f"{inv.id}_bill.png")
            _unlink(config.THUMB_DIR / f"{inv.id}_bill.jpg")
            store.remove(inv.id)
            removed_records += 1
    orphans = orphan_sweep()
    stats = {"removed_records": removed_records, "removed_orphans": orphans,
             "retention_days": RETENTION_DAYS}
    print(f"[cleanup] 过期记录 {removed_records} 条，孤儿文件 {orphans} 个"
          f"（保留期 {RETENTION_DAYS} 天）")
    return stats


def orphan_sweep() -> int:
    refs = referenced_names()
    now = time.time()
    removed = 0
    for d in (config.UPLOAD_DIR, config.THUMB_DIR):
        if not d.exists():
            continue
        for f in d.iterdir():
            if not f.is_file() or f.name in refs:
                continue
            try:
                if now - f.stat().st_mtime < 86400:   # 24h 内可能是正在处理的新文件
                    continue
            except OSError:
                continue
            removed += _unlink(f)
    return removed


async def daily_loop():
    await asyncio.to_thread(orphan_sweep)
    while True:
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
        await asyncio.sleep(max(1, (next_run - now).total_seconds()))
        try:
            await asyncio.to_thread(full_cleanup)
        except Exception as e:
            print(f"[cleanup] 执行失败: {e}")
