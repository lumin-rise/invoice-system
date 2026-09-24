"""数据模型：一张发票 = 一条记录。

category: travel  → 同时进入 Expenses report（路程表）
          other   → 只进入 Bills（按时间顺序贴图）
no_bill:  True 表示该行程无发票（如“工厂已付”），只出现在 Expenses report，
          不占用 Bills 编号。
"""
from __future__ import annotations

import time as _time
import uuid
from typing import Optional

from pydantic import BaseModel, Field

EDITABLE_FIELDS = {
    "item", "location", "amount", "date", "time", "category",
    "no_bill", "note", "hkd", "title",
}


class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    filename: str = ""                    # 原始文件名
    file_type: str = ""                   # pdf / ofd / image / manual
    stored_name: Optional[str] = None     # data/uploads 里的文件名
    thumb_name: Optional[str] = None      # data/thumbs 里的缩略图
    invoice_no: str = ""                  # 发票号码
    title: str = ""                       # 品名（项目名称）
    date: str = ""                        # yyyy-mm-dd（开票日期或乘车日期）
    time: str = ""                        # HH:MM（若有）
    amount: Optional[float] = None        # 价税合计
    tax: Optional[float] = None           # 税额
    seller: str = ""                      # 销售方
    category: str = "other"               # travel / other
    item: str = ""                        # Expenses report 的 Item（滴滴打车/高铁…）
    location: str = ""                    # Expenses report 的 Location（A至B）
    hkd: str = ""                         # HK$ 列，默认留空
    no_bill: bool = False                 # 无发票（工厂已付）
    note: str = ""                        # 备注（“工厂已付”等）
    source: str = "upload"                # upload / manual
    parse_ok: bool = True
    parse_msg: str = ""                   # 解析失败原因
    raw_text: str = ""                    # 提取的原始文本（排查用）
    created_at: float = Field(default_factory=_time.time)

    @property
    def sort_dt(self) -> str:
        """排序键：日期+时间，缺日期的排最后并保持上传顺序。"""
        if self.date:
            return f"{self.date} {self.time or '00:00'}"
        return "9999-12-31 23:59"


class InvoicePatch(BaseModel):
    item: Optional[str] = None
    location: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    time: Optional[str] = None
    category: Optional[str] = None
    no_bill: Optional[bool] = None
    note: Optional[str] = None
    hkd: Optional[str] = None
    title: Optional[str] = None
    invoice_no: Optional[str] = None


def sorted_invoices(invoices: list[Invoice]) -> list[Invoice]:
    return sorted(invoices, key=lambda i: (i.sort_dt, i.created_at))
