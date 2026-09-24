"""翻译引擎：MyMemory 免费接口（无需密钥）+ 内置术语表 + 并发提速。

提速策略：
1. 内置术语表：QC 单据里大量重复的固定词（Zone A、Any zone、Critical…、
   FB01 这类代码、单个字母）直接查表或跳过，不发网络请求
2. 翻译缓存：同一文本本次进程内只请求一次
3. 8 线程并发请求，长句按句子边界切分到单请求 500 字符限制内
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import DATA_DIR

CONFIG_FILE = DATA_DIR / "translate_config.json"

MAX_QUERY = 480          # MyMemory 单请求上限 500 字符
WORKERS = 4              # 并发线程数（太高会触发 429 限频）

# ---------------------------------------------------------------- 内置术语表

GLOSSARY = {
    "zone a": "A区", "zone b": "B区", "any zone": "任意区域",
    "critical": "致命", "major": "严重", "minor": "轻微",
    "critical, major, minor": "致命/严重/轻微", "major, minor": "严重/轻微",
    "critical, major": "致命/严重", "major minor": "严重/轻微",
    "outside": "外露处", "inside": "内侧", "inside and hidden": "内侧隐蔽处",
    "main body": "大身", "under arm": "腋下",
    "defect code": "缺陷代码", "description": "描述",
    "major if found in zone a; minor if found in zone b": "A区为严重；B区为轻微",
    "critical if found in any zone": "任意区域发现即为致命",
    "minor if found in any zone": "任意区域均为轻微",
    "major if found in any zone": "任意区域均为严重",
    "apparel": "服装", "category": "类别",
    "caterory: apparel": "类别：服装", "category: apparel": "类别：服装",
    "critical if major if": "", "others (must specify in note)": "其他（须在备注中说明）",
}

# 完全不需要翻译的文本（代码、编号、单个字母等）
_SKIP_RE = re.compile(r"^(?:[A-Z]{1,3}\d{1,4}[A-Za-z]?|[A-Z]|[a-z]|\d+(?:\.\d+)?[\"''”″]?|[/\-.•…,+&%()\s]*)$")


def is_translatable(text: str) -> bool:
    t = (text or "").strip()
    if not t or not re.search(r"[A-Za-z]", t):
        return False
    if _SKIP_RE.match(t):
        return False
    return True


def lookup(text: str) -> str | None:
    """术语表精确命中（忽略大小写/首尾空白），未命中返回 None。"""
    return GLOSSARY.get((text or "").strip().lower())


# ---------------------------------------------------------------- 配置

def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"email": ""}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


def config_summary() -> dict:
    cfg = load_config()
    return {"engine": "mymemory", "email": cfg.get("email", ""),
            "daily_limit": "50000 字符/天（填邮箱后）", "free": True}


def save_config_from(body: dict) -> dict:
    cfg = {"email": str(body.get("email", "")).strip()}
    save_config(cfg)
    return config_summary()


# ---------------------------------------------------------------- MyMemory 请求

def _mm_request(text: str, email: str) -> str:
    """单次请求（带限频退避重试）。"""
    params = {"langpair": "en|zh-CN", "q": text}
    if email:
        params["de"] = email
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    last_err: Exception | None = None
    for attempt in range(6):                       # 429/网络抖动指数退避重试
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("responseStatus") != 200 or data.get("quotaFinished"):
                raise RuntimeError(f"MyMemory 免费额度受限：{data.get('responseDetails') or '今日额度已用完，明天再试或在设置里填写邮箱提升额度'}")
            return html.unescape(data["responseData"]["translatedText"])
        except RuntimeError:
            raise                                   # 额度类错误重试无意义
        except Exception as e:                      # 429 / 超时 / 连接重置
            last_err = e
            time.sleep(min(20, 1.5 * (2 ** attempt)))
    raise RuntimeError(f"翻译请求多次失败: {last_err}")


def _split_long(text: str, limit: int = MAX_QUERY) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for seg in re.split(r"(?<=[.。;;!!？？])\s*", text):
        if not seg:
            continue
        if len(cur) + len(seg) <= limit:
            cur += seg
        else:
            if cur:
                parts.append(cur)
            cur = seg
    if cur:
        parts.append(cur)
    return parts or [text[:limit]]


_cache: dict[str, str] = {}
_pool = ThreadPoolExecutor(max_workers=WORKERS)


def translate_many(texts: list[str]) -> list[str]:
    """批量翻译：多条短段拼接为一次请求（换行分隔，实测行数可完整保留），
    拆回后行数不符才降级逐条；术语表命中与缓存不发请求。"""
    email = load_config().get("email", "")
    todo: list[str] = []
    seen: set[str] = set()
    for t in texts:
        t = t.strip()
        if not _needs_translation_remote(t) or t in seen:
            continue
        seen.add(t)
        if t not in _cache:
            todo.append(t)

    if todo:
        # 把每个待译文本切成 ≤480 字符的片段，凑成若干组（每组总长 ≤480），
        # 一组 = 一次请求（组内片段以换行分隔，MyMemory 可完整保留行数）
        part_text: list[str] = []
        todo_parts: list[list[int]] = []
        groups: list[list[int]] = []
        cur: list[int] = []
        size = 0
        for t in todo:
            mine: list[int] = []
            for piece in _split_long(t):
                pi = len(part_text)
                part_text.append(piece)
                mine.append(pi)
                n = len(piece) + 1
                if cur and size + n > MAX_QUERY:
                    groups.append(cur)
                    cur, size = [], 0
                cur.append(pi)
                size += n
            todo_parts.append(mine)
        if cur:
            groups.append(cur)

        def run_group(idxs: list[int]) -> dict[int, str]:
            joined = "\n".join(part_text[i] for i in idxs)
            out = _mm_request(joined, email)
            lines = [l.strip() for l in out.split("\n")]
            if len(lines) != len(idxs):             # 行数错位 → 该组逐条兜底
                return {i: _mm_request(part_text[i], email) for i in idxs}
            return {i: l for i, l in zip(idxs, lines)}

        part_results: dict[int, str] = {}
        for res in _pool.map(run_group, groups):
            part_results.update(res)

        # 按片段归属拼回每个文本的译文
        for t, mine in zip(todo, todo_parts):
            _cache[t] = " ".join(part_results[pi] for pi in mine)

    out = []
    for t in texts:
        s = t.strip()
        if not s:
            out.append(t)
            continue
        g = lookup(s)
        if g is not None:
            out.append(g)
        else:
            out.append(_cache.get(s, s))
    return out


def _needs_translation_remote(t: str) -> bool:
    t = (t or "").strip()
    if not t or not re.search(r"[A-Za-z]", t):
        return False
    if _SKIP_RE.match(t):
        return False
    if t.lower() in GLOSSARY:
        return False
    return True


def test_engine() -> dict:
    try:
        out = translate_many(["Quality defect classification standard"])
        return {"ok": True, "engine": "mymemory", "sample": out[0]}
    except Exception as e:
        return {"ok": False, "engine": "mymemory", "msg": str(e)}
