import os
import uuid
import socket
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Request,
    Response,
    Depends,
    HTTPException,
    status,
    Form,
    UploadFile,
    File
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Initialize SQLite tables on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_system_db()
    pg_ok, pg_msg = database.init_postgres_db()
    health = database.verify_system_health()
    if database.get_admin_master_key() == "admin123":
        print("[PERINGATAN KEAMANAN P0] Master key admin masih menggunakan password bawaan ('admin123').")
        print("  Disarankan mengganti password melalui portal admin (/admin) sebelum pelaksanaan ujian!")
    print("---------------------------------------------------------")
    print("Offline SQL Exam System Server Starting...")
    print(f"System SQLite DB Status      : {'OK' if health['sqlite'] else 'ERROR'}")
    print(f"PostgreSQL Sandbox Status    : {'OK' if pg_ok else 'PERHATIAN'}")
    print(f"Catatan PostgreSQL           : {pg_msg}")
    print(f"PostgreSQL Admin Status      : {'OK' if health['postgres_admin'] else 'ERROR'}")
    print(f"PostgreSQL student_role Status: {'OK' if health['postgres_student'] else 'ERROR'}")
    print(f"Host Local IP Address        : http://{get_local_host_ip()}:8000")
    print("---------------------------------------------------------")
    yield
    # Safely close PostgreSQL connection pools on server shutdown
    database.close_pg_pools()

app = FastAPI(title="Offline SQL Exam System", lifespan=lifespan)

# Mount Static Files and Templates
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    # Mencegah Safari dan browser lain meng-cache file JS/CSS atau halaman dinamis selama sesi ujian
    if request.url.path.startswith("/static/") or request.url.path in ["/", "/exam", "/admin", "/login"]:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Master Key Session Token for Admin / Lecturer (generated dynamically on start)
CURRENT_ADMIN_SESSION_TOKEN = str(uuid.uuid4())



import time
import threading
from collections import defaultdict

# ==============================================================================
# P0 Security Hardening: In-Memory Rate Limiter, CSRF, and Cookie Helpers
# ==============================================================================
class InMemoryRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""
    def __init__(self):
        self._history = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = [t for t in self._history[key] if t > cutoff]
            if len(timestamps) >= max_requests:
                self._history[key] = timestamps
                return False
            timestamps.append(now)
            self._history[key] = timestamps
            return True

rate_limiter = InMemoryRateLimiter()

def verify_csrf_origin(request: Request) -> None:
    """
    Validates Origin and Referer headers against Host on mutating HTTP requests.
    Mitigates Cross-Site Request Forgery (CSRF).
    """
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        host = request.headers.get("host")
        if not host:
            return
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        if origin:
            origin_host = origin.split("://")[-1].rstrip("/")
            if origin_host != host:
                raise HTTPException(status_code=403, detail="Permintaan ditolak: CSRF Origin tidak valid.")
        elif referer:
            try:
                referer_host = referer.split("://")[1].split("/")[0]
                if referer_host != host:
                    raise HTTPException(status_code=403, detail="Permintaan ditolak: CSRF Referer tidak valid.")
            except Exception:
                pass

def set_secure_cookie(
    response: Response,
    key: str,
    value: str,
    request: Request,
    max_age: int = 28800  # 8 hours
) -> None:
    """Sets an audited secure, HttpOnly, SameSite=Lax cookie with explicit expiration."""
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=key,
        value=value,
        httponly=True,
        samesite="lax",
        max_age=max_age,
        secure=is_https
    )

def get_local_host_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

# ==============================================================================
# Health & Readiness Probes (P2)
# ==============================================================================
@app.get("/health")
def health_check():
    """Liveness probe: returns status 200 if FastAPI is accepting HTTP requests."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/ready")
def readiness_check():
    """Readiness probe: validates SQLite, PostgreSQL admin/student connections, and connection pool."""
    health = database.verify_system_health()
    pool_stats = database.get_pool_stats()
    is_ready = bool(health.get("sqlite") and health.get("postgres_admin") and health.get("postgres_student"))
    status_code = 200 if is_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "degraded",
            "timestamp": datetime.now().isoformat(),
            "databases": {
                "sqlite": health.get("sqlite", False),
                "postgres_admin": health.get("postgres_admin", False),
                "postgres_student": health.get("postgres_student", False),
            },
            "pool": pool_stats,
            "details": health.get("details", {})
        }
    )

# ==============================================================================
# Pydantic Request Models
# ==============================================================================
class RunQueryRequest(BaseModel):
    nim: str
    session_token: str
    query: str
    active_database: Optional[str] = None

class SubmitAnswerRequest(BaseModel):
    nim: str
    session_token: str
    question_id: int
    query: str
    active_database: Optional[str] = None

class SelectCategoryRequest(BaseModel):
    nim: str
    session_token: str
    category: str

class HeartbeatRequest(BaseModel):
    nim: str
    session_token: str

class LogEventRequest(BaseModel):
    nim: str
    session_token: str
    action_type: str
    details: Optional[str] = None

class SaveQuestionRequest(BaseModel):
    question_id: Optional[int] = None
    category: str = "A"
    question_number: int
    title: str
    description: str
    score_weight: int = 15
    expected_query: Optional[str] = None
    target_database: Optional[str] = "pagila"
    difficulty_level: Optional[str] = "Medium"
    expected_output_image: Optional[Union[str, List[str]]] = ""
    expected_output_images: Optional[List[str]] = None
    question_images: Optional[Union[str, List[str]]] = None

class KickStudentRequest(BaseModel):
    nim: str

class ClearSessionsRequest(BaseModel):
    clear_logs: bool = False

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class CreatePackageRequest(BaseModel):
    code: str
    name: Optional[str] = ""
    description: Optional[str] = ""
    is_active: Optional[bool] = True

class UpdatePackageRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

# ==============================================================================
# Student Web Navigation Routes
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
def index_route(request: Request):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)

    if token and nim:
        is_valid, user, _ = database.validate_student_session(nim, token, client_ip)
        if is_valid:
            return RedirectResponse(url="/waiting", status_code=status.HTTP_302_FOUND)

    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: Optional[str] = None, message: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": error, "message": message}
    )

@app.post("/login")
def handle_login(
    request: Request,
    nim: str = Form(""),
    name: str = Form("")
):
    verify_csrf_origin(request)
    client_ip = get_client_ip(request)
    if not rate_limiter.check(f"student_login:{client_ip}", max_requests=15, window_seconds=60):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Terlalu banyak percobaan login. Silakan tunggu sejenak.", "nim_value": nim, "name_value": name}
        )
    nim = nim.strip()
    name = name.strip()
    if not nim or not name:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "NIM dan Nama Lengkap wajib diisi!", "nim_value": nim, "name_value": name}
        )

    client_ip = get_client_ip(request)
    new_session_token = str(uuid.uuid4())

    success, user, error_msg = database.login_student(nim, name, client_ip, new_session_token)

    if not success:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": error_msg, "nim_value": nim, "name_value": name}
        )

    response = RedirectResponse(url="/waiting", status_code=status.HTTP_302_FOUND)
    set_secure_cookie(response, "student_token", new_session_token, request)
    set_secure_cookie(response, "student_nim", nim, request)
    return response

@app.get("/waiting", response_class=HTMLResponse)
def waiting_room_page(request: Request):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)

    if not token or not nim:
        return RedirectResponse(url="/login?error=Silakan+login+terlebih+dahulu", status_code=status.HTTP_302_FOUND)

    is_valid, user, reason = database.validate_student_session(nim, token, client_ip)
    if not is_valid:
        resp = RedirectResponse(url=f"/login?error={reason}", status_code=status.HTTP_302_FOUND)
        resp.delete_cookie("student_token")
        resp.delete_cookie("student_nim")
        return resp

    # If exam already active, send straight to exam
    if database.get_exam_state() == "active":
        return RedirectResponse(url="/exam", status_code=status.HTTP_302_FOUND)

    database.mark_student_waiting(nim)
    return templates.TemplateResponse(
        request=request,
        name="waiting_room.html",
        context={"user": user}
    )

@app.get("/exam", response_class=HTMLResponse)
def exam_page(request: Request):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)

    if not token or not nim:
        return RedirectResponse(url="/login?error=Silakan+login+terlebih+dahulu", status_code=status.HTTP_302_FOUND)

    is_valid, user, reason = database.validate_student_session(nim, token, client_ip)
    if not is_valid:
        response = RedirectResponse(url=f"/login?error={reason}", status_code=status.HTTP_302_FOUND)
        response.delete_cookie("student_token")
        response.delete_cookie("student_nim")
        return response

    # Guard: if exam not active, redirect back to waiting room
    if database.get_exam_state() != "active":
        return RedirectResponse(url="/waiting", status_code=status.HTTP_302_FOUND)

    # Mark student as 'online' (in exam) so they leave the waiting room list
    database.mark_student_in_exam(nim)

    return templates.TemplateResponse(
        request=request,
        name="student.html",
        context={"user": user}
    )

@app.get("/logout")
def logout_route(request: Request):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    if token and nim:
        database.logout_student(nim, token)

    response = RedirectResponse(url="/login?message=Anda+telah+berhasil+logout", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("student_token")
    response.delete_cookie("student_nim")
    return response

# ==============================================================================
# Student API Endpoints (Sandboxed)
# ==============================================================================

@app.get("/api/student/questions")
def api_student_questions(request: Request, token: Optional[str] = None):
    token = token or request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)

    if not token or not nim:
        raise HTTPException(status_code=401, detail="Sesi tidak ditemukan.")

    is_valid, user, reason = database.validate_student_session(nim, token, client_ip)
    if not is_valid or not user:
        raise HTTPException(status_code=401, detail=reason)

    selected_cat = user.get("selected_category")
    if not selected_cat:
        available_categories = database.get_available_categories()
        return {
            "status": "needs_selection",
            "needs_category_selection": True,
            "category": None,
            "categories": available_categories,
            "questions": [],
            "submissions": {}
        }

    questions = database.get_questions_by_category(selected_cat)
    submissions = database.get_student_submissions(user["id"])
    return {
        "status": "success",
        "needs_category_selection": False,
        "category": selected_cat,
        "questions": questions,
        "submissions": submissions
    }

@app.post("/api/student/select-category")
def api_student_select_category(req: SelectCategoryRequest, request: Request):
    client_ip = get_client_ip(request)
    is_valid, user, reason = database.validate_student_session(req.nim, req.session_token, client_ip)
    if not is_valid or not user:
        raise HTTPException(status_code=401, detail=f"Otorisasi Sesi Gagal: {reason}")

    ok, msg = database.lock_student_category(req.nim, req.category)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    cat = req.category.strip().upper()
    database.log_exam_event(
        user["id"],
        "select_category",
        f"Mahasiswa mengunci pilihan Paket Soal: {cat}"
    )

    questions = database.get_questions_by_category(cat)
    return {
        "status": "success",
        "message": msg,
        "category": cat,
        "questions": questions
    }

@app.get("/api/student/databases")
def api_student_databases(request: Request, nim: Optional[str] = None):
    """Returns the list of allowed databases for students, including default database and student virtual db if any."""
    student_nim = (nim or request.cookies.get("student_nim") or "").strip()
    virtual_db = database.get_student_virtual_database(student_nim) if student_nim else None

    dbs = []
    for db_item in database.get_allowed_databases():
        d = dict(db_item)
        if d["name"] == "sandbox_pribadi" and virtual_db:
            d["label"] = f"sandbox_pribadi ({virtual_db})"
            d["virtual_db"] = virtual_db
        dbs.append(d)

    return {
        "status": "success",
        "default": database.DEFAULT_EXAM_DB,
        "databases": dbs,
        "virtual_db": virtual_db
    }

@app.post("/api/student/run-query")
def api_student_run_query(req: RunQueryRequest, request: Request):
    verify_csrf_origin(request)
    client_ip = get_client_ip(request)
    is_valid, user, reason = database.validate_student_session(req.nim, req.session_token, client_ip)
    if not is_valid or not user:
        raise HTTPException(status_code=401, detail=f"Otorisasi Sesi Gagal: {reason}")

    if not rate_limiter.check(f"run_query:{req.nim}:{client_ip}", max_requests=40, window_seconds=60):
        raise HTTPException(status_code=429, detail="Terlalu banyak eksekusi query. Silakan tunggu beberapa detik.")

    if len(req.query or "") > database.MAX_STUDENT_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail=f"Panjang query melebihi batas {database.MAX_STUDENT_QUERY_LENGTH} karakter.")

    active_db = (req.active_database or database.DEFAULT_EXAM_DB).strip().lower().split('(')[0].strip()
    if active_db not in database.ALLOWED_STUDENT_DBS:
        raise HTTPException(status_code=400, detail="Database target tidak valid.")

    # Execute inside PostgreSQL sandbox for the designated database and student NIM
    result = database.execute_student_query(req.query, active_db=active_db, nim=req.nim)

    # Routine query logging removed to optimize SQLite performance and prevent log table bloat
    return result

@app.post("/api/student/submit")
def api_student_submit(req: SubmitAnswerRequest, request: Request):
    verify_csrf_origin(request)
    client_ip = get_client_ip(request)
    is_valid, user, reason = database.validate_student_session(req.nim, req.session_token, client_ip)
    if not is_valid or not user:
        raise HTTPException(status_code=401, detail=f"Otorisasi Sesi Gagal: {reason}")

    if not rate_limiter.check(f"submit:{req.nim}:{client_ip}", max_requests=25, window_seconds=60):
        raise HTTPException(status_code=429, detail="Terlalu banyak permintaan submit. Silakan tunggu beberapa detik.")

    if len(req.query or "") > database.MAX_STUDENT_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail=f"Panjang query melebihi batas {database.MAX_STUDENT_QUERY_LENGTH} karakter.")
    if not is_valid or not user:
        raise HTTPException(status_code=401, detail=f"Otorisasi Sesi Gagal: {reason}")

    selected_cat = user.get("selected_category")
    if not selected_cat:
        raise HTTPException(status_code=400, detail="Anda belum memilih paket soal ujian!")

    # Guard: verify question exists and belongs to user's locked category
    question = database.get_question_by_id(req.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Soal tidak ditemukan.")

    if (question.get("category") or "A").upper() != selected_cat.upper():
        raise HTTPException(status_code=400, detail="Soal ini tidak sesuai dengan paket soal yang Anda pilih.")

    expected_query = question.get("expected_query") or ""
    score_weight = int(question.get("score_weight") or 10)
    target_database = question.get("target_database") or database.DEFAULT_EXAM_DB
    active_database = (req.active_database or target_database).strip()

    # Auto-grade submission using table comparison and sandbox engine
    eval_res = database.evaluate_sql_submission(
        submitted_query=req.query,
        expected_query=expected_query,
        score_weight=score_weight,
        target_db=target_database,
        active_db=active_database,
        nim=req.nim
    )

    is_correct_int = 1 if eval_res["is_correct"] else 0
    save_res = database.save_submission(
        user_id=user["id"],
        question_id=req.question_id,
        submitted_query=req.query,
        is_correct=is_correct_int,
        score=eval_res["score"],
        eval_status=eval_res["eval_status"],
        feedback=eval_res["feedback"]
    )

    effective_score = save_res["score"]
    effective_is_correct = save_res["is_correct"]
    score_retained = save_res.get("score_retained", False)

    student_res = eval_res.get("student_result") or {}
    return {
        "status": "success",
        "is_correct": effective_is_correct,
        "score": effective_score,
        "max_score": score_weight,
        "score_retained": score_retained,
        "previous_score": save_res.get("previous_score", 0),
        "new_score": save_res.get("new_score", 0),
        "retained_message": (
            f"Kueri terbaru Anda belum sesuai, namun skor tertinggi Anda sebelumnya (+{effective_score} Poin) tetap aman dipertahankan."
            if score_retained else ""
        ),
        "eval_status": eval_res["eval_status"],
        "feedback": eval_res["feedback"],
        "target_database": target_database,
        "active_database": active_database,
        "columns": student_res.get("columns", []),
        "rows": student_res.get("rows", []),
        "row_count": student_res.get("row_count", 0),
        "execution_time_ms": student_res.get("execution_time_ms", 0),
        "error": student_res.get("error")
    }

@app.post("/api/student/heartbeat")
def api_student_heartbeat(req: HeartbeatRequest, request: Request):
    client_ip = get_client_ip(request)
    is_valid, user, reason = database.validate_student_session(req.nim, req.session_token, client_ip)
    if is_valid and user:
        database.update_student_heartbeat(user["id"])
        return {
            "valid": True,
            "selected_category": user.get("selected_category")
        }
    return {"valid": False, "reason": reason}

@app.post("/api/student/log-event")
def api_student_log_event(req: LogEventRequest, request: Request):
    client_ip = get_client_ip(request)
    is_valid, user, _ = database.validate_student_session(req.nim, req.session_token, client_ip)
    user_id = user["id"] if (is_valid and user) else None

    database.log_exam_event(user_id, req.action_type, req.details or "")
    return {"status": "ok"}

@app.get("/api/student/schema")
def api_student_schema(request: Request, db: Optional[str] = None):
    target_db = (db or database.DEFAULT_EXAM_DB).strip()
    nim = request.cookies.get("student_nim")
    schema = database.get_database_schema(db_name=target_db, nim=nim)
    virtual_db = database.get_student_virtual_database(nim) if target_db == "sandbox_pribadi" else None
    return {"status": "success", "schema": schema, "database": target_db, "virtual_db": virtual_db}

@app.get("/api/student/schema-full")
def api_student_schema_full(request: Request, db: Optional[str] = None):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)
    if not token or not nim:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi.")
    is_valid, _, _ = database.validate_student_session(nim, token, client_ip)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Sesi tidak valid.")

    target_db = (db or database.DEFAULT_EXAM_DB).strip()
    schema = database.get_database_schema(db_name=target_db, nim=nim)
    relations = database.get_database_fk_relations(db_name=target_db, nim=nim)
    virtual_db = database.get_student_virtual_database(nim) if target_db == "sandbox_pribadi" else None
    return {
        "status": "success",
        "database": target_db,
        "virtual_db": virtual_db,
        "schema": schema,
        "relations": relations
    }

# ==============================================================================
# Admin & Lecturer Portal Routes
# ==============================================================================

def verify_admin_auth(request: Request) -> bool:
    token = request.cookies.get("admin_session")
    return bool(token and token == CURRENT_ADMIN_SESSION_TOKEN)

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context={"error": error}
    )

@app.post("/admin/login")
def admin_handle_login(request: Request, master_key: str = Form("")):
    verify_csrf_origin(request)
    client_ip = get_client_ip(request)
    if not rate_limiter.check(f"admin_login:{client_ip}", max_requests=6, window_seconds=30):
        return RedirectResponse(url="/admin/login?error=Terlalu+banyak+percobaan+login.+Silakan+tunggu+30+detik.", status_code=status.HTTP_302_FOUND)

    if not master_key.strip():
        return RedirectResponse(url="/admin/login?error=Master+Key+wajib+diisi!", status_code=status.HTTP_302_FOUND)

    stored_key = database.get_admin_master_key()
    if master_key.strip() == stored_key:
        global CURRENT_ADMIN_SESSION_TOKEN
        CURRENT_ADMIN_SESSION_TOKEN = str(uuid.uuid4())  # Rotate admin session token on login
        res = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
        set_secure_cookie(res, "admin_session", CURRENT_ADMIN_SESSION_TOKEN, request)
        return res

    return RedirectResponse(url="/admin/login?error=Master+Key+salah!", status_code=status.HTTP_302_FOUND)

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if not verify_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)

    host_ip = get_local_host_ip()
    is_default_master_key = (database.get_admin_master_key() == "admin123")
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"host_ip": host_ip, "is_default_master_key": is_default_master_key}
    )

@app.get("/admin/logout")
def admin_logout():
    global CURRENT_ADMIN_SESSION_TOKEN
    CURRENT_ADMIN_SESSION_TOKEN = str(uuid.uuid4())
    res = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    res.delete_cookie("admin_session")
    return res

# ------------------------------------------------------------------------------
# Admin REST APIs
# ------------------------------------------------------------------------------

@app.get("/api/admin/students")
def api_admin_students(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    students = database.get_all_students_progress()
    return {"students": students}

@app.post("/api/admin/kick-student")
def api_admin_kick_student(req: KickStudentRequest, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    conn = database.get_sqlite_conn()
    with conn:
        conn.execute(
            """
            UPDATE users
            SET session_token = 'KICKED_BY_ADMIN', status = 'offline'
            WHERE nim = ?;
            """,
            (req.nim,)
        )
        conn.execute(
            """
            INSERT INTO exam_logs (action_type, details)
            VALUES ('kick', ?);
            """,
            (f"Pengawas me-reset sesi untuk NIM {req.nim}",)
        )
    conn.close()
    return {"status": "success", "message": f"Sesi mahasiswa {req.nim} telah direset."}

@app.post("/api/admin/stop-all-sessions")
def api_admin_stop_all_sessions(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    count = database.stop_all_active_sessions()
    return {"status": "success", "message": f"Semua sesi aktif telah dihentikan ({count} sesi dinonaktifkan)."}

@app.post("/api/admin/clear-logs")
def api_admin_clear_logs(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    count = database.clear_exam_logs()
    return {"status": "success", "message": f"Log aktivitas berhasil dibersihkan ({count} entri dihapus)."}

@app.post("/api/admin/clear-sessions")
def api_admin_clear_sessions(req: ClearSessionsRequest, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    result = database.clear_previous_sessions(clear_logs=req.clear_logs)
    return {
        "status": "success",
        "message": f"Data sesi sebelumnya berhasil dibersihkan. {result['users_cleared']} mahasiswa dan {result['submissions_cleared']} submisi dihapus."
    }

@app.post("/api/admin/change-password")
def api_admin_change_password(req: ChangePasswordRequest, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    current_key = database.get_admin_master_key()
    if req.current_password.strip() != current_key:
        raise HTTPException(status_code=400, detail="Password lama tidak sesuai!")

    new_pw = req.new_password.strip()
    if not new_pw or len(new_pw) < 4:
        raise HTTPException(status_code=400, detail="Password baru minimal 4 karakter!")

    database.update_admin_master_key(new_pw)
    database.log_exam_event(None, "change_password", "Pengawas memperbarui master key admin.")
    global CURRENT_ADMIN_SESSION_TOKEN
    CURRENT_ADMIN_SESSION_TOKEN = str(uuid.uuid4())
    res = JSONResponse(content={"status": "success", "success": True, "message": "Password master admin berhasil diperbarui!"})
    set_secure_cookie(res, "admin_session", CURRENT_ADMIN_SESSION_TOKEN, request)
    return res

@app.get("/api/admin/questions")
def api_admin_questions(request: Request, category: Optional[str] = None):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    questions = database.get_all_questions(include_expected_query=True, category=category)
    categories = database.get_available_categories()
    packages = database.get_all_packages()
    return {"status": "success", "questions": questions, "categories": categories, "packages": packages}

@app.post("/api/admin/questions")
def api_admin_save_question(req: SaveQuestionRequest, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    exp_imgs = req.expected_output_images if req.expected_output_images is not None else req.expected_output_image
    q_imgs = req.question_images if req.question_images is not None else ""

    q_id = database.save_question(
        question_number=req.question_number,
        title=req.title,
        description=req.description,
        score_weight=req.score_weight,
        expected_query=req.expected_query,
        category=req.category,
        question_id=req.question_id,
        target_database=req.target_database or database.DEFAULT_EXAM_DB,
        difficulty_level=req.difficulty_level or "Medium",
        expected_output_image=exp_imgs or "",
        question_images=q_imgs or ""
    )
    return {
        "status": "success",
        "id": q_id,
        "message": f"Soal Paket {req.category} #{req.question_number} berhasil disimpan."
    }

@app.post("/api/admin/questions/upload-images")
async def api_admin_upload_question_images(
    request: Request,
    images: List[UploadFile] = File(...),
    image_type: Optional[str] = Form("question")
):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    upload_dir = os.path.join(STATIC_DIR, "uploads", "questions")
    os.makedirs(upload_dir, exist_ok=True)

    prefix = "qimg" if (image_type or "").lower() == "question" else "output"
    uploaded_urls = []
    allowed_exts = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"]

    for img in images:
        if not img.filename:
            continue
        ext = os.path.splitext(img.filename)[1].lower() if img.filename else ".png"
        if ext not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"File '{img.filename}' bukan gambar yang didukung (PNG, JPG, JPEG, WEBP, GIF, SVG).")

        file_id = f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"
        dest_path = os.path.join(upload_dir, file_id)

        content = await img.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        uploaded_urls.append(f"/static/uploads/questions/{file_id}")

    return {
        "status": "success",
        "image_urls": uploaded_urls,
        "image_url": uploaded_urls[0] if uploaded_urls else "",
        "count": len(uploaded_urls)
    }

@app.post("/api/admin/questions/upload-image")
async def api_admin_upload_question_image(request: Request, image: UploadFile = File(...), image_type: Optional[str] = Form("output")):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    upload_dir = os.path.join(STATIC_DIR, "uploads", "questions")
    os.makedirs(upload_dir, exist_ok=True)

    prefix = "qimg" if (image_type or "").lower() == "question" else "output"
    ext = os.path.splitext(image.filename)[1].lower() if image.filename else ".png"
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"]:
        raise HTTPException(status_code=400, detail="Format file harus gambar (PNG, JPG, JPEG, WEBP, GIF, SVG).")

    file_id = f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"
    dest_path = os.path.join(upload_dir, file_id)

    content = await image.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    return {
        "status": "success",
        "image_url": f"/static/uploads/questions/{file_id}",
        "filename": image.filename
    }

@app.post("/api/admin/student/{nim}/reset-category")
def api_admin_reset_student_category(nim: str, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    ok, msg = database.reset_student_category(nim)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}

@app.delete("/api/admin/questions/{question_id}")
def api_admin_delete_question(question_id: int, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    database.delete_question(question_id)
    return {"status": "success", "message": "Soal ujian berhasil dihapus."}

@app.delete("/api/admin/questions")
def api_admin_delete_all_questions(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    database.delete_all_questions()
    return {"status": "success", "message": "Seluruh soal ujian berhasil dihapus."}

# ------------------------------------------------------------------------------
# Exam Package Management APIs
# ------------------------------------------------------------------------------

@app.get("/api/admin/packages")
def api_admin_packages(request: Request, include_inactive: bool = True):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    packages = database.get_all_packages(include_inactive=include_inactive)
    return {"status": "success", "packages": packages}

@app.post("/api/admin/packages")
def api_admin_create_package(req: CreatePackageRequest, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    code = req.code.strip().upper()
    name = (req.name or f"Paket {code}").strip()
    desc = (req.description or "").strip()
    is_act = 1 if req.is_active else 0

    ok, msg, new_id = database.create_package(
        code=code,
        name=name,
        description=desc,
        is_active=is_act
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    database.log_exam_event(
        None,
        "create_package",
        f"Pengawas membuat paket soal baru: {code} ({name})"
    )
    return {
        "status": "success",
        "message": msg,
        "id": new_id,
        "package": database.get_package_by_code(code)
    }

@app.put("/api/admin/packages/{code}")
def api_admin_update_package(code: str, req: UpdatePackageRequest, request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    is_act = (1 if req.is_active else 0) if req.is_active is not None else None
    ok, msg = database.update_package(
        code=code,
        name=req.name,
        description=req.description,
        is_active=is_act
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    database.log_exam_event(
        None,
        "update_package",
        f"Pengawas memperbarui paket soal {code.strip().upper()}"
    )
    return {
        "status": "success",
        "message": msg,
        "package": database.get_package_by_code(code)
    }

@app.delete("/api/admin/packages/{code}")
def api_admin_delete_package(code: str, request: Request, delete_questions: bool = False):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    ok, msg = database.delete_package(code, delete_questions=delete_questions)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    database.log_exam_event(
        None,
        "delete_package",
        f"Pengawas menghapus paket soal {code.strip().upper()} (delete_questions={delete_questions})"
    )
    return {"status": "success", "message": msg}

# ==============================================================================
# Exam State & Waiting Room API
# ==============================================================================

@app.get("/api/exam/state")
def api_exam_state(request: Request):
    """Public endpoint: any authenticated student can poll this."""
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)
    if not token or not nim:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi.")
    is_valid, _, _ = database.validate_student_session(nim, token, client_ip)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Sesi tidak valid.")
    return {"state": database.get_exam_state()}

@app.post("/api/admin/exam/start")
def api_admin_exam_start(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    database.set_exam_state("active")
    return {"status": "success", "message": "Ujian dimulai. Seluruh peserta akan diarahkan ke lembar soal."}

@app.post("/api/admin/exam/stop")
def api_admin_exam_stop(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    database.set_exam_state("waiting")
    return {"status": "success", "message": "Ujian dihentikan. Peserta tidak dapat mengakses soal."}

@app.get("/api/waiting/participants")
def api_waiting_participants(request: Request):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)
    if not token or not nim:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi.")
    is_valid, _, _ = database.validate_student_session(nim, token, client_ip)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Sesi tidak valid.")
    participants = database.get_waiting_room_participants()
    return {"participants": participants, "count": len(participants)}



@app.post("/api/waiting/heartbeat")
def api_waiting_heartbeat(request: Request):
    """Called by the browser every 10s while on the waiting room page."""
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)
    if not token or not nim:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi.")
    is_valid, _, _ = database.validate_student_session(nim, token, client_ip)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Sesi tidak valid.")
    database.heartbeat_student_waiting(nim)
    return {"ok": True}

@app.get("/api/admin/waiting/participants")
def api_admin_waiting_participants(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    participants = database.get_waiting_room_participants()
    exam_state = database.get_exam_state()
    return {"participants": participants, "count": len(participants), "exam_state": exam_state}



@app.get("/api/admin/schema")
def api_admin_schema(request: Request, db: Optional[str] = "pagila"):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    target_db = (db or "pagila").strip().lower()
    schema = database.get_database_schema(db_name=target_db)
    relations = database.get_database_fk_relations(db_name=target_db)
    return {
        "status": "success",
        "database": target_db,
        "schema": schema,
        "relations": relations,
        "available_databases": database.get_allowed_databases()
    }

@app.get("/api/admin/table-data")
def api_admin_table_data(request: Request, db: Optional[str] = "pagila", table: str = "", limit: int = 50, offset: int = 0):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    target_db = (db or "pagila").strip().lower()
    if target_db not in database.ALLOWED_MASTER_DBS:
        raise HTTPException(status_code=400, detail="Target database tidak valid.")
    if not table:
        raise HTTPException(status_code=400, detail="Parameter table diperlukan.")
    try:
        data = database.get_table_data(db_name=target_db, table_name=table, limit=limit, offset=offset)
        return {"status": "success", **data}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memuat data tabel: {e}")

class ResetDatabaseAdminRequest(BaseModel):
    target_db: Optional[str] = "classicmodels"

@app.post("/api/admin/reset-database")
def api_admin_reset_database(request: Request, req: Optional[ResetDatabaseAdminRequest] = None):
    verify_csrf_origin(request)
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    client_ip = get_client_ip(request)
    if not rate_limiter.check(f"reset_db:{client_ip}", max_requests=6, window_seconds=60):
        raise HTTPException(status_code=429, detail="Terlalu banyak permintaan reset database. Silakan tunggu.")

    target_db = (req.target_db if req and req.target_db else "classicmodels").strip().lower()
    if target_db not in database.ALLOWED_MASTER_DBS:
        raise HTTPException(status_code=400, detail="Target database tidak valid.")
    success, msg = database.reset_target_database(target_db=target_db)
    if not success:
        raise HTTPException(status_code=500, detail=msg)
    database.log_exam_event(None, "reset_database", f"Pengawas me-reset database '{target_db}' ke kondisi awal.")
    return {"status": "success", "message": msg}

@app.post("/api/admin/upload-sql")
async def api_admin_upload_sql(
    request: Request,
    file: UploadFile = File(...),
    target_db: Optional[str] = Form("classicmodels")
):
    verify_csrf_origin(request)
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    client_ip = get_client_ip(request)
    if not rate_limiter.check(f"upload_sql:{client_ip}", max_requests=6, window_seconds=60):
        raise HTTPException(status_code=429, detail="Terlalu banyak permintaan unggah SQL. Silakan tunggu.")

    MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB limit
    content_bytes = await file.read(MAX_UPLOAD_SIZE + 1024)
    if len(content_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Ukuran file SQL melebihi batas maksimal (25 MB).")

    try:
        sql_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        sql_text = content_bytes.decode("latin-1")

    db_choice = (target_db or "classicmodels").strip().lower()
    if db_choice not in database.ALLOWED_MASTER_DBS:
        raise HTTPException(status_code=400, detail="Target database tidak valid.")
    success, msg = database.reset_target_database(target_db=db_choice, custom_sql_text=sql_text)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    database.log_exam_event(None, "upload_sql", f"Pengawas mengunggah custom dump SQL ke database '{db_choice}' ({len(sql_text)} karakter).")
    return {"status": "success", "message": msg}

@app.get("/api/admin/logs")
def api_admin_logs(request: Request, limit: int = 50, offset: int = 0):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    logs, total = database.get_recent_exam_logs(limit=limit, offset=offset)
    return {"logs": logs, "total": total, "limit": limit, "offset": offset}

@app.get("/api/admin/export/csv")
def api_admin_export_csv(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    csv_data = database.export_all_submissions_csv()
    csv_bytes = csv_data.encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="hasil_ujian_praktikum.csv"',
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Length": str(len(csv_bytes)),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/api/admin/export/zip")
def api_admin_export_zip(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    zip_bytes = database.export_submissions_zip_bytes()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="jawaban_sql_mahasiswa.zip"',
            "Content-Type": "application/zip",
            "Content-Length": str(len(zip_bytes)),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/api/admin/export/logs-csv")
def api_admin_export_logs_csv(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    csv_data = database.export_all_logs_csv()
    csv_bytes = csv_data.encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="rekap_log_aktivitas.csv"',
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Length": str(len(csv_bytes)),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/api/admin/export/tab-switches-csv")
def api_admin_export_tab_switches_csv(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    csv_data = database.export_tab_switches_csv()
    csv_bytes = csv_data.encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="rekap_perpindahan_tab.csv"',
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Length": str(len(csv_bytes)),
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


# ==============================================================================
# Main Runner Entry Point
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    # Bind to 0.0.0.0 so clients on local router Wi-Fi can connect
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
