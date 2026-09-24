"""从原始文本（PDF 文字层或 OCR 行）里抽取发票字段。

思路：中文发票/票据版面差异大，先构造一个去掉全部空白的“压缩文本”
用于关键词定位，再配合逐行文本做销售方、项目名称等结构化抽取。
所有字段在网页里都可人工修正，解析目标是把 90% 常见票填对。
"""
from __future__ import annotations

import re
from datetime import datetime

# ---------------------------------------------------------------- helpers

CN = r"\u4e00-\u9fa5"


def condense(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _tofloat(s: str) -> float:
    return float(s.replace(",", ""))


# ---------------------------------------------------------------- 字段抽取

def get_invoice_no(c: str) -> str:
    m = re.search(r"发票号码[:：]?\s*(\d{6,20})", c)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{20})(?!\d)", c)      # 数电票 20 位
    if m:
        return m.group(1)
    m = re.search(r"发票号码[:：]?\s*(\d{8})", c)
    return m.group(1) if m else ""


def get_date_time(text: str, c: str) -> tuple[str, str]:
    """返回 (yyyy-mm-dd, HH:MM)。优先乘车/行程时间，其次开票日期。"""
    date = ""
    time_hm = ""

    # 乘车/发车时间：2026年09月12日18:23开 / 行程时间2026-09-12 18:23
    m = re.search(
        r"(?:乘车|行程|发车|开车|旅行)[^0-9]{0,6}"
        r"(\d{4})[年\-/.](\d{1,2})[月\-/.](\d{1,2})日?[^\d]{0,4}"
        r"([01]?\d|2[0-3])[：:]([0-5]\d)",
        c,
    )
    if not m:
        m = re.search(
            r"(\d{4})[年\-/.](\d{1,2})[月\-/.](\d{1,2})日?"
            r"[^\d：:]{0,10}([01]?\d|2[0-3])[：:]([0-5]\d)\s*开",
            c,
        )
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%Y-%m-%d"), f"{int(m.group(4)):02d}:{m.group(5)}"
        except ValueError:
            pass

    # 开票日期
    m = re.search(
        r"开票日期[:：]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text
    ) or re.search(
        r"开票日期[:：]?\s*(\d{4})[年\-/.](\d{1,2})[月\-/.](\d{1,2})", c
    )
    if m:
        try:
            date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            date = ""

    if not date:
        m = re.search(r"(\d{4})[年\-/.](\d{1,2})[月\-/.](\d{1,2})日?", c)
        if m:
            try:
                date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
            except ValueError:
                date = ""
    if not date:
        m = re.search(r"(?<!\d)(\d{4})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)", c)
        if m:
            try:
                date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
            except ValueError:
                date = ""

    # 时间（任意 HH:MM）
    tm = re.search(r"([01]?\d|2[0-3])[：:]([0-5]\d)", text)
    if tm:
        time_hm = f"{int(tm.group(1)):02d}:{tm.group(2)}"
    return date, time_hm


def get_amount(c: str) -> tuple[float | None, float | None]:
    """返回 (价税合计, 税额)。"""
    amount = None
    m = re.search(
        r"价税合计.{0,12}?(?:大写[^¥￥\d]{0,12})?(?:[（(]小写[）)])?[¥￥]\s*([0-9,]+\.\d{2})",
        c,
    )
    if m:
        amount = _tofloat(m.group(1))
    if amount is None:
        m = re.search(r"[（(]小写[）)][¥￥]?\s*([0-9,]+\.\d{2})", c)
        if m:
            amount = _tofloat(m.group(1))
    if amount is None:  # 火车票 / 行程单：票价 ￥12.50元
        m = re.search(r"票价[:：]?[¥￥]?\s*([0-9,]+\.\d{2})", c)
        if m:
            amount = _tofloat(m.group(1))
    if amount is None:  # 最后一个 ￥xx.xx
        ms = re.findall(r"[¥￥]\s*([0-9]{1,7}(?:,\d{3})*\.\d{2})", c)
        if ms:
            amount = _tofloat(ms[-1])

    tax = None
    m = re.search(r"税额[¥￥]\s*([0-9,]+\.\d{2})", c)
    if m:
        tax = _tofloat(m.group(1))
    elif amount is not None:
        # 常见版式：合计 ￥92.79 ￥5.57 —— 第二个金额即税额
        m2 = re.search(r"合计[¥￥]([0-9,]+\.\d{2})[¥￥]([0-9,]+\.\d{2})", c)
        if m2:
            tax = _tofloat(m2.group(2))
    return amount, tax


def get_seller(lines: list[str], c: str) -> str:
    for ln in lines:
        cc = condense(ln)
        if ("销售" in cc or "销 售" in ln) and "名称" in cc and ":" in ln:
            val = ln.split(":")[-1].split("：")[-1].strip()
            val = re.sub(r"^(销售方名称|销售方|销售|名称)[:：]?", "", val).strip()
            if val and not re.match(r"^\d+$", val):
                return val[:40]
    m = re.search(r"销售(?:方)?名称[:：]([^开票项目购买价税备注]{2,40})", c)
    if m:
        return m.group(1)[:40]
    return ""


def get_title(lines: list[str]) -> str:
    """项目名称，如 *运输服务*客运服务费 → 运输服务客运服务费。"""
    for ln in lines:
        if "*" in ln:
            cc = condense(ln)
            m = re.search(r"\*([^*\d¥￥]{1,15})\*([^*\d¥￥]{1,30})", cc)
            if m:
                return (m.group(1) + m.group(2))[:30]
    return ""


# ---------------------------------------------------------------- 分类

TRAIN_FAST = re.compile(r"车次[:：]?[GC]\d{1,4}")
TRAIN_D = re.compile(r"车次[:：]?[D]\d{1,4}")
TRAIN_SLOW = re.compile(r"车次[:：]?[KTZ]?\d{1,4}")

TRAVEL_KEYS = (
    "滴滴", "打车", "出租", "网约", "客运", "运输服务", "行程", "铁路", "火车",
    "高铁", "动车", "机票", "航空", "民航", "客票", "车票", "检票", "乘车",
    "出行", "旅客", "出租车", "住宿", "酒店", "宾馆",
)


def classify(c: str, car_no: str = "") -> tuple[str, str, str]:
    """返回 (category, item, warn)。item 用于 Expenses report 的 Item 列。"""
    if "滴滴" in c:
        return "travel", "滴滴打车", ""
    if "出租" in c:
        return "travel", "出租车", ""
    if TRAIN_FAST.search(c) or re.search(r"(?<!\d)[GC]\d{3,4}(?!\d)", car_no) or "高铁" in c:
        return "travel", "高铁", ""
    if TRAIN_D.search(c) or re.search(r"(?<!\d)D\d{3,4}(?!\d)", car_no) or "动车" in c:
        return "travel", "动车", ""
    if TRAIN_SLOW.search(c) or "火车" in c:
        return "travel", "火车", ""
    if ("铁路" in c or "客票" in c) and "票" in c:
        return "travel", "火车", ""
    if "航空" in c or "机票" in c or "民航" in c or "登机" in c:
        return "travel", "机票", ""
    if "住宿" in c or "酒店" in c or "宾馆" in c:
        return "travel", "住宿", ""
    if "客运" in c or "运输服务" in c or "行程" in c or "打车" in c:
        return "travel", "交通", ""
    if any(k in c for k in TRAVEL_KEYS):
        return "travel", "交通", ""
    return "other", "", ""


# ---------------------------------------------------------------- 路程

def _clean(seg: str) -> str:
    return seg.strip("：: ，。；、·*#")


def get_route(text: str, c: str) -> str:
    # 1) 车站 A至B / A→B / A-B / from A to B（12306 英文模板）/ 发站-到站 /
    #    出发站-到达站（铁路电子客票常见字段）
    m = re.search(
        rf"([{CN}]{{2,8}}站|[A-Za-z]{{2,12}}站)\s*[至→➔➝—–\-]{{1,2}}\s*([{CN}]{{2,8}}站|[A-Za-z]{{2,12}}站)",
        text,
    ) or re.search(
        rf"(?:from|FROM|始发)\s*[:：]?\s*([{CN}]{{2,8}}站?)\s*(?:to|TO|→|到达|终到)[:：]?\s*([{CN}]{{2,8}}站?)",
        text,
    ) or re.search(
        r"发站[:：]\s*([" + CN + r"]{2,8}站?)[\s,，]*到站[:：]\s*([" + CN + r"]{2,8}站?)",
        text,
    ) or re.search(
        rf"出发站[:：]?\s*([{CN}]{{2,8}}站?)[\s,，]+到达站[:：]?\s*([{CN}]{{2,8}}站?)",
        text,
    )
    if m:
        return f"{_clean(m.group(1))}至{_clean(m.group(2))}"

    # 1b) 同一行仅以空格分隔的两个站名（OCR 时箭头常被丢成空格）
    for ln in text.splitlines():
        m = re.search(rf"([{CN}]{{2,8}}站)\s+([{CN}]{{2,8}}站)", ln)
        if m:
            return f"{m.group(1)}至{m.group(2)}"

    m = re.search(rf"([{CN}]{{2,8}})站[至→—–\-]{{1,2}}([{CN}]{{2,8}})站", c) or re.search(
        rf"(?<![{CN}])([{CN}]{{2,8}})至([{CN}]{{2,10}})(?![{CN}站])", c
    )
    if m:
        return f"{m.group(1)}至{m.group(2)}"

    # 2) 起点/终点（滴滴行程单）
    m = re.search(rf"起点[:：]?(.{{2,30}}?)终点[:：]?(.{{2,30}}?)(?=金额|合计|里程|乘客|车型|行驶|发票|$)", c)
    if m:
        return f"{_clean(m.group(1))}至{_clean(m.group(2))}"

    # 3) 上车点/下车点
    m = re.search(rf"上车点[:：]?(.{{2,30}}?)下车点[:：]?(.{{2,30}}?)(?=金额|里程|发票|$)", c)
    if m:
        return f"{_clean(m.group(1))}至{_clean(m.group(2))}"

    # 4) 机场/城市对（机票行程单）
    m = re.search(rf"([{CN}]{{2,6}})(?:机场|国际机场)[至→—–\-]{{1,2}}([{CN}]{{2,6}})(?:机场|国际机场)", c)
    if m:
        return f"{m.group(1)}至{m.group(2)}"
    return ""


# ---------------------------------------------------------------- Location 规则
# Expenses report 的 Location 列按票据类型走不同规则（后续规则在此扩展）：
#   高铁/动车/火车 → 统一成「A站到B站」（如 赣州站到长沙站），无站名的补「站」
#   滴滴打车/出租车 → 不自动填，留空由人工补充

RAIL_ITEMS = {"高铁", "动车", "火车"}
TAXI_ITEMS = {"滴滴打车", "出租车"}


def format_rail_location(loc: str) -> str:
    if not loc:
        return ""
    parts = [p.strip("：: ，。；、") for p in re.split(r"至|到|—|–|→|➔|\-{1,2}", loc) if p.strip()]
    if len(parts) != 2:
        return loc
    a, b = parts
    if not a.endswith("站"):
        a += "站"
    if not b.endswith("站"):
        b += "站"
    return f"{a}到{b}"


def apply_location_rules(item: str, location: str) -> str:
    if not location:
        return ""
    if item in RAIL_ITEMS:
        return format_rail_location(location)
    if item in TAXI_ITEMS:
        return ""          # 打车路程人工补充
    return location


# 真实铁路电子客票的 OCR 版式：出发站/到达站各占一行，中间夹车次号，
# 没有任何连接符（“兴国站\nK8753\n赣州站”）。按行扫描前两个不同的站名行。
_RAIL_HEADER_WORDS = {"到达站", "出发站", "终到站", "到站", "发站", "站"}


def rail_stations_from_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if (
            re.fullmatch(rf"[{CN}]{{2,8}}站", s)
            and s not in _RAIL_HEADER_WORDS
            and s not in out
        ):
            out.append(s)
            if len(out) == 2:
                break
    return out


# ---------------------------------------------------------------- 入口

def parse_fields(text: str) -> dict:
    c = condense(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    invoice_no = get_invoice_no(c)
    date, tm = get_date_time(text, c)
    amount, tax = get_amount(c)
    seller = get_seller(lines, c)
    title = get_title(lines)
    category, item, _ = classify(c)
    location = get_route(text, c) if category == "travel" else ""
    if item in RAIL_ITEMS and not location:
        stations = rail_stations_from_lines(lines)
        if stations:
            location = "至".join(stations)
    location = apply_location_rules(item, location)

    # 火车票金额兜底：取文本里最大的金额（票价往往是唯一大写金额）
    if amount is None and category == "travel":
        ms = [float(x.replace(",", "")) for x in re.findall(r"(\d{1,6}\.\d{2})", c)]
        if ms:
            amount = max(ms)

    return {
        "invoice_no": invoice_no,
        "date": date,
        "time": tm,
        "amount": amount,
        "tax": tax,
        "seller": seller,
        "title": title,
        "category": category,
        "item": item,
        "location": location,
    }
