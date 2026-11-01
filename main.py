import os
import uuid
import socket
from typing import Optional, Dict, Any
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
    File,
    WebSocket,
    WebSocketDisconnect
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

# ==============================================================================
# WebSocket Real-Time Waiting Room Hub
# ==============================================================================
class WaitingRoomHub:
    def __init__(self):
        self.students: Dict[str, WebSocket] = {}
        self.admins: set[WebSocket] = set()

    async def connect_student(self, nim: str, ws: WebSocket):
        await ws.accept()
        self.students[nim] = ws

    def disconnect_student(self, nim: str):
        self.students.pop(nim, None)

    async def connect_admin(self, ws: WebSocket):
        await ws.accept()
        self.admins.add(ws)

    def disconnect_admin(self, ws: WebSocket):
        self.admins.discard(ws)

    async def broadcast_to_all(self, payload: dict):
        targets = list(self.students.values()) + list(self.admins)
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                pass

    async def broadcast_message(self, message_dict: dict):
        await self.broadcast_to_all({
            "event": "NEW_MESSAGE",
            "message": message_dict
        })

    async def broadcast_participants(self, participants: list):
        await self.broadcast_to_all({
            "event": "PARTICIPANTS_UPDATE",
            "participants": participants,
            "count": len(participants)
        })

    async def broadcast_exam_start(self):
        await self.broadcast_to_all({
            "event": "EXAM_STARTED"
        })

    async def broadcast_exam_stop(self):
        await self.broadcast_to_all({
            "event": "EXAM_STOPPED"
        })

waiting_hub = WaitingRoomHub()

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
    expected_output_image: Optional[str] = ""

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
    nim: str = Form(...),
    name: str = Form(...)
):
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
    response.set_cookie(key="student_token", value=new_session_token, httponly=True)
    response.set_cookie(key="student_nim", value=nim, httponly=True)
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
    client_ip = get_client_ip(request)
    is_valid, user, reason = database.validate_student_session(req.nim, req.session_token, client_ip)
    if not is_valid or not user:
        return {"success": False, "error": f"Otorisasi Sesi Gagal: {reason}"}

    active_db = (req.active_database or database.DEFAULT_EXAM_DB).strip()

    # Execute inside PostgreSQL sandbox for the designated database and student NIM
    result = database.execute_student_query(req.query, active_db=active_db, nim=req.nim)
    
    # Log query execution
    database.log_exam_event(
        user["id"], 
        "run_query", 
        f"Eksekusi query [{active_db}] ({len(req.query)} karakter) - Status: {'Sukses' if result.get('success') else 'Error'}"
    )
    return result

@app.post("/api/student/submit")
def api_student_submit(req: SubmitAnswerRequest, request: Request):
    client_ip = get_client_ip(request)
    is_valid, user, reason = database.validate_student_session(req.nim, req.session_token, client_ip)
    if not is_valid or not user:
        return {"status": "error", "message": f"Otorisasi Sesi Gagal: {reason}"}

    selected_cat = user.get("selected_category")
    if not selected_cat:
        return {"status": "error", "message": "Anda belum memilih paket soal ujian!"}

    # Guard: verify question exists and belongs to user's locked category
    question = database.get_question_by_id(req.question_id)
    if not question:
        return {"status": "error", "message": "Soal tidak ditemukan."}

    if (question.get("category") or "A").upper() != selected_cat.upper():
        return {"status": "error", "message": "Soal ini tidak sesuai dengan paket soal yang Anda pilih."}

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
    database.save_submission(
        user_id=user["id"],
        question_id=req.question_id,
        submitted_query=req.query,
        is_correct=is_correct_int,
        score=eval_res["score"],
        eval_status=eval_res["eval_status"],
        feedback=eval_res["feedback"]
    )

    student_res = eval_res.get("student_result") or {}
    return {
        "status": "success",
        "is_correct": eval_res["is_correct"],
        "score": eval_res["score"],
        "max_score": score_weight,
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
def admin_handle_login(master_key: str = Form(...)):
    stored_key = database.get_admin_master_key()
    if master_key.strip() == stored_key:
        res = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
        res.set_cookie(key="admin_session", value=CURRENT_ADMIN_SESSION_TOKEN, httponly=True)
        return res

    return RedirectResponse(url="/admin/login?error=Master+Key+salah!", status_code=status.HTTP_302_FOUND)

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if not verify_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)

    host_ip = get_local_host_ip()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"host_ip": host_ip}
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
        return {"success": False, "message": "Password lama tidak sesuai!"}
    
    new_pw = req.new_password.strip()
    if not new_pw or len(new_pw) < 4:
        return {"success": False, "message": "Password baru minimal 4 karakter!"}
    
    database.update_admin_master_key(new_pw)
    return {"success": True, "message": "Password master admin berhasil diperbarui!"}

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
        expected_output_image=req.expected_output_image or ""
    )
    return {
        "status": "success", 
        "id": q_id, 
        "message": f"Soal Paket {req.category} #{req.question_number} berhasil disimpan."
    }

@app.post("/api/admin/questions/upload-image")
async def api_admin_upload_question_image(request: Request, image: UploadFile = File(...)):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    upload_dir = os.path.join(STATIC_DIR, "uploads", "questions")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(image.filename)[1].lower() if image.filename else ".png"
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        raise HTTPException(status_code=400, detail="Format file harus gambar (PNG, JPG, JPEG, WEBP, GIF).")

    file_id = f"output_{uuid.uuid4().hex[:12]}{ext}"
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
async def api_admin_exam_start(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    database.set_exam_state("active")
    database.clear_waiting_room_messages()
    await waiting_hub.broadcast_exam_start()
    return {"status": "success", "message": "Ujian dimulai. Seluruh peserta akan diarahkan ke lembar soal."}

@app.post("/api/admin/exam/stop")
async def api_admin_exam_stop(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    database.set_exam_state("waiting")
    await waiting_hub.broadcast_exam_stop()
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

@app.get("/api/waiting/messages")
def api_waiting_messages(request: Request, since_id: int = 0):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)
    if not token or not nim:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi.")
    is_valid, _, _ = database.validate_student_session(nim, token, client_ip)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Sesi tidak valid.")
    messages = database.get_waiting_room_messages(since_id=since_id)
    return {"messages": messages}

class WaitingMessageRequest(BaseModel):
    message: str

@app.post("/api/waiting/messages")
async def api_post_waiting_message(request: Request, body: WaitingMessageRequest):
    token = request.cookies.get("student_token")
    nim = request.cookies.get("student_nim")
    client_ip = get_client_ip(request)
    if not token or not nim:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi.")
    is_valid, user, _ = database.validate_student_session(nim, token, client_ip)
    if not is_valid or not user:
        raise HTTPException(status_code=401, detail="Sesi tidak valid.")
    msg = database.post_waiting_room_message(nim, user["name"], body.message)
    if not msg:
        raise HTTPException(status_code=400, detail="Pesan kosong atau terlalu panjang.")
    await waiting_hub.broadcast_message(msg)
    return {"status": "ok", "message": msg}

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

@app.get("/api/admin/waiting/messages")
def api_admin_waiting_messages(request: Request, since_id: int = 0):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    messages = database.get_waiting_room_messages(since_id=since_id)
    return {"messages": messages}

@app.post("/api/admin/waiting/messages")
async def api_admin_post_waiting_message(request: Request, body: WaitingMessageRequest):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    msg = database.post_waiting_room_message("ADMIN", "Pengawas", body.message)
    if not msg:
        raise HTTPException(status_code=400, detail="Pesan kosong atau terlalu panjang.")
    await waiting_hub.broadcast_message(msg)
    return {"status": "ok", "message": msg}

@app.post("/api/admin/waiting/clear-messages")
async def api_admin_clear_waiting_messages(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    database.clear_waiting_room_messages()
    await waiting_hub.broadcast_to_all({"event": "CLEAR_MESSAGES"})
    return {"status": "success", "message": "Pesan chat waiting room berhasil dibersihkan."}

@app.websocket("/ws/waiting")
async def ws_waiting_endpoint(websocket: WebSocket):
    token = websocket.cookies.get("student_token")
    nim = websocket.cookies.get("student_nim")
    client_ip = "127.0.0.1"
    if websocket.client and websocket.client.host:
        client_ip = websocket.client.host

    if not token or not nim:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    is_valid, user, _ = database.validate_student_session(nim, token, client_ip)
    if not is_valid or not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await waiting_hub.connect_student(nim, websocket)
    database.mark_student_waiting(nim)

    # Kirim snapshot state awal ke mahasiswa
    try:
        await websocket.send_json({
            "event": "INIT_STATE",
            "exam_state": database.get_exam_state(),
            "participants": database.get_waiting_room_participants(),
            "messages": database.get_waiting_room_messages(since_id=0, limit=50)
        })
    except Exception:
        pass

    # Broadcast update daftar peserta ke semua klien
    try:
        await waiting_hub.broadcast_participants(database.get_waiting_room_participants())
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_json()
            mtype = data.get("type")
            if mtype == "PING":
                database.heartbeat_student_waiting(nim)
                await websocket.send_json({"event": "PONG"})
            elif mtype == "CHAT":
                text = str(data.get("message", "")).strip()
                if text:
                    msg = database.post_waiting_room_message(nim, user["name"], text)
                    if msg:
                        await waiting_hub.broadcast_message(msg)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        waiting_hub.disconnect_student(nim)
        try:
            await waiting_hub.broadcast_participants(database.get_waiting_room_participants())
        except Exception:
            pass

@app.websocket("/ws/admin")
async def ws_admin_endpoint(websocket: WebSocket):
    token = websocket.cookies.get("admin_session")
    if not token or token != CURRENT_ADMIN_SESSION_TOKEN:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await waiting_hub.connect_admin(websocket)

    try:
        await websocket.send_json({
            "event": "INIT_STATE",
            "exam_state": database.get_exam_state(),
            "participants": database.get_waiting_room_participants(),
            "messages": database.get_waiting_room_messages(since_id=0, limit=50)
        })
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_json()
            mtype = data.get("type")
            if mtype == "CHAT":
                text = str(data.get("message", "")).strip()
                if text:
                    msg = database.post_waiting_room_message("ADMIN", "Pengawas", text)
                    if msg:
                        await waiting_hub.broadcast_message(msg)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        waiting_hub.disconnect_admin(websocket)

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

class ResetDatabaseAdminRequest(BaseModel):
    target_db: Optional[str] = "classicmodels"

@app.post("/api/admin/reset-database")
def api_admin_reset_database(request: Request, req: Optional[ResetDatabaseAdminRequest] = None):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    target_db = (req.target_db if req and req.target_db else "classicmodels").strip()
    success, msg = database.reset_target_database(target_db=target_db)
    return {"status": "success" if success else "error", "message": msg}

@app.post("/api/admin/upload-sql")
async def api_admin_upload_sql(
    request: Request, 
    file: UploadFile = File(...), 
    target_db: Optional[str] = Form("classicmodels")
):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    
    content_bytes = await file.read()
    try:
        sql_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        sql_text = content_bytes.decode("latin-1")

    db_choice = (target_db or "classicmodels").strip()
    success, msg = database.reset_target_database(target_db=db_choice, custom_sql_text=sql_text)
    return {"status": "success" if success else "error", "message": msg}

@app.get("/api/admin/logs")
def api_admin_logs(request: Request):
    if not verify_admin_auth(request):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    logs = database.get_recent_exam_logs(limit=50)
    return {"logs": logs}

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
