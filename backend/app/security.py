"""认证与安全核心。

- 口令：scrypt（内存困难型，抗 GPU/ASIC 爆破），随机盐，hmac.compare_digest 比较
- 会话：服务端随机 token，Cookie 只存不透明 id；服务端只存 token 的 sha256，
  文件泄露也无法直接冒用；滑动续期
- 登录限流：同一 (IP, 用户名) 连续失败 5 次锁定 15 分钟，成功即清零
- Cookie：HttpOnly + SameSite=Strict（配合同源 API 天然抗 CSRF）
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

from .config import DATA_DIR

AUTH_FILE = DATA_DIR / "auth.json"
HINT_FILE = DATA_DIR / "初始密码.txt"
SESSION_FILE = DATA_DIR / "sessions.json"

SESSION_COOKIE = "inv_session"
SESSION_TTL = 7 * 24 * 3600          # 7 天，滑动续期
RENEW_THRESHOLD = SESSION_TTL // 2
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60

_lock = threading.Lock()
_sessions: dict[str, float] = {}      # sha256(token) -> 过期时间
_fails: dict[str, tuple[int, float]] = {}   # (ip,username) -> (失败次数, 锁定截止)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_private(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        import os
        os.chmod(path, 0o600)   # 尽力限制权限（Windows 上为只读位，Linux/macOS 为 owner-only）
    except Exception:
        pass


# ---------------------------------------------------------------- 口令

def hash_password(pw: str) -> dict:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return {"algo": "scrypt", "n": 2**14, "r": 8, "p": 1, "salt": salt.hex(), "hash": h.hex()}


def verify_password(pw: str, rec: dict) -> bool:
    try:
        h = hashlib.scrypt(
            pw.encode("utf-8"),
            salt=bytes.fromhex(rec["salt"]),
            n=int(rec.get("n", 2**14)), r=int(rec.get("r", 8)),
            p=int(rec.get("p", 1)), dklen=32,
        )
        return hmac.compare_digest(h.hex(), rec["hash"])
    except Exception:
        return False


def get_account() -> dict | None:
    d = _load_json(AUTH_FILE, None)
    if isinstance(d, dict) and "hash" in d and "username" in d:
        return d
    return None


def set_account(username: str, password: str) -> None:
    rec = {"username": username, **hash_password(password), "updated_at": time.time()}
    _write_private(AUTH_FILE, rec)


def ensure_bootstrap() -> tuple[str, str] | None:
    """首次启动自动创建管理员账号，返回 (用户名, 初始密码)；已存在返回 None。"""
    if get_account():
        return None
    username, password = "admin", secrets.token_urlsafe(9)   # 12 位随机
    set_account(username, password)
    HINT_FILE.write_text(
        f"用户名: {username}\n密码: {password}\n"
        "（首次登录后请立即在页面右上角修改密码；本文件确认修改后可删除）\n",
        encoding="utf-8",
    )
    return username, password


def password_ok(pw: str) -> bool:
    """改密策略：至少 8 位且同时含字母和数字。"""
    return len(pw) >= 8 and any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw)


# ---------------------------------------------------------------- 会话

def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_sessions() -> dict[str, float]:
    global _sessions
    if not _sessions:
        now = time.time()
        _sessions = {k: v for k, v in _load_json(SESSION_FILE, {}).items() if isinstance(v, (int, float)) and v > now}
    return _sessions


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        ss = _load_sessions()
        now = time.time()
        ss[_token_key(token)] = now + SESSION_TTL
        for k in [k for k, v in ss.items() if v <= now]:
            del ss[k]
        _write_private(SESSION_FILE, ss)
    return token


def session_valid(token: str | None) -> bool:
    if not token:
        return False
    key = _token_key(token)
    with _lock:
        ss = _load_sessions()
        exp = ss.get(key)
        if not exp or exp < time.time():
            return False
        now = time.time()
        if exp - now < RENEW_THRESHOLD:        # 过半才续期，减少写盘
            ss[key] = now + SESSION_TTL
            _write_private(SESSION_FILE, ss)
    return True


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with _lock:
        ss = _load_sessions()
        ss.pop(_token_key(token), None)
        _write_private(SESSION_FILE, ss)


def destroy_other_sessions(keep_token: str | None) -> None:
    """改密后踢掉其他所有会话。"""
    if not keep_token:
        return
    keep = _token_key(keep_token)
    with _lock:
        ss = {k: v for k, v in _load_sessions().items() if k == keep}
        _write_private(SESSION_FILE, ss)


# ---------------------------------------------------------------- 登录限流

def _fail_key(ip: str, username: str) -> str:
    return f"{ip}|{username}"


def locked_seconds(ip: str, username: str) -> int:
    with _lock:
        cnt, until = _fails.get(_fail_key(ip, username), (0, 0.0))
        return max(0, int(until - time.time())) if until > time.time() else 0


def record_fail(ip: str, username: str) -> None:
    with _lock:
        key = _fail_key(ip, username)
        cnt, until = _fails.get(key, (0, 0.0))
        if until and until < time.time():
            cnt = 0
        cnt += 1
        until = time.time() + LOCK_SECONDS if cnt >= MAX_FAILS else 0
        _fails[key] = (cnt, until)
        # 防内存膨胀
        if len(_fails) > 1000:
            _fails.clear()


def record_success(ip: str, username: str) -> None:
    with _lock:
        _fails.pop(_fail_key(ip, username), None)


def login(ip: str, username: str, password: str) -> tuple[bool, str, str]:
    """返回 (成功?, 错误信息, 会话token)。含限流与恒定时间比较。"""
    remain = locked_seconds(ip, username)
    if remain:
        return False, f"失败次数过多，已锁定，请 {remain // 60 + 1} 分钟后再试", ""

    acct = get_account()
    user_ok = acct is not None and hmac.compare_digest(username, acct.get("username", ""))
    pw_ok = verify_password(password, acct or {"salt": "00", "hash": "00"})
    # 小延迟：进一步拉平在线爆破速度
    time.sleep(0.3)

    if not (user_ok and pw_ok):
        record_fail(ip, username)
        left = MAX_FAILS - _fails.get(_fail_key(ip, username), (0, 0))[0]
        msg = "用户名或密码错误"
        if 0 < left <= MAX_FAILS:
            msg += f"（剩余 {left} 次尝试）"
        return False, msg, ""

    record_success(ip, username)
    return True, "", create_session()
