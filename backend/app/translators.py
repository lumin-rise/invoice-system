"""翻译引擎层：多服务商 + 内存缓存。

- mymemory  MyMemory 免费接口（无需密钥，默认引擎；长句质量一般，日限 5 万字符）
- tencent   腾讯云机器翻译 TMT（每月 500 万字符免费，国内最稳，推荐追求质量时用）
- baidu     百度翻译开放平台（标准版每月 5 万字符免费）
- deepl     DeepL Free（每月 50 万字符，国内网络不一定可达）
- bing      Bing 免费接口（无需 key，国内网络大多不可达，备选）

统一入口：translate_many(texts: list[str]) -> list[str]
未配置服务商时自动使用免费的 mymemory。
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import urllib.request

from .config import DATA_DIR

CONFIG_FILE = DATA_DIR / "translate_config.json"

PROVIDERS = {
    "mymemory": "MyMemory 免费接口（无需密钥，开箱即用）",
    "tencent": "腾讯云机器翻译（500万字/月免费，更精准）",
    "baidu": "百度翻译开放平台（5万字/月免费）",
    "deepl": "DeepL Free（50万字/月）",
    "bing": "Bing 免费接口（无需 key，备选）",
}

# 各引擎单次请求的字符上限
ENGINE_LIMITS = {"mymemory": 480, "tencent": 1800, "baidu": 1800, "deepl": 1800, "bing": 1800}
DEFAULT_PROVIDER = "mymemory"

_cache: dict[str, str] = {}


# ---------------------------------------------------------------- 配置

def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"provider": "", "keys": {}}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


def mask(v: str) -> str:
    if not v:
        return ""
    return v[:4] + "****" + v[-4:] if len(v) > 8 else "****"


def config_summary() -> dict:
    cfg = load_config()
    keys = {k: {kk: mask(vv) for kk, vv in v.items()} for k, v in cfg.get("keys", {}).items()}
    return {"provider": cfg.get("provider", ""), "providers": PROVIDERS, "keys": keys}


def _key(cfg: dict, provider: str, name: str) -> str:
    return cfg.get("keys", {}).get(provider, {}).get(name, "")


# ---------------------------------------------------------------- 各引擎

def _post_json(url: str, body, headers: dict, timeout: int = 15):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8") if isinstance(body, (list, dict)) else body,
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _tencent(texts: list[str], cfg: dict) -> list[str]:
    """腾讯云 TMT v3（TC3-HMAC-SHA256 签名）。"""
    sid = _key(cfg, "tencent", "secret_id")
    skey = _key(cfg, "tencent", "secret_key")
    service, host = "tmt", "tmt.tencentcloudapi.com"
    out: list[str] = []
    for text in texts:
        payload = json.dumps({"SourceText": text, "Source": "en", "Target": "zh",
                              "ProjectId": 0}, ensure_ascii=False)
        ts = int(time.time())
        date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        canonical = ("POST\n/\n\n"
                     f"content-type:application/json; charset=utf-8\n"
                     f"host:{host}\nx-tc-action:texttranslate\n"
                     f"\ncontent-type;host;x-tc-action\n{payload}")
        scope = f"{date}/{service}/tc3_request"
        h2 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        k_date = hmac.new(f"TC3{skey}".encode(), date.encode(), hashlib.sha256).digest()
        k_srv = hmac.new(k_date, service.encode(), hashlib.sha256).digest()
        k_sign = hmac.new(k_srv, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(k_sign, h2.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": "TextTranslate", "X-TC-Version": "2018-03-21",
            "X-TC-Timestamp": str(ts), "X-TC-Signature": signature,
            "Authorization": (f"TC3-HMAC-SHA256 Credential={sid}/{scope}, "
                              f"SignedHeaders=content-type;host;x-tc-action, Signature={signature}"),
        }
        data = _post_json(f"https://{host}", payload, headers)
        resp = data.get("Response", {})
        if "Error" in resp:
            raise RuntimeError(f"腾讯翻译: {resp['Error'].get('Code')} {resp['Error'].get('Message')}")
        out.append(resp["TargetText"])
        time.sleep(0.12)        # 免费档限频 5 QPS
    return out


def _baidu(texts: list[str], cfg: dict) -> list[str]:
    appid = _key(cfg, "baidu", "app_id")
    key = _key(cfg, "baidu", "app_key")
    out = []
    for text in texts:
        salt = str(int(time.time()))
        sign = hashlib.md5((appid + text + salt + key).encode("utf-8")).hexdigest()
        q = urllib.parse.urlencode({"q": text, "from": "en", "to": "zh",
                                    "appid": appid, "salt": salt, "sign": sign})
        req = urllib.request.Request("https://fanyi-api.baidu.com/api/trans/vip/translate?" + q)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("error_code"):
            raise RuntimeError(f"百度翻译: {data['error_code']} {data.get('error_msg')}")
        out.append("".join(part["dst"] for part in data["trans_result"]))
        time.sleep(0.35)        # 免费档限频
    return out


def _deepl(texts: list[str], cfg: dict) -> list[str]:
    key = _key(cfg, "deepl", "api_key")
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    data = _post_json(f"https://{host}/v2/translate",
                      {"text": texts, "target_lang": "ZH"},
                      {"Authorization": f"DeepL-Auth-Key {key}",
                       "Content-Type": "application/json"})
    return [t["text"] for t in data["translations"]]


def _bing(texts: list[str], cfg: dict) -> list[str]:
    data = _post_json("https://api.edge.microsoft.com/translate/translate?from=en&to=zh-Hans",
                      [{"Text": t} for t in texts],
                      {"Content-Type": "application/json"})
    return [d["translations"][0]["text"] for d in data]


def _mymemory_one(text: str, email: str) -> str:
    params = {"langpair": "en|zh-CN", "q": text}
    if email:
        params["de"] = email          # 提供邮箱可将每日免费额度提升到 5 万字符
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("responseStatus") != 200 or data.get("quotaFinished"):
        raise RuntimeError(f"MyMemory: {data.get('responseDetails') or '配额或请求受限'}")
    return html.unescape(data["responseData"]["translatedText"])


def _split_long(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for seg in re.split(r"(?<=[.。;;!!？？])", text):
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


def _mymemory(texts: list[str], cfg: dict) -> list[str]:
    """单请求限 500 字符 → 逐段请求 + 4 线程并发。"""
    email = _key(cfg, "mymemory", "email")
    jobs = []
    for t in texts:
        jobs.extend(_split_long(t, 480))
    with ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(lambda s: _mymemory_one(s, email), jobs))
    # 按切分前的分段合并
    out, idx = [], 0
    for t in texts:
        n = len(_split_long(t, 480))
        out.append(" ".join(parts[idx:idx + n]))
        idx += n
    return out


ENGINES = {"mymemory": _mymemory, "tencent": _tencent, "baidu": _baidu,
           "deepl": _deepl, "bing": _bing}


def _chunks(texts: list[str], limit: int = 1800):
    """按字符长度分批（各引擎单请求都有上限）。"""
    batch, size = [], 0
    for t in texts:
        n = min(len(t), limit)
        if batch and size + n > limit:
            yield batch
            batch, size = [], 0
        batch.append(t)
        size += n
    if batch:
        yield batch


def translate_many(texts: list[str]) -> list[str]:
    """批量翻译（去重 + 缓存 + 分批调用）。texts 与返回一一对应。"""
    cfg = load_config()
    provider = cfg.get("provider") or DEFAULT_PROVIDER
    if provider not in ENGINES:
        raise RuntimeError(f"未知的服务商: {provider}")

    uniq = list(dict.fromkeys(t for t in texts if t.strip()))
    todo = [t for t in uniq if t not in _cache]

    engine = ENGINES[provider]
    for batch in _chunks(todo, ENGINE_LIMITS.get(provider, 1800)):
        result = engine(batch, cfg)
        if len(result) != len(batch):
            raise RuntimeError(f"翻译服务返回条数不符（{len(batch)}→{len(result)}）")
        for src, dst in zip(batch, result):
            _cache[src] = dst
    return [_cache.get(t, t) if t.strip() else t for t in texts]


def test_engine() -> dict:
    cfg = load_config()
    provider = cfg.get("provider") or DEFAULT_PROVIDER
    sample = ["Quality defect classification standard"]
    try:
        out = translate_many(sample)
        return {"ok": True, "provider": provider, "sample": out[0]}
    except Exception as e:
        return {"ok": False, "provider": provider, "msg": str(e)}
