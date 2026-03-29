"""
SQLAlchemy models for HygionX. Uses MySQL-compatible types.
Set DATABASE_URL in environment, e.g.:
  mysql+pymysql://user:password@localhost/hygionx
"""

import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Text, Integer, Float, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

db = SQLAlchemy()


def get_database_url():
    """Return DATABASE_URL only if explicitly set. No default = app runs without MySQL."""
    return os.environ.get("DATABASE_URL")


def init_app(app):
    url = get_database_url()
    if not url:
        return
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _run_migrations()


def _run_migrations():
    """Safely add any missing columns to existing tables without dropping data."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)

        # --- users table ---
        if "users" in insp.get_table_names():
            user_cols = [c["name"] for c in insp.get_columns("users")]
            if "firebase_uid" not in user_cols:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN firebase_uid VARCHAR(128) NULL UNIQUE"
                ))
                print("Migration: added firebase_uid to users.")
            if "age" not in user_cols:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN age INTEGER NULL"
                ))
                print("Migration: added age to users.")
            if "gender" not in user_cols:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN gender VARCHAR(32) NULL"
                ))
                print("Migration: added gender to users.")
            if "known_conditions" not in user_cols:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN known_conditions TEXT NULL"
                ))
                print("Migration: added known_conditions to users.")

        # --- sessions table ---
        if "sessions" in insp.get_table_names():
            session_cols = [c["name"] for c in insp.get_columns("sessions")]
            if "title" not in session_cols:
                db.session.execute(text(
                    "ALTER TABLE sessions ADD COLUMN title VARCHAR(255) NULL"
                ))
                print("Migration: added title to sessions.")
            
            # Handle user_id constraint - we need to be careful with existing NULL values
            if "user_id" in session_cols:
                # Check if there are NULL user_id values
                null_count = db.session.execute(text(
                    "SELECT COUNT(*) FROM sessions WHERE user_id IS NULL"
                )).scalar()
                
                if null_count > 0:
                    print(f"Warning: Found {null_count} sessions with NULL user_id. These will be assigned to a default user.")
                    # Create a default user if it doesn't exist
                    default_user = db.session.execute(text(
                        "SELECT id FROM users WHERE firebase_uid = 'default_system_user' LIMIT 1"
                    )).scalar()
                    
                    if not default_user:
                        db.session.execute(text(
                            "INSERT INTO users (firebase_uid, email, name) VALUES ('default_system_user', 'system@hygionx.com', 'System User')"
                        ))
                        default_user = db.session.execute(text(
                            "SELECT LAST_INSERT_ID()"
                        )).scalar()
                        print(f"Created default system user with ID: {default_user}")
                    
                    # Assign NULL sessions to default user
                    db.session.execute(text(
                        f"UPDATE sessions SET user_id = {default_user} WHERE user_id IS NULL"
                    ))
                    print(f"Updated {null_count} sessions to default user.")
                
                # Now make the column NOT NULL (this might fail on some databases, so we'll handle it gracefully)
                try:
                    # For MySQL/MariaDB
                    db.session.execute(text(
                        "ALTER TABLE sessions MODIFY COLUMN user_id INTEGER NOT NULL"
                    ))
                    print("Migration: made sessions.user_id NOT NULL.")
                except Exception as e:
                    print(f"Could not make user_id NOT NULL (might require manual intervention): {e}")

        # --- symptoms_detected table ---
        if "symptoms_detected" in insp.get_table_names():
            symptoms_detected_cols = [c["name"] for c in insp.get_columns("symptoms_detected")]
            if "symptoms_json" not in symptoms_detected_cols:
                db.session.execute(text(
                    "ALTER TABLE symptoms_detected ADD COLUMN symptoms_json TEXT NULL"
                ))
                print("Migration: added symptoms_json to symptoms_detected.")
            if "severity_score" not in symptoms_detected_cols:
                db.session.execute(text(
                    "ALTER TABLE symptoms_detected ADD COLUMN severity_score INTEGER NULL"
                ))
                print("Migration: added severity_score to symptoms_detected.")
            if "precautions_json" not in symptoms_detected_cols:
                db.session.execute(text(
                    "ALTER TABLE symptoms_detected ADD COLUMN precautions_json TEXT NULL"
                ))
                print("Migration: added precautions_json to symptoms_detected.")
            if "possible_diseases_json" not in symptoms_detected_cols:
                db.session.execute(text(
                    "ALTER TABLE symptoms_detected ADD COLUMN possible_diseases_json TEXT NULL"
                ))
                print("Migration: added possible_diseases_json to symptoms_detected.")
            if "confidence" not in symptoms_detected_cols:
                db.session.execute(text(
                    "ALTER TABLE symptoms_detected ADD COLUMN confidence FLOAT NULL"
                ))
                print("Migration: added confidence to symptoms_detected.")

        # --- triage_results table ---
        if "triage_results" in insp.get_table_names():
            triage_results_cols = [c["name"] for c in insp.get_columns("triage_results")]
            if "precautions_json" not in triage_results_cols:
                db.session.execute(text(
                    "ALTER TABLE triage_results ADD COLUMN precautions_json TEXT NULL"
                ))
                print("Migration: added precautions_json to triage_results.")
            if "possible_diseases_json" not in triage_results_cols:
                db.session.execute(text(
                    "ALTER TABLE triage_results ADD COLUMN possible_diseases_json TEXT NULL"
                ))
                print("Migration: added possible_diseases_json to triage_results.")

        # --- session_symptoms table ---
        if "session_symptoms" not in insp.get_table_names():
            # Create the table if it doesn't exist
            db.session.execute(text("""
                CREATE TABLE session_symptoms (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    session_id INTEGER NOT NULL,
                    symptom_name VARCHAR(100) NOT NULL,
                    severity_level INTEGER NULL,
                    confidence FLOAT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_session_symptoms_session_id (session_id),
                    INDEX idx_session_symptoms_name (symptom_name)
                )
            """))
            print("Migration: created session_symptoms table.")
        else:
            # Add missing columns if any
            session_symptoms_cols = [c["name"] for c in insp.get_columns("session_symptoms")]
            if "confidence" not in session_symptoms_cols:
                db.session.execute(text(
                    "ALTER TABLE session_symptoms ADD COLUMN confidence FLOAT NULL"
                ))
                print("Migration: added confidence to session_symptoms.")
            if "created_at" not in session_symptoms_cols:
                db.session.execute(text(
                    "ALTER TABLE session_symptoms ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ))
                print("Migration: added created_at to session_symptoms.")

        # --- Add foreign key constraints if they don't exist ---
        try:
            # Check if foreign key constraints exist (MySQL specific)
            if "sessions" in insp.get_table_names():
                # Add foreign key for sessions.user_id
                db.session.execute(text("""
                    ALTER TABLE sessions 
                    ADD CONSTRAINT fk_sessions_user_id 
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                """))
                print("Migration: added foreign key constraint for sessions.user_id")
        except Exception as e:
            print(f"Foreign key constraint may already exist or failed: {e}")

        try:
            if "session_symptoms" in insp.get_table_names():
                # Add foreign key for session_symptoms.session_id
                db.session.execute(text("""
                    ALTER TABLE session_symptoms 
                    ADD CONSTRAINT fk_session_symptoms_session_id 
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                """))
                print("Migration: added foreign key constraint for session_symptoms.session_id")
        except Exception as e:
            print(f"Foreign key constraint may already exist or failed: {e}")

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Migration error: {e}")


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    firebase_uid = db.Column(String(128), unique=True, nullable=True, index=True)
    email = db.Column(String(255), nullable=True, index=True)
    name = db.Column(String(255), nullable=True)
    age = db.Column(Integer, nullable=True)
    gender = db.Column(String(32), nullable=True)
    known_conditions = db.Column(Text, nullable=True)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")


class Session(db.Model):
    __tablename__ = "sessions"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(String(255), nullable=True)
    created_at = db.Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    symptoms_detected = relationship("SymptomsDetected", back_populates="session", cascade="all, delete-orphan")
    session_symptoms = relationship("SessionSymptom", back_populates="session", cascade="all, delete-orphan")
    triage_results = relationship("TriageResult", back_populates="session", cascade="all, delete-orphan")


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    role = db.Column(String(32), nullable=False)
    content = db.Column(Text, nullable=False)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="messages")


class SymptomsDetected(db.Model):
    __tablename__ = "symptoms_detected"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    message_id = db.Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    symptoms_json = db.Column(Text, nullable=True)
    severity_score = db.Column(Integer, nullable=True)
    precautions_json = db.Column(Text, nullable=True)
    possible_diseases_json = db.Column(Text, nullable=True)
    confidence = db.Column(Float, nullable=True)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="symptoms_detected")


class TriageResult(db.Model):
    __tablename__ = "triage_results"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    user_id = db.Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    severity_score = db.Column(Integer, nullable=True)
    risk_level = db.Column(String(20), nullable=True)
    recommended_action = db.Column(Text, nullable=True)
    precautions_json = db.Column(Text, nullable=True)
    possible_diseases_json = db.Column(Text, nullable=True)
    confidence = db.Column(Float, nullable=True)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="triage_results")
    user = relationship("User")


class SessionSymptom(db.Model):
    __tablename__ = "session_symptoms"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    symptom_name = db.Column(String(100), nullable=False)
    severity_level = db.Column(Integer, nullable=True)
    confidence = db.Column(Float, nullable=True)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="session_symptoms")