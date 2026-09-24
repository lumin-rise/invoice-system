"""发票解析系统后端（FastAPI）。

安全模型：
- 所有 /api/* 需要登录会话（除 /api/login、/api/me），Cookie HttpOnly + SameSite=Strict
- 写操作校验 Origin 同源（抗 CSRF）
- 口令 scrypt 哈希存储；登录失败 5 次锁定 15 分钟；/docs 已关闭

启动：在 backend/ 目录执行
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
首次启动自动生成管理员账号，初始密码见 data/初始密码.txt。
"""
from __future__ import annotations

import asyncio
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import cleanup, config, pipeline, security, store
from .exporter import to_xlsx_bytes
from .models import Invoice, InvoicePatch, sorted_invoices


@asynccontextmanager
async def lifespan(app: FastAPI):
    boot = security.ensure_bootstrap()
    if boot:
        print(f"[账号] 已创建管理员：用户名 {boot[0]}，初始密码 {boot[1]}"
              f"（见 {security.HINT_FILE}，登录后请尽快修改）")
    task = asyncio.create_task(cleanup.daily_loop())
    yield
    task.cancel()


app = FastAPI(title="发票解析系统", version="1.1",
              docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

_pool = ThreadPoolExecutor(max_workers=4)

PUBLIC_PATHS = {"/api/login", "/api/me"}
UNSAFE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


@app.middleware("http")
async def security_middleware(request, call_next):
    path = request.url.path
    if path.startswith("/api"):
        # 会话鉴权
        if path not in PUBLIC_PATHS:
            if not security.session_valid(request.cookies.get(security.SESSION_COOKIE)):
                return JSONResponse({"detail": "未登录或会话已过期"}, status_code=401)
        # CSRF：浏览器写请求必带 Origin，必须是同源
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin:
                host = request.headers.get("host", "")
                if urlparse(origin).netloc != host:
                    return JSONResponse({"detail": "跨站请求被拒绝"}, status_code=403)
    return await call_next(request)


# ---------------------------------------------------------------- 认证

from fastapi import Request  # noqa: E402


@app.post("/api/login")
async def do_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "请求体不是 JSON")
    username = str(body.get("username", ""))
    password = str(body.get("password", ""))
    if not username or not password or len(password) > 200 or len(username) > 64:
        raise HTTPException(400, "用户名或密码格式不正确")
    ip = request.client.host if request.client else "unknown"
    ok, msg, token = security.login(ip, username, password)
    if not ok:
        return JSONResponse({"detail": msg}, status_code=401)
    resp = JSONResponse({"ok": True, "username": security.get_account()["username"]})
    resp.set_cookie(
        security.SESSION_COOKIE, token,
        max_age=security.SESSION_TTL, httponly=True, samesite="strict", path="/",
    )
    return resp


@app.get("/api/me")
def me(request: Request):
    token = request.cookies.get(security.SESSION_COOKIE)
    acct = security.get_account()
    if security.session_valid(token) and acct:
        return {"logged_in": True, "username": acct["username"]}
    return {"logged_in": False, "username": None}


@app.post("/api/logout")
def logout(request: Request):
    security.destroy_session(request.cookies.get(security.SESSION_COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(security.SESSION_COOKIE, path="/")
    return resp


@app.post("/api/change-password")
async def change_password(request: Request):
    token = request.cookies.get(security.SESSION_COOKIE)
    if not security.session_valid(token):
        raise HTTPException(401, "未登录")
    body = await request.json()
    old, new = str(body.get("old_password", "")), str(body.get("new_password", ""))
    acct = security.get_account()
    if not acct or not security.verify_password(old, acct):
        return JSONResponse({"detail": "原密码不正确"}, status_code=401)
    if not security.password_ok(new):
        return JSONResponse(
            {"detail": "新密码至少 8 位，且需同时包含字母和数字"}, status_code=400)
    security.set_account(acct["username"], new)
    security.destroy_other_sessions(token)   # 踢掉其他设备
    print(f"[账号] 密码已修改（{datetime.now():%Y-%m-%d %H:%M}）")
    return {"ok": True}


# ---------------------------------------------------------------- 业务 API

@app.post("/api/upload", response_model=list[Invoice])
async def upload(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "没有文件")
    jobs = []
    for f in files:
        content = await f.read()
        jobs.append((f.filename or "未命名", content))
    invoices = list(_pool.map(lambda j: pipeline.process_upload(*j), jobs))
    existing = store.load_invoices()
    existing.extend(invoices)
    store.save_invoices(existing)
    return invoices


@app.get("/api/invoices", response_model=list[Invoice])
def list_invoices():
    return sorted_invoices(store.load_invoices())


@app.patch("/api/invoices/{inv_id}", response_model=Invoice)
def patch_invoice(inv_id: str, patch: InvoicePatch):
    inv = store.get_invoice(inv_id)
    if not inv:
        raise HTTPException(404, "记录不存在")
    data = patch.model_dump(exclude_none=True)
    if "category" in data and data["category"] not in ("travel", "other"):
        raise HTTPException(400, "category 只能是 travel/other")
    for k, v in data.items():
        setattr(inv, k, v)
    store.upsert(inv)
    return inv


@app.post("/api/invoices/manual", response_model=Invoice)
def add_manual(body: dict):
    """新增一行无发票的行程（如“工厂已付”）。"""
    inv = Invoice(
        filename=body.get("item") or "手工行程",
        file_type="manual",
        source="manual",
        category="travel",
        item=body.get("item") or "",
        location=body.get("location") or "",
        amount=body.get("amount"),
        date=body.get("date") or datetime.now().strftime("%Y-%m-%d"),
        time=body.get("time") or "",
        no_bill=bool(body.get("no_bill", True)),
        note=body.get("note") or "（工厂已付）",
    )
    store.upsert(inv)
    return inv


@app.delete("/api/invoices/{inv_id}")
def delete_invoice(inv_id: str):
    if not store.remove(inv_id):
        raise HTTPException(404, "记录不存在")
    return {"ok": True}


@app.post("/api/session/clear")
def clear_session():
    store.clear()
    return {"ok": True}


# ---------------------------------------------------------------- Tracker 基准文件

@app.get("/api/tracker")
def tracker_info():
    if config.TRACKER_FILE.exists():
        from openpyxl import load_workbook
        try:
            wb = load_workbook(str(config.TRACKER_FILE), read_only=True)
        except Exception:
            return {"loaded": False, "filename": None, "sheets": []}
        try:
            return {"loaded": True, "filename": config.TRACKER_FILE.name,
                    "sheets": wb.sheetnames}
        finally:
            wb.close()   # read_only 模式会一直持有文件句柄，必须显式关闭，
                         # 否则 Windows 下文件被锁、移除接口删不掉
    return {"loaded": False, "filename": None, "sheets": []}


@app.post("/api/tracker")
async def upload_tracker(file: UploadFile = File(...)):
    name = file.filename or ""
    if not name.lower().endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 文件")
    content = await file.read()
    tmp = config.TRACKER_FILE.with_suffix(".tmp.xlsx")
    tmp.write_bytes(content)
    try:
        from openpyxl import load_workbook
        wb = load_workbook(str(tmp))
        sheets = wb.sheetnames
        wb.close()
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, f"无法读取该 xlsx: {e}")
    tmp.replace(config.TRACKER_FILE)
    return {"loaded": True, "filename": Path(name).name, "sheets": sheets}


@app.delete("/api/tracker")
def remove_tracker():
    try:
        config.TRACKER_FILE.unlink(missing_ok=True)
    except PermissionError:
        raise HTTPException(500, "文件被占用，请稍后再试或重启服务")
    return {"ok": True}


# ---------------------------------------------------------------- 文件与导出

@app.get("/api/files/uploads/{name}")
def get_upload(name: str):
    path = (config.UPLOAD_DIR / name).resolve()
    if not str(path).startswith(str(config.UPLOAD_DIR.resolve())) or not path.exists():
        raise HTTPException(404)
    media, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media or "application/octet-stream")


@app.get("/api/files/thumbs/{name}")
def get_thumb(name: str):
    path = (config.THUMB_DIR / name).resolve()
    if not str(path).startswith(str(config.THUMB_DIR.resolve())) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/export")
def export_xlsx():
    invoices = store.load_invoices()
    if not invoices:
        raise HTTPException(400, "当前没有可导出的发票")
    tracker = config.TRACKER_FILE if config.TRACKER_FILE.exists() else None
    data = to_xlsx_bytes(invoices, tracker)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Tracker merged {stamp}.xlsx"'},
    )


# ---------------------------------------------------------------- 调试

@app.post("/api/debug/parse")
def debug_parse(body: dict):
    """诊断用：看服务端实际加载的解析器与解析结果。"""
    import app.parsers.fields as f
    text = body.get("text", "")
    return {
        "module_file": f.__file__,
        "has_rail_fallback": hasattr(f, "rail_stations_from_lines"),
        "result": f.parse_fields(text),
    }


# ---------------------------------------------------------------- 前端静态资源

_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
else:
    @app.get("/")
    def dev_hint():
        return {"hint": "前端尚未构建：执行 frontend/build.bat 后重启本服务，或访问 /docs 调试 API"}
