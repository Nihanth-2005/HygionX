"""
HygionX Smart Medical Triage Assistant.
Flask-only: serves HTML from templates/, static files from static/, no Node.js.
Auth via Firebase when FIREBASE_CREDENTIALS_PATH and web config are set in .env.
"""

import json
import os
import requests
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
import re

from dotenv import load_dotenv
from flask import Flask, send_from_directory, request, jsonify, render_template, session, redirect, url_for

from triage_pipeline import run_triage_pipeline, hygionx_triage

load_dotenv()

# Optional: enable MySQL only when DATABASE_URL is set (install flask-sqlalchemy, pymysql)
MODELS_AVAILABLE = False
try:
    from models import (
        db,
        init_app,
        get_database_url,
        User,
        Session,
        Message,
        SymptomsDetected,
        TriageResult,
        SessionSymptom,
    )
    MODELS_AVAILABLE = True
except ImportError:
    get_database_url = lambda: None
    User = Session = Message = SymptomsDetected = TriageResult = SessionSymptom = None

# Optional: Firebase Admin for token verification
FIREBASE_AVAILABLE = False
try:
    import firebase_admin
    from firebase_admin import credentials, auth as firebase_auth
    FIREBASE_AVAILABLE = True
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
# Support both a Datasets/ subfolder and CSVs in the project root
_datasets_subdir = BASE_DIR / "Datasets"
DATASETS_DIR = _datasets_subdir if _datasets_subdir.is_dir() else BASE_DIR

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
    template_folder=str(TEMPLATES_DIR),
)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "hygionx-dev-secret-key")


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_chart_labels(items):
    labels = []
    for item in items:
        parsed = _parse_datetime(item)
        labels.append(parsed.strftime("%b %d") if parsed else str(item))
    return labels


def _admin_credentials_configured():
    return bool(os.environ.get("ADMIN_USERNAME")) and bool(
        os.environ.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD_HASH")
    )


def _is_admin_authenticated():
    return session.get("is_admin") is True


def admin_login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not _is_admin_authenticated():
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Admin authentication required."}), 401
            return redirect(url_for("admin_login_page"))
        return view_func(*args, **kwargs)

    return wrapped_view


def _verify_admin_credentials(username, password):
    expected_username = (os.environ.get("ADMIN_USERNAME") or "").strip()
    expected_password = os.environ.get("ADMIN_PASSWORD")
    expected_password_hash = os.environ.get("ADMIN_PASSWORD_HASH")

    if not expected_username or not (expected_password or expected_password_hash):
        return False, "Admin credentials are not configured in the .env file."

    if username != expected_username:
        return False, "Invalid admin username or password."

    if expected_password_hash:
        try:
            from werkzeug.security import check_password_hash
            password_ok = check_password_hash(expected_password_hash, password)
        except Exception:
            password_ok = False
    else:
        password_ok = password == expected_password

    if not password_ok:
        return False, "Invalid admin username or password."

    return True, None


def _collect_admin_dashboard_data():
    if not MODELS_AVAILABLE:
        return {
            "available": False,
            "message": "Database models are not available. Connect the database to view analytics.",
        }

    try:
        from sqlalchemy import func, desc

        now = datetime.utcnow()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)
        last_14_days = now - timedelta(days=13)

        total_users = User.query.count()
        total_sessions = Session.query.count()
        total_messages = Message.query.count()
        total_triage_results = TriageResult.query.count()

        recent_users = User.query.filter(User.created_at >= last_7_days).count()
        recent_sessions = Session.query.filter(Session.created_at >= last_7_days).count()
        active_users_30d = (
            db.session.query(func.count(func.distinct(Session.user_id)))
            .filter(Session.created_at >= last_30_days)
            .scalar()
            or 0
        )

        avg_messages_per_session = round(total_messages / total_sessions, 2) if total_sessions else 0
        avg_severity = db.session.query(func.avg(TriageResult.severity_score)).scalar() or 0
        avg_confidence = db.session.query(func.avg(TriageResult.confidence)).scalar() or 0

        user_growth_rows = (
            db.session.query(
                func.date(User.created_at).label("day"),
                func.count(User.id).label("count"),
            )
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
            .all()
        )

        risk_distribution_rows = (
            db.session.query(
                TriageResult.risk_level,
                func.count(TriageResult.id).label("count"),
            )
            .group_by(TriageResult.risk_level)
            .all()
        )

        symptom_frequency_rows = (
            db.session.query(
                SessionSymptom.symptom_name,
                func.count(SessionSymptom.id).label("count"),
            )
            .group_by(SessionSymptom.symptom_name)
            .order_by(desc("count"))
            .limit(6)
            .all()
        )

        avg_severity_over_time_rows = (
            db.session.query(
                func.date(TriageResult.created_at).label("day"),
                func.avg(TriageResult.severity_score).label("avg_severity"),
            )
            .filter(TriageResult.created_at >= last_14_days)
            .group_by(func.date(TriageResult.created_at))
            .order_by(func.date(TriageResult.created_at))
            .all()
        )

        emergency_cases_over_time_rows = (
            db.session.query(
                func.date(TriageResult.created_at).label("day"),
                func.count(TriageResult.id).label("count"),
            )
            .filter(TriageResult.created_at >= last_14_days)
            .filter(
                (func.lower(TriageResult.risk_level).like("%high%")) |
                (func.lower(TriageResult.risk_level).like("%emergency%")) |
                (func.lower(TriageResult.recommended_action).like("%emergency%")) |
                (func.lower(TriageResult.recommended_action).like("%immediate%")) |
                (func.lower(TriageResult.recommended_action).like("%call 108%"))
            )
            .group_by(func.date(TriageResult.created_at))
            .order_by(func.date(TriageResult.created_at))
            .all()
        )

        avg_severity_map = {
            _parse_datetime(row.day).date().isoformat(): round(float(row.avg_severity or 0), 2)
            for row in avg_severity_over_time_rows
            if _parse_datetime(row.day)
        }
        emergency_cases_map = {
            _parse_datetime(row.day).date().isoformat(): row.count
            for row in emergency_cases_over_time_rows
            if _parse_datetime(row.day)
        }
        trend_labels = []
        avg_severity_values = []
        emergency_case_values = []
        for offset in range(14):
            day = (last_14_days + timedelta(days=offset)).date()
            trend_labels.append(day.strftime("%b %d"))
            avg_severity_values.append(avg_severity_map.get(day.isoformat(), 0))
            emergency_case_values.append(emergency_cases_map.get(day.isoformat(), 0))

        recent_sessions_rows = (
            db.session.query(
                Session.id,
                Session.title,
                Session.created_at,
                User.name,
                User.email,
            )
            .join(User, User.id == Session.user_id)
            .order_by(Session.created_at.desc())
            .limit(8)
            .all()
        )

        return {
            "available": True,
            "kpis": {
                "total_users": total_users,
                "recent_users": recent_users,
                "total_sessions": total_sessions,
                "recent_sessions": recent_sessions,
                "total_messages": total_messages,
                "active_users_30d": active_users_30d,
                "avg_messages_per_session": avg_messages_per_session,
                "avg_severity": round(avg_severity, 2),
                "avg_confidence": round(avg_confidence * 100, 1),
                "total_triage_results": total_triage_results,
            },
            "charts": {
                "user_growth": {
                    "labels": _format_chart_labels([row.day for row in user_growth_rows]),
                    "values": [row.count for row in user_growth_rows],
                },
                "risk_distribution": {
                    "labels": [row.risk_level or "Unknown" for row in risk_distribution_rows],
                    "values": [row.count for row in risk_distribution_rows],
                },
                "symptom_frequency": {
                    "labels": [row.symptom_name.replace("_", " ").title() for row in symptom_frequency_rows],
                    "values": [row.count for row in symptom_frequency_rows],
                },
                "avg_severity_over_time": {
                    "labels": trend_labels,
                    "values": avg_severity_values,
                },
                "emergency_cases_over_time": {
                    "labels": trend_labels,
                    "values": emergency_case_values,
                },
            },
            "recent_sessions": [
                {
                    "id": row.id,
                    "title": row.title or "Untitled consultation",
                    "created_at": row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else "",
                    "user_name": row.name or "Unknown user",
                    "email": row.email or "No email",
                }
                for row in recent_sessions_rows
            ],
        }
    except Exception as exc:
        return {
            "available": False,
            "message": f"Analytics are temporarily unavailable: {exc}",
        }

# Initialize Firebase Admin if credentials path is set
_firebase_initialized = False
if FIREBASE_AVAILABLE:
    cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH")
    if cred_path and os.path.isfile(cred_path):
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
        _firebase_initialized = True


def _get_firebase_config():
    """Public config for frontend (from .env)."""
    api_key = os.environ.get("FIREBASE_API_KEY")
    if not api_key or api_key == "your-api-key":
        return None
    cfg = {
        "apiKey": api_key,
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId": os.environ.get("FIREBASE_APP_ID", ""),
    }
    if os.environ.get("FIREBASE_MEASUREMENT_ID"):
        cfg["measurementId"] = os.environ.get("FIREBASE_MEASUREMENT_ID")
    return cfg


def _verify_firebase_token(id_token):
    """Verify Firebase ID token; return decoded claims or None."""
    if not FIREBASE_AVAILABLE or not _firebase_initialized:
        return None
    try:
        return firebase_auth.verify_id_token(id_token)
    except Exception:
        return None
    
def verify_recaptcha(token):
    """Verify Google reCAPTCHA token with Google servers."""
    secret = os.environ.get("RECAPTCHA_SECRET_KEY")

    if not secret:
        print("Warning: RECAPTCHA_SECRET_KEY not set in .env")
        return True

    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": secret,
                "response": token
            }
        ).json()

        return response.get("success", False)

    except Exception as e:
        print("reCAPTCHA verification error:", e)
        return False


def _get_or_create_user(firebase_uid: str, email: str = None, name: str = None):
    """Get user by firebase_uid or create. Returns (user, created)."""
    if not MODELS_AVAILABLE or not User:
        return None, False
    user = User.query.filter_by(firebase_uid=firebase_uid).first()
    if user:
        if email is not None:
            user.email = email
        if name is not None and str(name).strip():
            user.name = name
        return user, False
    user = User(firebase_uid=firebase_uid, email=email or "", name=name or "")
    db.session.add(user)
    db.session.flush()
    return user, True


def _get_or_create_session(user_id: int, session_id: int = None):
    """Get session by id if valid and belongs to user, or create new. Returns session."""
    if not MODELS_AVAILABLE or not Session:
        return None
    if session_id:
        session = Session.query.filter_by(id=session_id, user_id=user_id).first()
        if session:
            return session
    session = Session(user_id=user_id)
    db.session.add(session)
    db.session.flush()
    return session

if MODELS_AVAILABLE and get_database_url():
    try:
        init_app(app)
        with app.app_context():
            from sqlalchemy import text
            db.session.execute(text("SELECT 1"))
        print("Database connection OK.")
    except Exception as e:
        MODELS_AVAILABLE = False
        print("Database not available (triage will work without saving sessions):", e)

# Load ML models at startup (once)
print("Starting backend...")
print("Loading AI models at startup...")
try:
    from model_loader import load_models
    _ml_loaded = load_models(str(DATASETS_DIR))
    if _ml_loaded:
        print("AI models loaded successfully")
    else:
        print("Warning: ML models could not be loaded. Server will use rule-based triage fallback.")
except Exception as e:
    print(f"Warning: Failed to load AI models ({e}). Server will use rule-based triage fallback.")

# ----- Health check (includes database status) -----
@app.route("/api/health")
def api_health():
    """Return backend and database status."""
    status = {"status": "ok", "database": "disabled"}
    if MODELS_AVAILABLE and get_database_url():
        try:
            with app.app_context():
                from sqlalchemy import text
                db.session.execute(text("SELECT 1"))
            status["database"] = "connected"
        except Exception as e:
            status["database"] = "error"
            status["database_error"] = str(e)
            status["status"] = "degraded"
    return jsonify(status)


@app.route("/api/routes-status")
def api_routes_status():
    """
    Quick backend self-check for important API routes.
    200 means healthy, while 400/401 can still mean the route is alive but needs input/auth.
    """
    route_checks = [
        {"path": "/api/health", "method": "GET", "label": "Health check"},
        {"path": "/api/chat", "method": "POST", "label": "Main chat API", "json": {}},
        {"path": "/api/login", "method": "POST", "label": "Login API", "json": {}},
        {"path": "/api/register", "method": "POST", "label": "Register API", "json": {}},
        {"path": "/api/user/profile", "method": "GET", "label": "User profile API"},
        {"path": "/api/user/health-context", "method": "GET", "label": "Health context API"},
        {"path": "/api/user/data/export", "method": "GET", "label": "Data export API"},
        {
            "path": "/api/user/data/delete",
            "method": "DELETE",
            "request_method": "options",
            "label": "Data delete API",
        },
        {"path": "/api/disease-info", "method": "POST", "label": "Disease info API", "json": {}},
    ]

    results = []
    with app.test_client() as client:
        for check in route_checks:
            method = check.get("request_method", check["method"]).lower()
            kwargs = {}
            if "json" in check:
                kwargs["json"] = check["json"]

            try:
                response = getattr(client, method)(check["path"], **kwargs)
                code = response.status_code
                if code < 400:
                    state = "working"
                elif code in (400, 401):
                    state = "reachable"
                else:
                    state = "error"

                results.append({
                    "path": check["path"],
                    "method": check["method"],
                    "label": check["label"],
                    "status": state,
                    "status_code": code,
                })
            except Exception as e:
                results.append({
                    "path": check["path"],
                    "method": check["method"],
                    "label": check["label"],
                    "status": "error",
                    "status_code": None,
                    "error": str(e),
                })

    summary = {
        "working": sum(1 for item in results if item["status"] == "working"),
        "reachable": sum(1 for item in results if item["status"] == "reachable"),
        "error": sum(1 for item in results if item["status"] == "error"),
    }

    overall = "ok" if summary["error"] == 0 else "degraded"
    return jsonify({
        "status": overall,
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "summary": summary,
        "routes": results,
    })


# ----- Page routes: all HTML from templates/, no Node.js -----
@app.route("/")
def index():
    return send_from_directory(TEMPLATES_DIR, "landing.html")


@app.route("/chat")
def chat_page():
    return send_from_directory(TEMPLATES_DIR, "chat.html")


@app.route("/login")
def login_page():
    return render_template("login.html", firebase_config=_get_firebase_config())


@app.route("/admin/login")
def admin_login_page():
    return render_template(
        "admin_login.html",
        admin_configured=_admin_credentials_configured(),
        admin_logged_in=_is_admin_authenticated(),
    )


@app.route("/admin/dashboard")
@admin_login_required
def admin_dashboard_page():
    analytics = _collect_admin_dashboard_data()
    return render_template("admin_dashboard.html", analytics=analytics)


@app.route("/register")
def register_page():
    return render_template("register.html", firebase_config=_get_firebase_config())


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


@app.route("/profile")
def profile_page():
    return render_template("profile.html", firebase_config=_get_firebase_config())


@app.route("/medical-encyclopedia")
def medical_encyclopedia_page():
    return send_from_directory(TEMPLATES_DIR, "medical_encyclopedia.html")


@app.route("/about")
def about_page():
    return send_from_directory(TEMPLATES_DIR, "about.html")


@app.route("/help")
def help_page():
    return send_from_directory(TEMPLATES_DIR, "help.html")


@app.route("/settings")
def settings_page():
    return send_from_directory(TEMPLATES_DIR, "settings.html")


@app.route("/timeline")
def health_timeline_page():
    """Render health timeline using triage_results + latest symptoms per session."""
    if not MODELS_AVAILABLE or not TriageResult or not Session:
        return render_template("timeline.html", items=[])
    from sqlalchemy import desc
    rows = (
        TriageResult.query.order_by(desc(TriageResult.created_at))
        .limit(50)
        .all()
    )
    items = []
    session_ids = [r.session_id for r in rows]
    symptoms_map = {}
    if SymptomsDetected and session_ids:
        latest = (
            SymptomsDetected.query.filter(SymptomsDetected.session_id.in_(session_ids))
            .order_by(SymptomsDetected.session_id, desc(SymptomsDetected.created_at))
            .all()
        )
        for sym in latest:
            if sym.session_id not in symptoms_map and sym.symptoms_json:
                try:
                    symptoms_map[sym.session_id] = json.loads(sym.symptoms_json)
                except Exception:
                    symptoms_map[sym.session_id] = []
    for r in rows:
        items.append(
            {
                "session_id": r.session_id,
                "created_at": r.created_at,
                "severity_score": r.severity_score,
                "risk_level": r.risk_level,
                "recommended_action": r.recommended_action,
                "confidence": r.confidence,
                "symptoms": symptoms_map.get(r.session_id, []),
            }
        )
    return render_template("timeline.html", items=items)


# ----- API: Chat (triage) -----
def _severity_to_urgency(score):
    if score is None:
        return "Low Risk"
    if score >= 7:
        return "High Risk"
    if score >= 5:
        return "Moderate Risk"
    return "Low Risk"


def _normalize_possible_conditions(raw_conditions):
    normalized = []
    for item in raw_conditions or []:
        if isinstance(item, dict):
            condition = (item.get("condition") or "").strip()
            probability = item.get("probability", 0)
        else:
            condition = str(item or "").strip()
            probability = 0

        if not condition:
            continue

        try:
            probability = int(round(float(str(probability).replace("%", "").strip())))
        except Exception:
            probability = 0

        normalized.append({
            "condition": condition,
            "probability": max(0, min(100, probability)),
        })

    return normalized


def _build_confidence_explanation(confidence_val, symptoms, followup_count=0):
    symptom_count = len(symptoms or [])
    confidence_pct = max(0, min(100, round((confidence_val or 0) * 100)))
    return (
        f"The confidence score is {confidence_pct}% based on how specific the symptom description was, "
        f"how many symptoms were detected ({symptom_count}), and how much clarification was gathered "
        f"through follow-up questions ({followup_count})."
    )


def _fallback_session_summary(symptoms, urgency, recommended_action, possible_conditions):
    symptom_text = ", ".join(symptoms[:4]) if symptoms else "general symptoms"
    condition_text = ", ".join(
        [c.get("condition", "") for c in possible_conditions[:2] if c.get("condition")]
    )
    first_action = ""
    for line in (recommended_action or "").splitlines():
        cleaned = line.strip().lstrip("-").strip()
        if cleaned:
            first_action = cleaned
            break

    parts = [
        f"- Symptoms discussed: {symptom_text}",
        f"- Current urgency: {urgency}",
    ]

    if condition_text:
        parts.append(f"- Important patterns considered: {condition_text}")

    if first_action:
        parts.append(f"- Next step: {first_action}")

    return "\n".join(parts[:4])


def _generate_session_summary(previous_messages, symptoms, urgency, recommended_action, possible_conditions):
    fallback = _fallback_session_summary(symptoms, urgency, recommended_action, possible_conditions)

    try:
        from llm.llm_client import call_llm
    except Exception:
        return fallback

    recent_lines = []
    for msg in (previous_messages or [])[-6:]:
        role = msg.get("role", "user").capitalize()
        content = (msg.get("content") or "").strip()
        if content:
            recent_lines.append(f"{role}: {content}")

    prompt_context = "\n".join(recent_lines) if recent_lines else "No prior conversation context."
    symptom_text = ", ".join(symptoms[:6]) if symptoms else "general symptoms"
    condition_text = ", ".join(
        [c.get("condition", "") for c in possible_conditions[:3] if c.get("condition")]
    ) or "No clear condition patterns yet"

    system_prompt = (
        "You are generating a concise medical triage session summary for a chat sidebar. "
        "Do not provide a diagnosis. Return exactly 3 or 4 short bullet points. "
        "Each bullet must start with '- '. Mention symptoms discussed, current urgency, "
        "important condition patterns if relevant, and the next action."
    )
    user_prompt = (
        f"Recent conversation:\n{prompt_context}\n\n"
        f"Detected symptoms: {symptom_text}\n"
        f"Urgency: {urgency}\n"
        f"Possible condition patterns: {condition_text}\n"
        f"Recommended action: {recommended_action or 'Continue monitoring'}"
    )

    try:
        summary = call_llm(system_prompt, user_prompt, temperature=0.2, max_tokens=120)
        if summary:
            summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
            if summary:
                lines = []
                for line in summary.splitlines():
                    cleaned = line.strip()
                    if not cleaned:
                        continue
                    if not cleaned.startswith("- "):
                        cleaned = "- " + cleaned.lstrip("-").strip()
                    lines.append(cleaned)
                if lines:
                    return "\n".join(lines[:4])
    except Exception:
        pass

    return fallback


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Accepts { "message": "...", "session_id": optional, "idToken": optional } or Authorization: Bearer <token>.
    Creates/gets user from Firebase UID, gets/creates session, stores messages and symptoms.
    Returns type "triage" | "followup" | "emergency" with session_id.
    """
    data = request.get_json() or {}
    text = (data.get("message") or data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "message or text is required"}), 400

    # Resolve auth: token from body or Authorization header
    id_token = (data.get("idToken") or data.get("id_token") or "").strip()
    if not id_token and request.headers.get("Authorization", "").startswith("Bearer "):
        id_token = request.headers.get("Authorization", "").split(" ", 1)[1].strip()

    user = None
    session = None
    result = None
    known_conditions = ""
    previous_messages_list = []
    
    if MODELS_AVAILABLE:
        try:
            if id_token:
                claims = _verify_firebase_token(id_token)
                if claims:
                    uid = claims.get("uid")
                    email = claims.get("email") or ""
                    user, _ = _get_or_create_user(uid, email=email)
                    if user and getattr(user, "known_conditions", None):
                        known_conditions = user.known_conditions
                    if user:
                        db.session.commit()
                    session = _get_or_create_session(user.id, data.get("session_id")) if user else None
            if session is None:
                # No auth provided - this should not happen in production
                # For now, create a session with the default system user
                print("Warning: Creating session without user authentication - assigning to default user")
                default_user = User.query.filter_by(firebase_uid="default_system_user").first()
                if not default_user:
                    # Create default user if it doesn't exist
                    default_user = User(
                        firebase_uid="default_system_user",
                        email="system@hygionx.com", 
                        name="System User"
                    )
                    db.session.add(default_user)
                    db.session.flush()
                
                session_id_param = data.get("session_id")
                if session_id_param:
                    session = Session.query.filter_by(id=session_id_param, user_id=default_user.id).first()
                if not session:
                    session = Session(user_id=default_user.id)
                    db.session.add(session)
                    db.session.flush()

            # 1. Store user message
            msg_user = Message(session_id=session.id, role="user", content=text)
            db.session.add(msg_user)
            db.session.flush()
            print("Saving message to database (user).")

            # 2. Load context: last N messages and previous symptoms
            previous_messages = (
                Message.query.filter_by(session_id=session.id)
                .order_by(Message.created_at.desc())
                .limit(11)
                .all()
            )
            previous_messages = [m for m in reversed(previous_messages) if m.id != msg_user.id][-10:]
            previous_messages_list = [{"role": m.role, "content": m.content} for m in previous_messages]

            # Fix: merge ALL symptom rows for this session, not just the last one
            all_sym_rows = (
                SymptomsDetected.query.filter_by(session_id=session.id)
                .order_by(SymptomsDetected.created_at.asc())
                .all()
            )
            previous_symptoms = []
            seen_syms = set()
            for row in all_sym_rows:
                if row.symptoms_json:
                    try:
                        for s in json.loads(row.symptoms_json):
                            key = (s or "").strip().lower()
                            if key and key not in seen_syms:
                                previous_symptoms.append(s)
                                seen_syms.add(key)
                    except Exception:
                        pass

            # Also merge any symptoms sent from the client (for no-DB fallback continuity)
            client_syms = data.get("previous_symptoms") or []
            for s in client_syms:
                key = (s or "").strip().lower()
                if key and key not in seen_syms:
                    previous_symptoms.append(s)
                    seen_syms.add(key)

            # 3. Generate response
            followup_count = data.get("followup_count", 0)
            force_triage = data.get("force_triage", False)
            
            result = run_triage_pipeline(
                text,
                session_id=session.id,
                previous_symptoms=previous_symptoms,
                previous_messages=previous_messages_list,
                followup_count=followup_count,
                force_triage=force_triage,
                known_conditions=known_conditions
            )

            # 4. Build assistant content and store assistant message
            if result.get("type") == "emergency":
                assistant_content = result.get("message", "")
            elif result.get("type") == "followup":
                qs = result.get("questions", [])
                assistant_content = qs[0] if qs else "Are there any other symptoms you are experiencing?"
            else:
                assistant_content = result.get("explanation", "")

            msg_assistant = Message(
                session_id=session.id,
                role="assistant",
                content=assistant_content,
            )
            db.session.add(msg_assistant)
            db.session.flush()
            print("Saving message to database (assistant).")

            # 5. Store symptoms_detected for triage, emergency, AND followup (persist partial symptoms)
            symptoms = result.get("symptoms", [])
            severity = result.get("severity") or result.get("severity_score")
            precautions = result.get("precautions", [])
            possible_diseases = result.get("possible_diseases", [])
            # Save whenever we have real symptoms (even during followup turns)
            real_symptoms = [s for s in symptoms if s and s.lower() != "general symptoms (from your description)"]
            
            # Auto-set session title based on detected symptoms or first message
            if not session.title:
                if real_symptoms:
                    # Create meaningful title from primary symptom
                    primary_symptom = real_symptoms[0] if real_symptoms else "General"
                    session.title = f"Consultation - {primary_symptom.title()}"
                else:
                    # Fallback to truncated first message
                    session.title = f"Consultation - {text[:40]}{'...' if len(text) > 40 else ''}"
            
            # Store symptoms and create session_symptoms records
            if real_symptoms:
                sym = SymptomsDetected(
                    session_id=session.id,
                    message_id=msg_assistant.id,
                    symptoms_json=json.dumps(real_symptoms),
                    severity_score=severity if result.get("type") in ("triage", "emergency") else None,
                    precautions_json=json.dumps(precautions) if precautions else None,
                    possible_diseases_json=json.dumps(possible_diseases) if possible_diseases else None,
                    confidence=result.get("confidence"),
                )
                db.session.add(sym)
                
                # Also store in session_symptoms for easy querying
                for symptom in real_symptoms:
                    session_symptom = SessionSymptom(
                        session_id=session.id,
                        symptom_name=symptom,
                        severity_level=severity if result.get("type") in ("triage", "emergency") else None,
                        confidence=result.get("confidence"),
                    )
                    db.session.add(session_symptom)
                
                # Store triage result for final assessments
                if result.get("type") in ("triage", "emergency"):
                    triage_result = TriageResult(
                        session_id=session.id,
                        user_id=session.user_id,
                        severity_score=severity,
                        risk_level=_severity_to_urgency(severity),
                        recommended_action=result.get("recommended_action") or ("; ".join(precautions) if precautions else "Monitor symptoms."),
                        precautions_json=json.dumps(precautions) if precautions else None,
                        possible_diseases_json=json.dumps(possible_diseases) if possible_diseases else None,
                        confidence=result.get("confidence"),
                    )
                    db.session.add(triage_result)
                    
            db.session.commit()
            print("Saving message to database (commit).")
        except Exception as e:
            if db.session:
                db.session.rollback()
            print(f"Database error in api_chat: {e}")
            session = None
            result = run_triage_pipeline(text)

    if not MODELS_AVAILABLE or session is None:
        if result is None:
            result = run_triage_pipeline(text)
        session_id_out = None
    else:
        session_id_out = session.id

    result["session_id"] = session_id_out
    possible_conditions_normalized = _normalize_possible_conditions(
        result.get("possible_conditions_structured") or result.get("possible_conditions") or []
    )
    confidence_val = result.get("confidence", 0.5) or 0.0
    confidence_pct = f"{max(0, min(100, round(confidence_val * 100)))}%"
    confidence_explanation = _build_confidence_explanation(
        confidence_val,
        result.get("symptoms", []),
        result.get("followup_count", 0),
    )

    # ---- Response: emergency ----
    if result.get("type") == "emergency":
        msg = result.get("message", "")
        symptoms = result.get("symptoms", [])
        severity = result.get("severity") or result.get("severity_score", 10)
        model_reasoning = result.get("reasoning", "")
        models_used = [
            "SciSpaCy medical NER",
            "Rule-based triage engine",
            "MiniLM symptom matcher",
            "Symptom embedding index",
        ]
        symptom_text = ", ".join(symptoms[:5]) if symptoms else "serious symptoms"
        emergency_assessment = (
            f"Based on the symptoms detected in this session: {symptom_text}. "
            f"The severity score is {severity}/10, which places this in an emergency range. "
            "This is looking like an emergency situation and needs immediate in-person medical attention. "
            "Please do not wait for symptoms to settle on their own."
        )
        session_summary = _generate_session_summary(
            previous_messages_list,
            symptoms,
            "Emergency",
            msg,
            possible_conditions_normalized,
        )

        payload = {
            "type": "emergency",
            "message": msg,
            "symptoms": symptoms,
            "session_id": session_id_out,
            "safety_message": "This AI provides guidance only and is not a substitute for professional medical diagnosis.",
            "session_summary": session_summary,
            "confidence": confidence_val,
            "severity_score": severity,
        }
        payload["response_type"] = "final"
        payload["assessment"] = emergency_assessment
        payload["response"] = emergency_assessment
        payload["recommended_action"] = msg
        payload["urgency_level"] = "Emergency"
        payload["urgency"] = "emergency"

        # Visible vs hidden explainability for UI
        payload["visible_response"] = {
            "assessment": emergency_assessment,
            "urgency_level": "Emergency",
            "recommended_action": msg,
            "disclaimer": "This AI provides guidance only and is not a substitute for professional medical diagnosis.",
        }
        payload["hidden_metadata"] = {
            "confidence_score": confidence_pct,
            "confidence_explanation": confidence_explanation,
            "model_reasoning": model_reasoning,
            "models_used": models_used,
        }

        return jsonify(payload)

    # ---- Response: followup ----
    if result.get("type") == "followup":
        qs = result.get("questions")

        question_text = "Are there any other symptoms you are experiencing?"
        answer_type = "text"
        options = []

        if isinstance(qs, dict):
            question_text = qs.get("question", question_text)
            answer_type = qs.get("answer_type", "text")
            options = qs.get("options", [])

        elif isinstance(qs, list) and len(qs) > 0:
            question_text = qs[0]
            answer_type = "yes_no"
            options = ["Yes", "No"]

        payload = {
            "type": "followup",
            "response_type": "question",
            "question": question_text,
            "answer_type": answer_type,
            "options": options,
            "session_id": session_id_out,
            "safety_message": "This AI provides guidance only and is not a substitute for professional medical diagnosis."
        }
        # Keep urgency low during follow-up
        payload["urgency"] = "low"
        payload["confidence"] = confidence_val
        payload["session_summary"] = _generate_session_summary(
            previous_messages_list,
            result.get("symptoms", []),
            "Low Risk",
            "Answer the follow-up question so the assessment can be refined.",
            possible_conditions_normalized,
        )

        # Visible vs hidden explainability for UI
        model_reasoning = result.get("reasoning", "")
        models_used = [
            "SciSpaCy medical NER",
            "Rule-based triage engine",
            "MiniLM symptom matcher",
            "Symptom embedding index",
        ]

        payload["visible_response"] = {
            "assessment": "I need a bit more information to understand your symptoms.",
            "urgency_level": "Low Risk",
            "recommended_action": "Please answer the follow-up question shown above.",
            "disclaimer": "This AI provides guidance only and is not a substitute for professional medical diagnosis.",
        }
        payload["hidden_metadata"] = {
            "confidence_score": confidence_pct,
            "confidence_explanation": confidence_explanation,
            "model_reasoning": model_reasoning,
            "models_used": models_used,
        }

        return jsonify(payload)

    # ---- Response: triage ----
    severity = result.get("severity") or result.get("severity_score", 3)
    symptoms = result.get("symptoms", [])
    precautions = result.get("precautions", [])
    possible_diseases = result.get("possible_diseases", [])
    explanation = result.get("explanation", "")
    urgency = result.get("urgency_level") or _severity_to_urgency(severity)
    recommended_action = result.get("recommended_action") or (
        "; ".join(precautions) if precautions else "Monitor your symptoms. Seek care if they worsen."
    )
    model_reasoning = result.get("reasoning", "")
    models_used = [
        "SciSpaCy medical NER",
        "Rule-based triage engine",
        "MiniLM symptom matcher",
        "Symptom embedding index",
    ]

    payload = {
        "type": "triage",
        "symptoms": symptoms,
        "severity": severity,
        "session_id": session_id_out,
        "session_summary": _generate_session_summary(
            previous_messages_list,
            symptoms,
            urgency,
            recommended_action,
            possible_conditions_normalized,
        ),
    }
    payload["response_type"] = "final"
    payload["assessment"] = explanation
    payload["response"] = explanation
    payload["urgency_level"] = urgency
    # For header risk indicator: low|moderate|high|emergency
    if urgency == "Emergency":
        payload["urgency"] = "emergency"
    elif urgency == "High Risk":
        payload["urgency"] = "high"
    elif urgency == "Moderate Risk":
        payload["urgency"] = "moderate"
    elif urgency == "Low Risk":
        payload["urgency"] = "low"
    else:
        payload["urgency"] = "low"
    payload["recommended_action"] = recommended_action
    payload["possible_conditions"] = possible_conditions_normalized or [{"condition": d, "probability": 0} for d in (possible_diseases if isinstance(possible_diseases, list) else [])]
    payload["confidence"] = confidence_val
    payload["model_details"] = {
        "model_reasoning": model_reasoning,
        "models_used": models_used,
        "full_probabilities": possible_conditions_normalized,
    }
    payload["safety_message"] = "This AI provides guidance only and is not a substitute for professional medical diagnosis."
    payload["severity_score"] = severity
    payload["precautions"] = precautions
    payload["possible_diseases"] = possible_diseases
    payload["reasoning"] = model_reasoning
    payload["explanation"] = explanation

    # Visible vs hidden explainability for UI
    payload["visible_response"] = {
        "assessment": explanation,
        "urgency_level": urgency,
        "recommended_action": recommended_action,
        "disclaimer": "This AI provides guidance only and is not a substitute for professional medical diagnosis.",
    }
    payload["hidden_metadata"] = {
        "confidence_score": confidence_pct,
        "confidence_explanation": confidence_explanation,
        "model_reasoning": model_reasoning,
        "models_used": models_used,
    }

    return jsonify(payload)


# ----- API: Auth (Firebase + user creation) -----
@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.get_json() or {}
    id_token = (body.get("idToken") or body.get("id_token") or "").strip()
    if not id_token:
        return jsonify({
            "success": False,
            "message": "Authentication not configured. Add Firebase credentials to .env (see .env.example).",
        })
    claims = _verify_firebase_token(id_token)
    if not claims:
        return jsonify({"success": False, "message": "Invalid or expired sign-in. Try again."}), 401
    uid = claims.get("uid")
    email = claims.get("email") or ""
    user, created = _get_or_create_user(uid, email=email)
    if user and MODELS_AVAILABLE:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return jsonify({
        "success": True,
        "redirect": "/chat",
        "uid": uid,
        "email": email,
        "user_id": user.id if user else None,
    })


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    body = request.get_json() or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return jsonify({"success": False, "message": "Enter both admin username and password."}), 400

    is_valid, error_message = _verify_admin_credentials(username, password)
    if not is_valid:
        return jsonify({"success": False, "message": error_message}), 401

    session["is_admin"] = True
    session["admin_username"] = username
    session.permanent = True

    return jsonify({"success": True, "redirect": "/admin/dashboard"})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    return jsonify({"success": True})


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.pop("is_admin", None)
    session.pop("admin_username", None)
    return jsonify({"success": True, "redirect": "/admin/login"})


@app.route("/api/register", methods=["POST"])
def api_register():
    body = request.get_json() or {}
    # Verify reCAPTCHA
    captcha_token = body.get("captcha")

    if not captcha_token or not verify_recaptcha(captcha_token):
        return jsonify({
            "success": False,
            "message": "Captcha verification failed. Please try again."
        }), 400
    id_token = (body.get("idToken") or body.get("id_token") or "").strip()
    if not id_token:
        return jsonify({
            "success": False,
            "message": "Registration not configured. Add Firebase credentials to .env (see .env.example).",
        })
    claims = _verify_firebase_token(id_token)
    if not claims:
        return jsonify({"success": False, "message": "Invalid or expired sign-up. Try again."}), 401
    uid = claims.get("uid")
    email = claims.get("email") or ""
    name = (body.get("name") or "").strip()
    age_raw = body.get("age")
    user, created = _get_or_create_user(uid, email=email, name=name)
    if user and MODELS_AVAILABLE:
        try:
            if age_raw not in (None, ""):
                try:
                    user.age = int(age_raw)
                except (TypeError, ValueError):
                    pass
            db.session.commit()
        except Exception:
            db.session.rollback()
    return jsonify({
        "success": True,
        "redirect": "/chat",
        "uid": uid,
        "email": email,
        "user_id": user.id if user else None,
    })


@app.route("/api/admin/analytics", methods=["GET"])
@admin_login_required
def api_admin_analytics():
    analytics = _collect_admin_dashboard_data()
    status_code = 200 if analytics.get("available") else 503
    return jsonify(analytics), status_code


# ----- API: User profile & health context (stubs) -----
@app.route("/api/user/profile", methods=["GET", "PUT"])
def api_user_profile():

    if not MODELS_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503

    # Get Firebase token
    id_token = request.headers.get("Authorization", "").replace("Bearer ", "")
    claims = _verify_firebase_token(id_token)

    if not claims:
        return jsonify({"error": "Unauthorized"}), 401

    uid = claims.get("uid")
    user = User.query.filter_by(firebase_uid=uid).first()

    if not user:
        return jsonify({"error": "User not found"}), 404

    # ---- GET PROFILE ----
    if request.method == "GET":
        return jsonify({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "age": user.age,
            "gender": user.gender,
            "known_conditions": user.known_conditions or "",
            "created_at": user.created_at.isoformat() if user.created_at else None
        })

    # ---- UPDATE PROFILE ----
    data = request.get_json() or {}

    # Update allowed fields
    if "name" in data:
        user.name = data["name"]
    if "age" in data:
        user.age = data["age"]
    if "gender" in data:
        user.gender = data["gender"]
    if "known_conditions" in data:
        user.known_conditions = data["known_conditions"]

    try:
        db.session.commit()
        return jsonify({
            "success": True,
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "age": user.age,
            "gender": user.gender,
            "known_conditions": user.known_conditions or "",
            "created_at": user.created_at.isoformat() if user.created_at else None
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update profile: {str(e)}"}), 500


@app.route("/api/user/health-context", methods=["GET", "PUT"])
def api_user_health_context():
    if not MODELS_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503

    id_token = request.headers.get("Authorization", "").replace("Bearer ", "")
    claims = _verify_firebase_token(id_token)

    if not claims:
        return jsonify({"error": "Unauthorized"}), 401

    uid = claims.get("uid")
    user = User.query.filter_by(firebase_uid=uid).first()

    if not user:
        return jsonify({"error": "User not found"}), 404

    if request.method == "GET":
        conditions = [
            item.strip() for item in (user.known_conditions or "").split(",") if item.strip()
        ]
        return jsonify({
            "conditions": conditions,
            "allergies": [],
            "medications": [],
        })

    data = request.get_json() or {}
    conditions = data.get("conditions") or []
    user.known_conditions = ", ".join(
        [item.strip() for item in conditions if isinstance(item, str) and item.strip()]
    )

    try:
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update health context: {str(e)}"}), 500


@app.route("/api/user/data/export")
def api_user_data_export():
    return jsonify({
        "profile": {},
        "health_context": {},
        "exported_at": None,
    })


@app.route("/api/user/data/delete", methods=["DELETE"])
def api_user_data_delete():
    return jsonify({"success": True})


# ----- API: Medical encyclopedia (Wikipedia via wiki_retriever) -----
_wiki_retriever = None


def _get_wiki_retriever():
    global _wiki_retriever
    if _wiki_retriever is None:
        try:
            from wiki_retriever import WikiRetriever
            _wiki_retriever = WikiRetriever()
        except Exception as e:
            print(f"Warning: WikiRetriever not available: {e}")
            return None
    return _wiki_retriever


@app.route("/api/disease-info", methods=["POST"])
def api_disease_info():
    body = request.get_json() or {}
    name = (body.get("disease_name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "disease_name is required"}), 400

    retriever = _get_wiki_retriever()
    if retriever:
        try:
            max_sentences = int(body.get("max_sentences", 5))
            information = retriever.retrieve(name, max_sentences=max_sentences)
            return jsonify({
                "success": True,
                "disease_name": name,
                "information": information,
                "source": "Wikipedia",
            })
        except Exception as e:
            print(f"Wiki retriever error: {e}")
            return jsonify({
                "success": False,
                "error": "Could not fetch disease information.",
                "disease_name": name,
            }), 502

    return jsonify({
        "success": False,
        "error": "Disease lookup is not available.",
        "disease_name": name,
    }), 503


# # ----- API: React frontend (same backend, different path shape) -----
# @app.route("/api/auth/login", methods=["POST"])
# def api_auth_login():
#     body = request.get_json() or {}
#     return jsonify({
#         "token": "stub-token",
#         "user": {"id": "1", "name": body.get("name", ""), "email": body.get("email", "")},
#     })


# @app.route("/api/auth/register", methods=["POST"])
# def api_auth_register():
#     body = request.get_json() or {}
#     return jsonify({
#         "token": "stub-token",
#         "user": {"id": "1", "name": body.get("name", ""), "email": body.get("email", "")},
#     })


# @app.route("/api/auth/me")
# def api_auth_me():
#     return jsonify({"id": "1", "name": "", "email": ""})

@app.route("/api/hygionx/chat", methods=["POST"])
def api_hygionx_chat():
    """
    Enhanced HygionX MediAI Triage endpoint with full feature access.
    Provides the complete HygionX assessment format while maintaining compatibility.
    """
    data = request.get_json() or {}
    text = (data.get("message") or data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "message is required"}), 400

    # Get session context if available
    session_id = data.get("session_id")
    previous_symptoms = data.get("previous_symptoms", [])
    followup_count = data.get("followup_count", 0)
    
    # Reset triage system for new session if needed
    if data.get("reset_session", False):
        hygionx_triage.reset_session()
        followup_count = 0
        previous_symptoms = []
    
    # Initialize with previous symptoms
    if previous_symptoms:
        hygionx_triage.session_symptoms = previous_symptoms.copy()
    hygionx_triage.follow_up_count = followup_count
    
    # Process through HygionX system
    response = hygionx_triage.process_message(text)
    
    # Return the full HygionX response
    return jsonify({
        "session_id": session_id,
        "hygionx_response": response,
        "session_symptoms": hygionx_triage.session_symptoms,
        "follow_up_count": hygionx_triage.follow_up_count
    })

@app.route("/api/triage/chat", methods=["POST"])
def api_triage_chat():
    body = request.get_json() or {}
    text = (body.get("message") or "").strip()
    if not text:
        return jsonify({"error": "message is required"}), 400
    result = run_triage_pipeline(text)
    if result.get("type") == "followup":
        return jsonify({"type": "followup", "questions": result.get("questions", [])})
    sev = result.get("severity") or result.get("severity_score", 0)
    return jsonify({
        "type": "triage",
        "symptoms": result.get("symptoms", []),
        "severity": sev,
        "response": result.get("explanation", ""),
        "urgency": "low" if sev < 5 else "moderate" if sev < 7 else "high",
        "confidence": result.get("confidence", 0.5),
        "redFlag": sev >= 7,
    })


@app.route("/api/profile", methods=["GET", "PATCH"])
def api_profile():
    if request.method == "GET":
        return jsonify({"id": "1", "name": "", "email": "", "age": None, "gender": None, "conditions": []})
    return jsonify({"id": "1", "name": "", "email": ""})


@app.route("/api/profile/clear-history", methods=["POST"])
def api_profile_clear_history():
    return jsonify({"success": True})


@app.route("/api/profile/delete-health-data", methods=["POST"])
def api_profile_delete_health_data():
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
