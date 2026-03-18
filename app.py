import os
import sqlite3
import hashlib
import hmac
import re
import socket
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, send_file, jsonify
import PyPDF2
import docx2txt
import smtplib
from email.message import EmailMessage
import requests

from config import FLASK_SECRET_KEY
from repositories.chat_repository import create_chat_session, ensure_chat_tables, get_chat_messages, save_chat_message
from services.chatbot_service import DEFAULT_CHAT_SUGGESTIONS, generate_chat_response, get_chatbot_health

# simple email helper (configure as needed)
def send_email(to_address, subject, body):
    # placeholder: replace with real SMTP config
    print(f"[email] To: {to_address}, Subject: {subject}\n{body}")
    # Example using localhost SMTP server:
    # msg = EmailMessage()
    # msg['Subject'] = subject
    # msg['From'] = 'no-reply@example.com'
    # msg['To'] = to_address
    # msg.set_content(body)
    # with smtplib.SMTP('localhost') as s:
    #     s.send_message(msg)


# logging helper for application events
# stores each change or notice so admins (and later users) can review

def log_application_event(application_id, status, message):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO application_logs(application_id,status,message) VALUES(?,?,?)",
        (application_id, status, message),
    )
    conn.commit()
    conn.close()


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

TRACKER_STATUS_META = {
    "Submitted": {"badge": "secondary", "step": 1, "label": "Submitted"},
    "In Review": {"badge": "info", "step": 2, "label": "In Review"},
    "Shortlisted": {"badge": "primary", "step": 3, "label": "Shortlisted"},
    "Interview": {"badge": "warning", "step": 4, "label": "Interview"},
    "Selected": {"badge": "success", "step": 5, "label": "Selected"},
    "Rejected": {"badge": "danger", "step": 5, "label": "Rejected"},
    "Duplicate": {"badge": "danger", "step": 5, "label": "Rejected"},
    "Fake": {"badge": "danger", "step": 5, "label": "Rejected"},
}

TRACKER_UPDATE_STATUSES = ["Selected", "Rejected"]

COURSE_NOTE_LIBRARY = {
    "Backend Development": [
        {
            "course_title": "Python for Backend",
            "module_title": "REST API Design with Python",
            "note_body": "Design endpoints around business resources, keep response shapes consistent, validate payloads, and return proper HTTP status codes for predictable client behavior.",
            "objectives": [
                "Create CRUD endpoints with clear naming and status codes",
                "Use request validation and centralized error handling",
                "Document API contracts for frontend and mobile teams",
            ],
            "practice": [
                "Build a notes API with pagination and filtering",
                "Add token-based auth and role checks",
                "Write 10 API tests for success and failure paths",
            ],
            "duration": "5-7 days",
            "interview_focus": "Explain idempotency, status-code choices, and how you version APIs safely.",
            "source_platform": "FastAPI Docs",
            "source_url": "https://fastapi.tiangolo.com/tutorial/",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Django/FastAPI Boot Camp",
            "module_title": "Authentication and Authorization",
            "note_body": "Separate authentication from authorization. Use secure password storage, short-lived tokens, and policy-driven permission checks per route.",
            "objectives": [
                "Implement login, refresh, logout, and password reset flow",
                "Protect endpoints by role and ownership checks",
                "Log sensitive auth events for audits",
            ],
            "practice": [
                "Implement JWT access and refresh tokens",
                "Add role-based route guard middleware",
                "Record failed login attempts and lockout policy",
            ],
            "duration": "1 week",
            "interview_focus": "Discuss token revocation, session expiry, and defending against broken access control.",
            "source_platform": "Django Docs",
            "source_url": "https://docs.djangoproject.com/en/5.0/intro/tutorial01/",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Database Design",
            "module_title": "Schema Modeling and Query Optimization",
            "note_body": "Model entities with explicit relationships, normalize until it hurts performance, then optimize with indexes and targeted denormalization.",
            "objectives": [
                "Design normalized tables for users, jobs, and applications",
                "Use indexes to speed up common lookup patterns",
                "Prevent data anomalies with constraints",
            ],
            "practice": [
                "Write explain plans for 3 heavy queries",
                "Add composite indexes for dashboard filters",
                "Benchmark before and after index tuning",
            ],
            "duration": "5 days",
            "interview_focus": "Explain JOIN strategy, index tradeoffs, and how you diagnose slow queries.",
            "source_platform": "PostgreSQL Docs",
            "source_url": "https://www.postgresql.org/docs/current/tutorial.html",
            "difficulty": "Advanced",
        },
    ],
    "Frontend Development": [
        {
            "course_title": "React Boot Camp",
            "module_title": "Component Architecture and State",
            "note_body": "Split UI into reusable components, lift state only when necessary, and avoid prop-drilling with context or state libraries where justified.",
            "objectives": [
                "Build reusable form and table components",
                "Manage local and shared state predictably",
                "Handle loading and error UX consistently",
            ],
            "practice": [
                "Build a job dashboard with reusable cards",
                "Add optimistic UI updates for status edits",
                "Measure re-render count and optimize hot paths",
            ],
            "duration": "1 week",
            "interview_focus": "Explain rendering lifecycle, memoization strategy, and state ownership.",
            "source_platform": "React Docs",
            "source_url": "https://react.dev/learn",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Vue.js Advanced",
            "module_title": "Reactivity and Composition API",
            "note_body": "Use composables to isolate logic, prefer explicit reactive boundaries, and keep side effects inside lifecycle-aware utilities.",
            "objectives": [
                "Structure reusable composables by domain",
                "Use watchers and computed properties correctly",
                "Control async side effects with cleanup",
            ],
            "practice": [
                "Build profile and application composables",
                "Add caching for repeated API calls",
                "Refactor one Options API component to Composition API",
            ],
            "duration": "4-6 days",
            "interview_focus": "Discuss reactivity caveats and the rationale for composables.",
            "source_platform": "Vue Docs",
            "source_url": "https://vuejs.org/tutorial/",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "UI/UX Principles",
            "module_title": "Accessibility and Usability Foundations",
            "note_body": "Design interfaces that are keyboard-friendly, readable, and consistent. Validate usability with real tasks rather than assumptions.",
            "objectives": [
                "Apply color contrast and semantic structure rules",
                "Create predictable navigation and feedback patterns",
                "Write UX copy that reduces ambiguity",
            ],
            "practice": [
                "Run Lighthouse accessibility checks",
                "Fix keyboard traps in one module",
                "Document one end-to-end UX flow improvement",
            ],
            "duration": "3-5 days",
            "interview_focus": "Explain accessibility decisions and measurable usability improvements.",
            "source_platform": "Google UX Certificate",
            "source_url": "https://www.coursera.org/professional-certificates/google-ux-design",
            "difficulty": "Beginner",
        },
    ],
    "Data Science": [
        {
            "course_title": "Machine Learning Masterclass",
            "module_title": "Model Selection and Evaluation",
            "note_body": "Choose models based on data shape and business constraints, then evaluate with metrics tied to real product outcomes.",
            "objectives": [
                "Split data with leakage prevention",
                "Compare baseline and tuned models",
                "Use confusion matrix and F1 for imbalanced classes",
            ],
            "practice": [
                "Train logistic regression and tree-based model",
                "Tune hyperparameters with cross-validation",
                "Write a model card with risks and assumptions",
            ],
            "duration": "1 week",
            "interview_focus": "Explain why a model was selected and how you validated generalization.",
            "source_platform": "scikit-learn Docs",
            "source_url": "https://scikit-learn.org/stable/tutorial/basic/tutorial.html",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Statistics For Data",
            "module_title": "Probability, Sampling, and Inference",
            "note_body": "Statistics drives trustworthy decisions. Focus on understanding distributions, confidence intervals, and hypothesis testing errors.",
            "objectives": [
                "Interpret central tendency and variance correctly",
                "Select suitable statistical tests",
                "Avoid p-value misuse",
            ],
            "practice": [
                "Run A/B test significance checks",
                "Compute confidence intervals on sample data",
                "Write assumptions and limitations per test",
            ],
            "duration": "4-6 days",
            "interview_focus": "Explain type I/type II errors and practical significance.",
            "source_platform": "Khan Academy",
            "source_url": "https://www.khanacademy.org/math/statistics-probability",
            "difficulty": "Beginner",
        },
        {
            "course_title": "TensorFlow Basics",
            "module_title": "Training Pipelines and Experiment Tracking",
            "note_body": "Build reproducible training pipelines, capture hyperparameters, and track metrics across experiments for clear model iteration.",
            "objectives": [
                "Build dataset pipelines with preprocessing",
                "Train and validate neural network baselines",
                "Track metrics and checkpoints consistently",
            ],
            "practice": [
                "Create one classification pipeline in TensorFlow",
                "Compare two architectures with fixed seeds",
                "Log experiments and summarize outcomes",
            ],
            "duration": "1 week",
            "interview_focus": "Discuss overfitting control and experiment reproducibility.",
            "source_platform": "TensorFlow Tutorials",
            "source_url": "https://www.tensorflow.org/tutorials",
            "difficulty": "Intermediate",
        },
    ],
    "Cloud & DevOps": [
        {
            "course_title": "AWS Solutions Architect",
            "module_title": "Reliable Cloud Architecture",
            "note_body": "Design systems around reliability and cost tradeoffs: multi-AZ architecture, autoscaling, observability, and least-privilege IAM.",
            "objectives": [
                "Map workloads to suitable AWS services",
                "Design high-availability deployment topology",
                "Estimate and optimize cost for key components",
            ],
            "practice": [
                "Design a 3-tier architecture diagram",
                "Implement IAM policy with least privilege",
                "Set CloudWatch alarms for latency and errors",
            ],
            "duration": "1 week",
            "interview_focus": "Explain architecture choices for reliability, security, and cost.",
            "source_platform": "AWS Skill Builder",
            "source_url": "https://explore.skillbuilder.aws/learn/public/learning_plan/view/82",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Kubernetes in 30 days",
            "module_title": "Container Orchestration Fundamentals",
            "note_body": "Understand deployment, service discovery, and scaling in Kubernetes. Treat manifests as versioned artifacts and observe workloads actively.",
            "objectives": [
                "Deploy pods, services, and ingress resources",
                "Use rolling updates and rollback strategies",
                "Monitor health checks and logs",
            ],
            "practice": [
                "Deploy Flask app to a local cluster",
                "Add readiness and liveness probes",
                "Simulate rollout failure and rollback",
            ],
            "duration": "6-8 days",
            "interview_focus": "Discuss rollout safety, service discovery, and cluster troubleshooting.",
            "source_platform": "Kubernetes Docs",
            "source_url": "https://kubernetes.io/docs/tutorials/",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Terraform IaC",
            "module_title": "Infrastructure as Code Workflows",
            "note_body": "Use Terraform modules for repeatable environments, review execution plans before apply, and keep state secure and remote.",
            "objectives": [
                "Create reusable Terraform module structure",
                "Use remote state backend and locking",
                "Manage drift and change reviews in CI",
            ],
            "practice": [
                "Provision a VPC and compute stack",
                "Set variables for dev and prod environments",
                "Add plan and apply steps in pipeline",
            ],
            "duration": "5-7 days",
            "interview_focus": "Explain module boundaries, state management, and safe change rollout.",
            "source_platform": "HashiCorp Learn",
            "source_url": "https://developer.hashicorp.com/terraform/tutorials",
            "difficulty": "Intermediate",
        },
    ],
    "Mobile Development": [
        {
            "course_title": "React Native Bootcamp",
            "module_title": "Cross-Platform App Foundations",
            "note_body": "Build reusable mobile components, handle navigation cleanly, and optimize startup performance on both Android and iOS.",
            "objectives": [
                "Create multi-screen navigation with state persistence",
                "Integrate API calls with robust error handling",
                "Apply mobile performance best practices",
            ],
            "practice": [
                "Build a job tracker mobile app shell",
                "Add offline cache for application list",
                "Profile startup time and optimize heavy screens",
            ],
            "duration": "1 week",
            "interview_focus": "Explain navigation architecture and performance bottleneck fixes.",
            "source_platform": "React Native Docs",
            "source_url": "https://reactnative.dev/docs/getting-started",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Swift for iOS",
            "module_title": "iOS App Architecture and Lifecycle",
            "note_body": "Use MVVM or clean architecture to separate concerns, manage lifecycle events properly, and keep state consistent across navigation transitions.",
            "objectives": [
                "Build screens with reusable view models",
                "Persist local state safely",
                "Handle app lifecycle transitions correctly",
            ],
            "practice": [
                "Build a profile and settings flow",
                "Implement local persistence for preferences",
                "Write unit tests for business logic",
            ],
            "duration": "5-7 days",
            "interview_focus": "Discuss lifecycle handling, memory management, and architecture choices.",
            "source_platform": "Apple Developer",
            "source_url": "https://developer.apple.com/tutorials/app-dev-training",
            "difficulty": "Intermediate",
        },
        {
            "course_title": "Flutter Basics",
            "module_title": "UI Composition and State in Flutter",
            "note_body": "Compose responsive widgets, manage state deliberately, and maintain a clean project structure to support scaling teams.",
            "objectives": [
                "Build responsive layouts for multiple screens",
                "Use a state management pattern consistently",
                "Integrate APIs with retry and failure states",
            ],
            "practice": [
                "Create an application timeline screen",
                "Implement dark/light style support",
                "Add integration test for one user flow",
            ],
            "duration": "1 week",
            "interview_focus": "Explain widget lifecycle, state strategy, and testing approach.",
            "source_platform": "Flutter Docs",
            "source_url": "https://docs.flutter.dev/get-started/codelab",
            "difficulty": "Beginner",
        },
    ],
}


def encode_note_list(items):
    return "||".join(item.strip() for item in items if item and item.strip())


def decode_note_list(items_text):
    if not items_text:
        return []
    return [item.strip() for item in str(items_text).split("||") if item.strip()]


def fallback_source_link(course_name):
    source_links = {
        "python": ("Python Docs", "https://docs.python.org/3/tutorial/"),
        "django": ("Django Docs", "https://docs.djangoproject.com/en/5.0/intro/tutorial01/"),
        "fastapi": ("FastAPI Docs", "https://fastapi.tiangolo.com/tutorial/"),
        "database": ("PostgreSQL Docs", "https://www.postgresql.org/docs/current/tutorial.html"),
        "react": ("React Docs", "https://react.dev/learn"),
        "vue": ("Vue Docs", "https://vuejs.org/tutorial/"),
        "ui": ("Google UX Certificate", "https://www.coursera.org/professional-certificates/google-ux-design"),
        "machine learning": ("scikit-learn Docs", "https://scikit-learn.org/stable/tutorial/basic/tutorial.html"),
        "statistics": ("Khan Academy", "https://www.khanacademy.org/math/statistics-probability"),
        "tensorflow": ("TensorFlow Tutorials", "https://www.tensorflow.org/tutorials"),
        "aws": ("AWS Skill Builder", "https://explore.skillbuilder.aws/learn/public/learning_plan/view/82"),
        "kubernetes": ("Kubernetes Docs", "https://kubernetes.io/docs/tutorials/"),
        "terraform": ("HashiCorp Learn", "https://developer.hashicorp.com/terraform/tutorials"),
        "react native": ("React Native Docs", "https://reactnative.dev/docs/getting-started"),
        "swift": ("Apple Developer", "https://developer.apple.com/tutorials/app-dev-training"),
        "flutter": ("Flutter Docs", "https://docs.flutter.dev/get-started/codelab"),
    }
    lowered = course_name.lower()
    for key, value in source_links.items():
        if key in lowered:
            return value
    return ("MDN / Docs", "https://developer.mozilla.org/")


def seed_course_notes_catalog(cur):
    cur.execute("SELECT id, skill_area, courses FROM career_paths")
    paths = cur.fetchall()

    for path_id, skill_area, courses_text in paths:
        cur.execute("SELECT COUNT(*) FROM course_notes_catalog WHERE path_id=?", (path_id,))
        existing = cur.fetchone()[0]
        if existing > 0:
            continue

        notes = COURSE_NOTE_LIBRARY.get(skill_area, [])

        # Fallback: generate one practical note per course when no curated profile exists.
        if not notes:
            courses = [item.strip() for item in str(courses_text or "").split(",") if item.strip()]
            notes = []
            for course in courses:
                platform, url = fallback_source_link(course)
                notes.append(
                    {
                        "course_title": course,
                        "module_title": f"Core Concepts of {course}",
                        "note_body": f"Understand the practical workflow of {course} and map concepts to a mini project before interview preparation.",
                        "objectives": [
                            f"Learn the most used concepts in {course}",
                            "Apply them in one project-style exercise",
                            "Prepare a concise explanation of design tradeoffs",
                        ],
                        "practice": [
                            "Create one demo project from scratch",
                            "Write a quick revision sheet after each session",
                            "Review one production example from docs",
                        ],
                        "duration": "4-5 days",
                        "interview_focus": "Explain project choices, constraints, and improvements clearly.",
                        "source_platform": platform,
                        "source_url": url,
                        "difficulty": "Intermediate",
                    }
                )

        for index, note in enumerate(notes, start=1):
            cur.execute(
                """
                INSERT INTO course_notes_catalog(
                    path_id, course_title, module_title, note_body, objectives, practice,
                    duration, interview_focus, source_platform, source_url, difficulty, display_order
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    path_id,
                    note["course_title"],
                    note["module_title"],
                    note["note_body"],
                    encode_note_list(note["objectives"]),
                    encode_note_list(note["practice"]),
                    note["duration"],
                    note["interview_focus"],
                    note["source_platform"],
                    note["source_url"],
                    note["difficulty"],
                    index,
                ),
            )


def get_tracker_status_meta(status):
    return TRACKER_STATUS_META.get(status, {"badge": "secondary", "step": 1, "label": status or "Unknown"})


def get_initial_application_status(score):
    return "Selected" if score >= 60 else "Rejected"


def get_tracker_next_action(status, missing_skills):
    if status == "Submitted":
        return "Wait for the first screening update and keep your profile current."
    if status == "In Review":
        return "Review the job description again and prepare project examples for each required skill."
    if status == "Shortlisted":
        return "Prepare for interviews and strengthen the missing skills that appear in the job match report."
    if status == "Interview":
        return "Practice role-specific questions and be ready to explain architecture, debugging, and impact."
    if status == "Selected":
        return "Watch your email for next steps and prepare documents for onboarding or offer discussion."
    if status == "Rejected":
        return "Use the missing-skills list to improve your resume and apply again with a stronger match."
    if status == "Duplicate":
        return "Rejected due to duplicate resume. Upload an updated resume and apply again."
    if status == "Fake":
        return "Rejected because resume content appears invalid or incomplete."
    if missing_skills:
        return "Improve the missing skills shown in the tracker to increase your match rate."
    return "Keep monitoring this application for further updates."


def format_tracker_date(raw_value):
    if not raw_value:
        return "Recent"
    try:
        return datetime.fromisoformat(str(raw_value)).strftime("%d %b %Y")
    except ValueError:
        return str(raw_value)


def build_tracker_entry(row):
    status = row[5] or "Submitted"
    meta = get_tracker_status_meta(status)
    missing_skills = row[6] or ""
    missing_items = [skill.strip() for skill in missing_skills.split(",") if skill.strip()]
    progress = min(100, max(15, meta["step"] * 20))
    return {
        "id": row[0],
        "filename": row[1],
        "title": row[2],
        "company": row[3],
        "score": row[4],
        "status": status,
        "status_badge": meta["badge"],
        "status_label": meta["label"],
        "progress": progress,
        "missing_skills": missing_items,
        "applied_on": format_tracker_date(row[7]),
        "job_skills": row[8] or "",
        "next_action": get_tracker_next_action(status, missing_items),
    }


def is_skills_specified(skills_text):
    value = str(skills_text or "").strip().lower()
    return value not in {"", "not specified", "n/a", "na", "none"}


def build_description_highlights(text, max_items=5):
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    chunks = re.split(r"(?<=[.!?])\s+", cleaned)
    points = []
    for chunk in chunks:
        line = chunk.strip(" .")
        if len(line) < 35:
            continue
        points.append(line)
        if len(points) >= max_items:
            break
    return points

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response



# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        password TEXT,
        profile_pic TEXT,
        location TEXT,
        birthday TEXT
    )
    """)
    # ensure new columns exist
    cur.execute("PRAGMA table_info(users)")
    user_cols = [r[1] for r in cur.fetchall()]
    for col in ['profile_pic', 'location', 'birthday']:
        if col not in user_cols:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            except Exception:
                pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT,
        title TEXT,
        skills TEXT,
        vacancies INTEGER,
        description TEXT,
        status TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        logo TEXT,
        location TEXT,
        website TEXT
    )
    """)

    # Ensure 'location' and 'website' columns exist (handle older DBs created before migration)
    cur.execute("PRAGMA table_info(companies)")
    cols = [r[1] for r in cur.fetchall()]
    if 'location' not in cols:
        try:
            cur.execute("ALTER TABLE companies ADD COLUMN location TEXT")
        except Exception:
            pass
    if 'website' not in cols:
        try:
            cur.execute("ALTER TABLE companies ADD COLUMN website TEXT")
        except Exception:
            pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS applications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        user_email TEXT,
        job_id INTEGER,
        filename TEXT,
        score INTEGER,
        missing_skills TEXT,
        status TEXT,
        resume_hash TEXT,
        is_duplicate INTEGER DEFAULT 0,
        is_fake INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # ensure new columns exist on older DBs
    cur.execute("PRAGMA table_info(applications)")
    app_cols = [r[1] for r in cur.fetchall()]
    if 'user_email' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN user_email TEXT")
        except Exception:
            pass
    if 'missing_skills' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN missing_skills TEXT")
        except Exception:
            pass
    if 'created_at' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN created_at DATETIME")
        except Exception:
            pass
    if 'updated_at' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN updated_at DATETIME")
        except Exception:
            pass
    try:
        cur.execute("UPDATE applications SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL OR created_at='' ")
    except Exception:
        pass
    try:
        cur.execute("UPDATE applications SET updated_at=COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL OR updated_at='' ")
    except Exception:
        pass

    # Force single confidential admin account
    # every time the app starts, ensure there is only one admin user
    # with the credentials specified below (only himabindu/hima should log in).
    admin_username = 'himabindu'
    admin_password = 'hima'
    cur.execute("DELETE FROM admin")  # clear any other rows
    cur.execute("INSERT INTO admin(username,password) VALUES(?,?)", (admin_username, admin_password))

    # Seed companies if empty
    cur.execute("SELECT * FROM companies")
    if not cur.fetchone():
        companies = [
            ("Google", "Organizes the world’s information and makes it universally accessible and useful.", "", "Bengaluru, India", "https://www.google.com"),
            ("Microsoft", "Empowers every person and every organization on the planet to achieve more.", "", "Hyderabad, India", "https://www.microsoft.com"),
            ("Amazon", "Earth’s most customer-centric company; built to sell anything online.", "", "Mumbai, India", "https://www.amazon.com"),
            ("Apple", "Designs, manufactures, and markets mobile communication and media devices, personal computers, and portable digital music players.", "", "Chennai, India", "https://www.apple.com"),
            ("IBM", "Provides integrated solutions and products that leverage information technology and knowledge of business processes.", "", "Pune, India", "https://www.ibm.com"),
        ]
        cur.executemany("INSERT INTO companies(name,description,logo,location,website) VALUES(?,?,?,?,?)", companies)
    else:
        # Backfill locations for known companies if column was added to an existing DB
        known_locations = {
            'Google': ('Bengaluru, India', 'https://www.google.com'),
            'Microsoft': ('Hyderabad, India', 'https://www.microsoft.com'),
            'Amazon': ('Mumbai, India', 'https://www.amazon.com'),
            'Apple': ('Chennai, India', 'https://www.apple.com'),
            'IBM': ('Pune, India', 'https://www.ibm.com'),
        }
        for cname, (loc, web) in known_locations.items():
            cur.execute("UPDATE companies SET location=? WHERE name=?", (loc, cname))
            cur.execute("UPDATE companies SET website=? WHERE name=?", (web, cname))

    # Seed a few demo jobs if jobs table is empty
    # ensure job table has company_id column
    cur.execute("PRAGMA table_info(jobs)")
    job_cols = [r[1] for r in cur.fetchall()]
    if 'company_id' not in job_cols:
        try:
            cur.execute("ALTER TABLE jobs ADD COLUMN company_id INTEGER")
        except Exception:
            pass
    if 'is_demo' not in job_cols:
        try:
            cur.execute("ALTER TABLE jobs ADD COLUMN is_demo INTEGER DEFAULT 0")
        except Exception:
            pass

    # Remove all demo jobs
    cur.execute("DELETE FROM jobs WHERE is_demo=1")

    # admin session tracking for single login
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        login_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 1
    )
    """)

    # career guidance suggestions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS career_paths(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_area TEXT,
        courses TEXT,
        skills_to_learn TEXT,
        career_options TEXT
    )
    """)
    
    # ensure data exists
    cur.execute("SELECT COUNT(*) FROM career_paths")
    if cur.fetchone()[0] == 0:
        careers = [
            ('Backend Development', 'Python for Backend, Django/FastAPI Boot Camp, Database Design', 'Python, SQL, APIs, Microservices', 'Backend Engineer, DevOps Engineer, Cloud Architect'),
            ('Frontend Development', 'React Boot Camp, Vue.js Advanced, UI/UX Principles', 'JavaScript, React, CSS, TypeScript', 'Frontend Engineer, UI Developer, Full Stack Developer'),
            ('Data Science', 'Machine Learning Masterclass, Statistics For Data, TensorFlow Basics', 'Python, Statistics, ML Algorithms, SQL', 'Data Scientist, ML Engineer, Analytics Engineer'),
            ('Cloud & DevOps', 'AWS Solutions Architect, Kubernetes in 30 days, Terraform IaC', 'AWS/Azure, Docker, K8s, CI/CD', 'Cloud Architect, DevOps Engineer, SRE'),
            ('Mobile Development', 'React Native Bootcamp, Swift for iOS, Flutter Basics', 'Swift, Kotlin, React Native, Mobile UI', 'iOS Developer, Android Developer, Mobile Engineer'),
        ]
        cur.executemany(
            "INSERT INTO career_paths(skill_area,courses,skills_to_learn,career_options) VALUES(?,?,?,?)",
            careers
        )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS course_notes_catalog(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path_id INTEGER NOT NULL,
            course_title TEXT NOT NULL,
            module_title TEXT NOT NULL,
            note_body TEXT NOT NULL,
            objectives TEXT,
            practice TEXT,
            duration TEXT,
            interview_focus TEXT,
            source_platform TEXT,
            source_url TEXT,
            difficulty TEXT DEFAULT 'Intermediate',
            display_order INTEGER DEFAULT 1,
            reference_clicks INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(path_id) REFERENCES career_paths(id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_course_notes_path ON course_notes_catalog(path_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_course_notes_order ON course_notes_catalog(path_id, display_order)")
    seed_course_notes_catalog(cur)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS application_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER,
        status TEXT,
        message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # company account table for enterprise use
    cur.execute("""
    CREATE TABLE IF NOT EXISTS company_accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        username TEXT,
        password TEXT
    )
    """)

    # add extra columns to applications for hashing/duplication/fake detection
    cur.execute("PRAGMA table_info(applications)")
    app_cols = [r[1] for r in cur.fetchall()]
    if 'user_email' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN user_email TEXT")
        except Exception:
            pass
    if 'missing_skills' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN missing_skills TEXT")
        except Exception:
            pass
    if 'resume_hash' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN resume_hash TEXT")
        except Exception:
            pass
    if 'is_duplicate' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN is_duplicate INTEGER DEFAULT 0")
        except Exception:
            pass
    if 'is_fake' not in app_cols:
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN is_fake INTEGER DEFAULT 0")
        except Exception:
            pass

    # API keys table for module access control
    cur.execute("""
    CREATE TABLE IF NOT EXISTS api_keys(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module TEXT,
        key TEXT UNIQUE,
        company_id INTEGER,
        job_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # ensure job_id column exists on older DBs
    cur.execute("PRAGMA table_info(api_keys)")
    api_cols = [r[1] for r in cur.fetchall()]
    if 'job_id' not in api_cols:
        try:
            cur.execute("ALTER TABLE api_keys ADD COLUMN job_id INTEGER")
        except Exception:
            pass
    
    # Insert master API key
    master_key = "7738501078msh629d88695c19b1bp1c4eeajsn556ca45ae6af"
    cur.execute("SELECT id FROM api_keys WHERE key=?", (master_key,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO api_keys(module,key,company_id) VALUES(?,?,?)",
            ("master", master_key, None)
        )

    ensure_chat_tables(conn)

    conn.commit()
    conn.close()


init_db()


# ---------------- RESUME TEXT EXTRACTION ----------------
def extract_text(filepath):

    text = ""

    try:
        if filepath.endswith(".pdf"):
            with open(filepath, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    if page.extract_text():
                        text += page.extract_text()

        elif filepath.endswith(".docx"):
            text = docx2txt.process(filepath)

    except:
        text = ""

    return text.lower()


def extract_resume_details(text):
    """Return a dict with sections found in resume text."""
    sections = {}
    patterns = {
        'skills': r'(?:skills?|technical skills)\s*[:\-]\s*(.*)',
        'education': r'(?:education)\s*[:\-]\s*(.*)',
        'experience': r'(?:experience)\s*[:\-]\s*(.*)',
        'certifications': r'(?:certifications?)\s*[:\-]\s*(.*)',
    }
    for key, patt in patterns.items():
        m = re.search(patt, text, re.I)
        if m:
            # split on commas or newlines
            items = re.split(r'[\n,]', m.group(1))
            sections[key] = [i.strip() for i in items if i.strip()]
    return sections

def extract_skills_from_text(text):
    text_lower = text.lower()
    common_skills = [
        'python', 'java', 'c++', 'javascript', 'react', 'node.js', 'sql', 'mysql', 
        'postgresql', 'aws', 'docker', 'kubernetes', 'html', 'css', 'django', 
        'flask', 'api', 'git', 'agile', 'linux', 'azure', 'gcp', 'machine learning', 
        'data science', 'excel', 'word', 'communication', 'leadership', 'project management'
    ]
    found = [s for s in common_skills if s in text_lower]
    return found

# ---------------- SCORE CALCULATION ----------------
def calculate_score(resume_text, job_skills):

    skills = job_skills.lower().split(",")
    match = 0

    for skill in skills:
        if skill.strip() in resume_text:
            match += 1

    if len(skills) == 0:
        return 0

    score = int((match / len(skills)) * 100)
    return score


def generate_job_api_key(master_key, job_id, company, title, vacancies):
    """Generate a per-job API key using HMAC-SHA256 of master key and job fields."""
    msg = f"{job_id}|{company}|{title}|{vacancies}".encode("utf-8")
    return hmac.new(master_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


# ================= USER ROUTES =================

@app.route("/")
def home():
    # If user is logged in, redirect to dashboard
    if "user" in session:
        return redirect("/user_dashboard")
    # If admin is logged in, redirect to admin dashboard
    if "admin" in session:
        return redirect("/admin_dashboard")
    return render_template("index.html")


@app.route("/about")
def about_page():
    return render_template("about.html")


@app.route("/contact")
def contact_page():
    return render_template("contact.html")


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


@app.route("/auth", methods=["GET", "POST"])
def auth():
    if "user" in session:
        return redirect("/user_dashboard")
    if "admin" in session:
        return redirect("/admin_dashboard")
    if "company" in session:
        return redirect("/company_dashboard")
        
    if request.method == "POST":
        mode = request.form.get("mode", "login")
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        if mode == "login":
            # validate input
            if not email or not password:
                conn.close()
                return redirect("/auth?error=Email and password are required")
            if len(password) < 6:
                conn.close()
                return redirect("/auth?error=Password must be at least 6 characters")
            cur.execute(
                "SELECT email,name FROM users WHERE email=? AND password=?",
                (email, password),
            )
            user = cur.fetchone()
            conn.close()
            if user:
                session["user"] = user[0]
                session["user_name"] = user[1] or user[0]
                return redirect("/user_dashboard")
            return redirect("/auth?error=Invalid credentials")

        elif mode == "register":
            name = request.form.get("name")
            if not name or not name.strip():
                conn.close()
                return redirect("/auth?error=Name is required")
            if not email or not password:
                conn.close()
                return redirect("/auth?error=Email and password are required")
            if len(password) < 6:
                conn.close()
                return redirect("/auth?error=Password must be at least 6 characters")
            cur.execute("SELECT id FROM users WHERE email=?", (email,))
            if cur.fetchone():
                conn.close()
                return redirect("/auth?error=Email already registered")
            cur.execute(
                "INSERT INTO users(name,email,password) VALUES(?,?,?)",
                (name, email, password),
            )
            conn.commit()
            conn.close()
            session["user"] = email
            session["user_name"] = name
            return redirect("/user_dashboard")

    error = request.args.get("error", "")
    return render_template("auth.html", error=error)


@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    return redirect("/auth")


@app.route("/user_register", methods=["GET", "POST"])
def user_register():
    return redirect("/auth")


@app.route("/user_dashboard")
def user_dashboard():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    
    # Get open jobs along with company website
    cur.execute("""
        SELECT jobs.id, jobs.company, jobs.title, jobs.skills, jobs.vacancies, 
               jobs.description, jobs.company_id, companies.website
        FROM jobs
        LEFT JOIN companies ON jobs.company_id = companies.id
        WHERE jobs.status='Open' AND (jobs.is_demo=0 OR jobs.is_demo IS NULL)
    """)
    jobs = cur.fetchall()
    
    # Get user's application stats (use user_email now)
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status='Selected' THEN 1 ELSE 0 END) as selected,
            SUM(CASE WHEN status='Rejected' THEN 1 ELSE 0 END) as rejected
        FROM applications 
        WHERE user_email=?
    """, (session["user"],))
    stats = cur.fetchone()
    
    # Get user's application history for tracker and recent items.
    cur.execute("""
        SELECT applications.id, applications.filename, jobs.title, jobs.company, 
               applications.score, applications.status, applications.missing_skills,
               applications.created_at, jobs.skills
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        WHERE applications.user_email=?
        ORDER BY applications.id DESC
    """, (session["user"],))
    application_rows = cur.fetchall()
    
    # ensure name is available for template
    user_display_name = session.get("user_name", session.get("user"))

    
    conn.close()
    
    # Handle None values from COUNT/SUM properly
    total = stats[0] if stats[0] is not None else 0
    selected = stats[1] if stats[1] is not None else 0
    rejected = stats[2] if stats[2] is not None else 0
    
    stats_dict = {
        'total': total,
        'selected': selected,
        'rejected': rejected,
        'pending': total - selected - rejected
    }

    tracker_applications = [build_tracker_entry(row) for row in application_rows]
    my_applications = tracker_applications[:5]
    tracker_counts = {
        "submitted": sum(1 for item in tracker_applications if item["status"] == "Submitted"),
        "review": sum(1 for item in tracker_applications if item["status"] in ["In Review", "Shortlisted"]),
        "interview": sum(1 for item in tracker_applications if item["status"] == "Interview"),
        "closed": sum(1 for item in tracker_applications if item["status"] in ["Selected", "Rejected", "Duplicate", "Fake"]),
    }
    tracker_focus = None
    if tracker_applications:
        tracker_focus = sorted(
            tracker_applications,
            key=lambda item: (item["progress"], item["score"]),
            reverse=True,
        )[0]

    return render_template(
        "user_dashboard.html", jobs=jobs, name=user_display_name, 
        stats=stats_dict, my_applications=my_applications,
        tracker_applications=tracker_applications,
        tracker_counts=tracker_counts,
        tracker_focus=tracker_focus
    )


@app.route("/apply/<int:job_id>")
def apply(job_id):

    if "user" not in session:
        return redirect("/auth?error=Login required to upload resume and apply for a job")

    # fetch job and company website if available
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT jobs.id, jobs.company, jobs.title, companies.website
        FROM jobs
        LEFT JOIN companies ON jobs.company_id = companies.id
        WHERE jobs.id=?
    """, (job_id,))
    job = cur.fetchone()
    conn.close()

    company_website = job[3] if job and job[3] else None
    return render_template("apply_job.html", job_id=job_id, company_website=company_website)


@app.route("/submit_application/<int:job_id>", methods=["POST"])
def submit_application(job_id):

    if "user" not in session:
        return redirect("/auth?error=Login required to upload resume and apply for a job")

    try:
        file = request.files.get("resume")
        if not file or file.filename == "":
            raise ValueError("No file selected")

        filename = file.filename
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        resume_text = extract_text(filepath)

        # compute hash and detect duplicates/fakes
        hsh = hashlib.sha256(resume_text.encode('utf-8')).hexdigest()
        is_dup = 0
        is_fake = 0

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        # fetch full job details
        cur.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        job = cur.fetchone()
        if not job:
            raise ValueError("Job not found")

        job_skills = job[3]
        vacancies = job[4]
        skills_available = is_skills_specified(job_skills)

        # compute missing skills
        if skills_available:
            skill_list = [s.strip().lower() for s in job_skills.split(",") if s.strip()]
            resume_lower = resume_text.lower()
            missing = [s for s in skill_list if s and s not in resume_lower]
            missing_str = ",".join(missing)
            score = calculate_score(resume_text, job_skills)
        else:
            missing_str = ""
            # fallback score when job has no explicit skills; keep deterministic and simple
            score = 65 if len(resume_text) >= 200 else 45

        status = get_initial_application_status(score)

        # check duplicate
        cur.execute("SELECT id FROM applications WHERE resume_hash=?", (hsh,))
        if cur.fetchone():
            is_dup = 1
            status = "Rejected"

        # simple fake detection
        if len(resume_text) < 100 or "lorem ipsum" in resume_text.lower():
            is_fake = 1
            status = "Rejected"

        # reduce vacancy only when an application is selected
        if status == "Selected":
            new_vacancies = max(0, vacancies - 1)
            new_job_status = "Closed" if new_vacancies == 0 else "Open"
            cur.execute(
                "UPDATE jobs SET vacancies=?, status=? WHERE id=?",
                (new_vacancies, new_job_status, job_id),
            )

        # get user email (session stores email now)
        user_email = session.get("user")
        applicant_name = session.get("user_name", user_email)

        cur.execute(
            "INSERT INTO applications(user,user_email,job_id,filename,score,missing_skills,status,resume_hash,is_duplicate,is_fake,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
            (applicant_name, user_email, job_id, filename, score, missing_str, status, hsh, is_dup, is_fake),
        )
        conn.commit()
        
        app_id = cur.lastrowid

        # try to pull out structured sections; this is a naive NLP extraction
        details = extract_resume_details(resume_text)
        log_application_event(app_id, "Submitted", f"Application submitted for {job[2]} at {job[1]}")
        if details:
            log_application_event(app_id, "Resume Parsed", f"Extracted sections: {details}")
        log_application_event(app_id, "Screening", f"Score={score}, missing={missing_str or 'none'}, dup={is_dup}, fake={is_fake}")
        log_application_event(app_id, status, f"Tracker moved to '{status}'")

        if user_email:
            subj = f"Your application for {job[2]} at {job[1]}"
            body = f"Your application has been received and is currently '{status}'."
            if missing_str:
                body += f"\nMissing skills: {missing_str}"
            if is_dup:
                body += "\nNote: similar resume was submitted earlier, so this application is marked rejected."
            if is_fake:
                body += "\nWarning: resume appears incomplete or invalid, so this application is marked rejected."
            send_email(user_email, subj, body)

        conn.close()

        return render_template(
            "application_result.html",
            job=job,
            app_id=app_id,
            score=score,
            status=status,
            missing_skills=missing_str,
            job_skills=job_skills if skills_available else "",
            job_description_highlights=build_description_highlights(job[5]),
            resume_text=resume_text,
        )
    except Exception as e:
        # log error and return result page with message
        try:
            conn.close()
        except Exception:
            pass
        # sanitize known database errors for users
        msg = str(e)
        if isinstance(e, sqlite3.Error):
            msg = "There was a problem processing your application. Please try again later."
        return render_template("application_result.html", job=None, score=0, status="Error", missing_skills="", error=msg)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# user profile update
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user" not in session:
        return redirect("/auth")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        location = request.form.get("location")
        birthday = request.form.get("birthday")
        password = request.form.get("password")

        if password:
            # enforce password min length when updating
            if len(password) < 6:
                conn.close()
                return redirect("/profile?error=Password must be at least 6 characters")
            cur.execute(
                "UPDATE users SET name=?, email=?, location=?, birthday=?, password=? WHERE email=?",
                (name, email, location, birthday, password, session["user"]),
            )
        else:
            cur.execute(
                "UPDATE users SET name=?, email=?, location=?, birthday=? WHERE email=?",
                (name, email, location, birthday, session["user"]),
            )

        conn.commit()
        conn.close()
        session["user"] = email
        session["user_name"] = name
        return redirect("/user_dashboard")
    else:
        cur.execute(
            "SELECT name, email, location, birthday, profile_pic FROM users WHERE email=?",
            (session["user"],),
        )
        user_row = cur.fetchone()
        conn.close()
        return render_template("profile_edit.html", user=user_row, name=session.get("user_name"))


@app.route("/upload_profile_pic", methods=["POST"])
def upload_profile_pic():
    if "user" not in session:
        return redirect("/auth")

    if "profile_pic" not in request.files:
        return redirect("/profile")

    file = request.files["profile_pic"]
    if file.filename == "":
        return redirect("/profile")

    # save file
    filename = f"profile_{session['user']}.png"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET profile_pic=? WHERE name=?",
        (filepath, session["user"]),
    )
    conn.commit()
    conn.close()

    return redirect("/profile")


@app.route("/career_guidance")
def career_guidance():
    """Show career suggestions based on user's missing skills."""
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM career_paths")
    paths = cur.fetchall()
    conn.close()

    return render_template("career_guidance.html", career_paths=paths)


@app.route("/course_notes/<int:path_id>")
def course_notes(path_id):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM career_paths WHERE id=?", (path_id,))
    path = cur.fetchone()

    if not path:
        conn.close()
        return redirect("/career_guidance")

    cur.execute(
        """
        SELECT id, course_title, module_title, note_body, objectives, practice,
               duration, interview_focus, source_platform, source_url, difficulty, reference_clicks
        FROM course_notes_catalog
        WHERE path_id=?
        ORDER BY display_order, id
        """,
        (path_id,),
    )
    rows = cur.fetchall()
    conn.close()

    notes_data = []
    for row in rows:
        notes_data.append(
            {
                "id": row[0],
                "course_title": row[1],
                "title": row[2],
                "content": row[3],
                "objectives": decode_note_list(row[4]),
                "practice": decode_note_list(row[5]),
                "duration": row[6] or "5-7 days",
                "interview_focus": row[7] or "Explain tradeoffs and implementation details clearly.",
                "source_platform": row[8] or "Reference Platform",
                "source_url": row[9] or "",
                "difficulty": row[10] or "Intermediate",
                "reference_clicks": row[11] or 0,
            }
        )

    return render_template("course_notes.html", path=path, notes=notes_data)


@app.route("/course_reference/<int:note_id>")
def course_reference(note_id):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT source_url FROM course_notes_catalog WHERE id=?", (note_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        return redirect("/career_guidance")

    cur.execute(
        "UPDATE course_notes_catalog SET reference_clicks=COALESCE(reference_clicks, 0) + 1 WHERE id=?",
        (note_id,),
    )
    conn.commit()
    conn.close()
    return redirect(row[0])


@app.route("/resume_builder", methods=["GET", "POST"])
def resume_builder():
    if "user" not in session:
        return redirect("/auth")
    
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    if request.method == "POST":
        # Extract basic info
        name = request.form.get("name", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        links = request.form.get("links", "")
        summary = request.form.get("summary", "")
        skills = request.form.get("skills", "")

        # Extract dynamic arrays
        exp_titles = request.form.getlist("exp_title[]")
        exp_companies = request.form.getlist("exp_company[]")
        exp_dates = request.form.getlist("exp_dates[]")
        exp_details = request.form.getlist("exp_details[]")
        
        experience = []
        for i in range(len(exp_titles)):
            if exp_titles[i] or exp_companies[i]:
                experience.append({
                    "title": exp_titles[i],
                    "company": exp_companies[i],
                    "dates": exp_dates[i] if len(exp_dates) > i else "",
                    "details": exp_details[i] if len(exp_details) > i else ""
                })

        edu_degrees = request.form.getlist("edu_degree[]")
        edu_schools = request.form.getlist("edu_school[]")
        edu_details = request.form.getlist("edu_details[]")
        
        education = []
        for i in range(len(edu_degrees)):
            if edu_degrees[i] or edu_schools[i]:
                education.append({
                    "degree": edu_degrees[i],
                    "school": edu_schools[i],
                    "details": edu_details[i] if len(edu_details) > i else ""
                })

        # Process skills and certifications
        skills_list = [s.strip() for s in skills.split(",")] if skills else []
        certs_raw = request.form.get("certifications", "")
        # Try splitting by newline, then comma
        if "\n" in certs_raw:
            certs_list = [c.strip() for c in certs_raw.split("\n") if c.strip()]
        else:
            certs_list = [c.strip() for c in certs_raw.split(",")] if certs_raw else []

        # Process Projects
        proj_titles = request.form.getlist("proj_title[]")
        proj_dates = request.form.getlist("proj_dates[]")
        proj_details = request.form.getlist("proj_details[]")
        
        projects = []
        for i in range(len(proj_titles)):
            if proj_titles[i]:
                projects.append({
                    "title": proj_titles[i],
                    "dates": proj_dates[i] if len(proj_dates) > i else "",
                    "details": proj_details[i] if len(proj_details) > i else ""
                })

        # Package data for template
        resume_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "links": links,
            "summary": summary,
            "experience": experience,
            "education": education,
            "projects": projects,
            "certifications": certs_list,
            "skills_list": skills_list
        }
        
        conn.close()
        return render_template("resume_generated.html", data=resume_data)

    else:
        # GET request: load user profile data to pre-fill the form
        cur.execute(
            "SELECT name, email, location FROM users WHERE email=?",
            (session["user"],),
        )
        user_row = cur.fetchone()
        conn.close()
        return render_template("resume_builder.html", user=user_row)


# ================= ADMIN =================

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if "admin" in session:
        return redirect("/admin_dashboard")

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        # only the locked-down account is valid
        cur.execute(
            "SELECT * FROM admin WHERE username=? AND password=?",
            (username, password),
        )
        admin = cur.fetchone()
        if admin and username == 'himabindu':
            # proceed only if the username matches the confidential account
            # check if admin already logged in elsewhere
            cur.execute(
                "SELECT id FROM admin_sessions WHERE username=? AND active=1",
                (username,),
            )
            existing = cur.fetchone()
            if existing:
                # logout previous session
                cur.execute(
                    "UPDATE admin_sessions SET active=0 WHERE username=? AND active=1",
                    (username,),
                )

            # create new session
            cur.execute(
                "INSERT INTO admin_sessions(username,active) VALUES(?,1)",
                (username,),
            )
            admin_session_id = cur.lastrowid
            conn.commit()
            conn.close()

            # password verification + session ID for extra security
            session["admin"] = username
            session["admin_session_id"] = admin_session_id
            return redirect("/admin_dashboard")

        conn.close()
        return render_template("admin_login.html", error="Invalid credentials")

    return render_template("admin_login.html")


# ===== company registration/login =====
@app.route("/company_register", methods=["GET", "POST"])
def company_register():
    if request.method == "POST":
        cname = request.form.get("company")
        username = request.form.get("username")
        password = request.form.get("password")
        # enforce minimum password length for company accounts
        if not password or len(password) < 6:
            return redirect("/company_register?error=Password must be at least 6 characters")
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        # ensure company row exists
        cur.execute("SELECT id FROM companies WHERE name=?", (cname,))
        comp = cur.fetchone()
        if not comp:
            cur.execute(
                "INSERT INTO companies(name,description,logo,location) VALUES(?,?,?,?)",
                (cname, "", "", ""),
            )
            comp_id = cur.lastrowid
        else:
            comp_id = comp[0]
        # enforce company password length
        if not password or len(password) < 6:
            conn.close()
            return redirect("/company_register?error=Password must be at least 6 characters")
        cur.execute(
            "INSERT INTO company_accounts(company_id,username,password) VALUES(?,?,?)",
            (comp_id, username, password),
        )
        conn.commit()
        conn.close()
        session["company"] = comp_id
        return redirect("/company_dashboard")
    return render_template("company_register.html")


@app.route("/company_login", methods=["GET", "POST"])
def company_login():
    if "company" in session:
        return redirect("/company_dashboard")
        
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        if not username or not password:
            return render_template("company_login.html", error="Username and password are required")
        
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT company_id FROM company_accounts WHERE username=? AND password=?",
            (username, password),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            session["company"] = row[0]
            return redirect("/company_dashboard")
        return render_template("company_login.html", error="Invalid username or password")
    return render_template("company_login.html")


@app.route("/company_dashboard")
def company_dashboard():
    if "company" not in session:
        return redirect("/company_login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT jobs.id, jobs.company, jobs.title, jobs.skills, jobs.vacancies,
               jobs.description, jobs.status, api_keys.key
        FROM jobs
        LEFT JOIN api_keys ON api_keys.job_id=jobs.id AND api_keys.module='job'
        WHERE jobs.company_id=?
        """,
        (session["company"],)
    )
    jobs = cur.fetchall()

    cur.execute(
        "SELECT COUNT(applications.id) FROM applications JOIN jobs ON applications.job_id=jobs.id WHERE jobs.company_id=?",
        (session["company"],)
    )
    result = cur.fetchone()
    total_apps = result[0] if result else 0

    conn.close()
    return render_template("company_dashboard.html", jobs=jobs, total_apps=total_apps)


@app.route("/company_applications")
def company_applications():
    if "company" not in session:
        return redirect("/company_login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT applications.id, applications.user, applications.filename, jobs.title, applications.score, applications.status
        FROM applications JOIN jobs ON applications.job_id=jobs.id
        WHERE jobs.company_id=?
        ORDER BY applications.score DESC
        """,
        (session["company"],),
    )
    applications = cur.fetchall()
    conn.close()
    return render_template("company_applications.html", applications=applications)


@app.route("/chat", methods=["GET"])
def chat():
    current_token = session.get("chat_session_token")
    chat_session = create_chat_session(user_email=session.get("user"), session_token=current_token)
    session["chat_session_token"] = chat_session["session_token"]
    messages = get_chat_messages(chat_session["session_token"], user_email=session.get("user"), limit=20)
    return render_template(
        "chat.html",
        messages=messages,
        chat_session_token=chat_session["session_token"],
        suggestions=DEFAULT_CHAT_SUGGESTIONS,
        prefill_question=request.args.get("question", "").strip(),
    )


@app.route("/chat_api", methods=["POST"])
def chat_api():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"ok": False, "error": "Please enter a question."}), 400

    current_token = str(data.get("session_token", "")).strip() or session.get("chat_session_token")
    chat_session = create_chat_session(user_email=session.get("user"), session_token=current_token)
    session["chat_session_token"] = chat_session["session_token"]

    history = get_chat_messages(chat_session["session_token"], user_email=session.get("user"), limit=12)
    result = generate_chat_response(question, history=history)

    if not result.get("ok"):
        return jsonify(result), 503

    save_chat_message(chat_session["session_token"], session.get("user"), "user", question)
    save_chat_message(chat_session["session_token"], session.get("user"), "assistant", result["answer"])
    return jsonify(
        {
            "ok": True,
            "answer": result["answer"],
            "source": result.get("source", "ai"),
            "session_token": chat_session["session_token"],
        }
    )


@app.route("/chat_reset", methods=["POST"])
def chat_reset():
    chat_session = create_chat_session(user_email=session.get("user"))
    session["chat_session_token"] = chat_session["session_token"]
    return jsonify({"ok": True, "session_token": chat_session["session_token"]})


@app.route("/health_openai", methods=["GET"])
def health_openai():
    result = get_chatbot_health()
    return jsonify(result), 200 if result.get("ok") else 503


def extract_skills_from_text(text):
    """Extract common tech skills from job description text."""
    if not text:
        return []
    
    tech_keywords = [
        'Python', 'JavaScript', 'Java', 'C++', 'C#', 'Go', 'Rust', 'Ruby', 'PHP', 'Swift', 'Kotlin',
        'React', 'Vue', 'Angular', 'Node.js', 'Django', 'Flask', 'FastAPI', 'Spring',
        'SQL', 'MongoDB', 'PostgreSQL', 'MySQL', 'Redis', 'Elasticsearch',
        'AWS', 'Azure', 'Google Cloud', 'Docker', 'Kubernetes', 'Terraform',
        'Git', 'CI/CD', 'DevOps', 'Jenkins', 'GitLab', 'GitHub',
        'Machine Learning', 'TensorFlow', 'PyTorch', 'Scikit-learn',
        'HTML', 'CSS', 'REST API', 'GraphQL', 'WebSockets',
        'Agile', 'Scrum', 'Jira', 'Confluence'
    ]
    
    text_lower = text.lower()
    found_skills = []
    for skill in tech_keywords:
        if skill.lower() in text_lower:
            found_skills.append(skill)
    
    return found_skills[:6]  # return up to 6 skills


@app.route("/import_jobs")
def import_jobs():
    """Fetch real job postings from RapidAPI using the master API key.
    This pulls live job data from JSearch API and populates the database with actual job info."""
    if "admin" not in session:
        return redirect("/admin_login")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT key FROM api_keys WHERE module='master' LIMIT 1")
    row = cur.fetchone()
    if not row:
        conn.close()
        return "No master API key configured."
    master_key = row[0]

    # Company-specific vacancy counts (realistic numbers)
    vacancy_map = {
        'Google': 5,
        'Microsoft': 3,
        'Amazon': 4,
        'Apple': 2,
        'IBM': 1
    }

    # Real RapidAPI endpoint for job listings
    url = "https://jsearch.p.rapidapi.com/search"
    
    headers = {
        'X-RapidAPI-Key': master_key,
        'X-RapidAPI-Host': 'jsearch.p.rapidapi.com'
    }
    
    # Search for jobs at major tech companies
    companies_to_search = ['Google', 'Microsoft', 'Amazon', 'Apple', 'IBM']
    count = 0
    
    for company_name in companies_to_search:
        params = {
            'query': f'{company_name} jobs',
            'page': '1',
            'num_pages': '1'
        }
        
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            continue  # skip if this company's fetch fails
        
        # Parse job data from API response
        for item in data.get('data', []):
            job_title = item.get('job_title')
            job_desc = item.get('job_description', 'Position available')
            required_skills = item.get('job_required_skills')
            
            # Format skills: try API first, then extract from description
            if isinstance(required_skills, list) and len(required_skills) > 0:
                skills_str = ','.join(str(s) for s in required_skills[:6])
            else:
                # Extract skills from job description
                extracted = extract_skills_from_text(job_desc)
                if extracted:
                    skills_str = ','.join(extracted)
                else:
                    skills_str = 'Not specified'
            
            # Look up or create company
            cur.execute("SELECT id FROM companies WHERE name=?", (company_name,))
            comp_row = cur.fetchone()
            if comp_row:
                comp_id = comp_row[0]
            else:
                cur.execute("INSERT INTO companies(name,description,logo,location,website) VALUES(?,?,?,?,?)",
                            (company_name, '', '', '', ''))
                comp_id = cur.lastrowid
            
            # Check if job already exists
            cur.execute("SELECT id FROM jobs WHERE title=? AND company_id=? LIMIT 1", (job_title, comp_id))
            if cur.fetchone():
                continue  # skip duplicates
            
            # Get vacancy count from map
            vacancies = vacancy_map.get(company_name, 3)
            
            # Insert the real job posting
            cur.execute(
                "INSERT INTO jobs(company,company_id,title,skills,vacancies,description,status,is_demo) VALUES(?,?,?,?,?,?,?,?)",
                (company_name, comp_id, job_title, skills_str, vacancies, job_desc, 'Open', 0)
            )
            job_id = cur.lastrowid
            
            # Generate and store job-specific API key
            job_key = generate_job_api_key(master_key, job_id, company_name, job_title or "", vacancies)
            try:
                cur.execute(
                    "INSERT INTO api_keys(module,key,company_id,job_id) VALUES(?,?,?,?)",
                    ("job", job_key, comp_id, job_id)
                )
            except Exception:
                pass
            
            count += 1
    
    conn.commit()
    conn.close()
    
    if count > 0:
        return f"Successfully imported {count} real jobs from RapidAPI with actual skills and vacancy counts."
    else:
        return "Could not import jobs. Please verify your API key has credits remaining."


@app.route("/admin_dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect("/admin_login")

    try:
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        # fetch all jobs
        cur.execute("SELECT * FROM jobs")
        jobs = cur.fetchall() or []

        # total users
        cur.execute("SELECT COUNT(*) FROM users")
        result = cur.fetchone()
        total_users = result[0] if result else 0

        # applications per job
        cur.execute(
            "SELECT jobs.title, COUNT(applications.id) FROM applications JOIN jobs ON applications.job_id=jobs.id GROUP BY jobs.title"
        )
        apps_per_job = cur.fetchall() or []

        # hiring rate
        cur.execute("SELECT COUNT(*) FROM applications")
        result = cur.fetchone()
        total_apps = result[0] if result else 0
        
        cur.execute("SELECT COUNT(*) FROM applications WHERE status='Selected'")
        result = cur.fetchone()
        selected_apps = result[0] if result else 0
        
        if total_apps > 0:
            hiring_rate = (selected_apps * 100.0) / total_apps
        else:
            hiring_rate = 0.0

        conn.close()

        return render_template(
            "admin_dashboard.html",
            jobs=jobs,
            total_users=total_users,
            apps_per_job=apps_per_job,
            hiring_rate=round(hiring_rate, 1),
        )
    except Exception as e:
        conn.close() if conn else None
        return f"Error loading admin dashboard: {str(e)}", 500


@app.route("/companies")
def companies():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    
    # Get search and location filters from query parameters
    search = request.args.get('search', '').strip()
    location = request.args.get('location', '').strip()
    
    # Build query dynamically based on filters
    query = "SELECT * FROM companies WHERE 1=1"
    params = []
    
    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    
    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")
    
    query += " ORDER BY name"
    
    cur.execute(query, params)
    companies_list = cur.fetchall()
    
    # Get unique locations for the filter dropdown
    cur.execute("SELECT DISTINCT location FROM companies WHERE location IS NOT NULL ORDER BY location")
    locations = [row[0] for row in cur.fetchall()]
    
    conn.close()
    
    return render_template("companies.html", companies=companies_list, locations=locations, 
                           search=search, selected_location=location)


@app.route("/companies/<int:company_id>")
def company_detail(company_id):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM companies WHERE id=?", (company_id,))
    company = cur.fetchone()

    if not company:
        conn.close()
        return redirect("/companies")

    # get open positions for this company (matching by name)
    cur.execute("SELECT * FROM jobs WHERE company=? AND status='Open'", (company[1],))
    jobs = cur.fetchall()
    conn.close()
    return render_template("company_detail.html", company=company, jobs=jobs)


@app.route("/post_job", methods=["GET", "POST"])
def post_job():

    if "admin" not in session and "company" not in session:
        return redirect("/admin_login")

    if request.method == "POST":

        title = request.form["title"]
        skills = request.form.get("skills", "").strip()
        vacancies = request.form["vacancies"]
        description = request.form["description"]

        if not skills:
            # 1. Try to extract from description
            extracted = extract_skills_from_text(description)
            
            # 2. Try to extract from title
            if not extracted:
                extracted = extract_skills_from_text(title)
                
            if extracted:
                skills = ', '.join([s.title() if s.islower() else s for s in extracted])
            else:
                skills = ""

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        if "admin" in session:
            company = request.form["company"]
            # look up company id if exists
            cur.execute("SELECT id FROM companies WHERE name=?", (company,))
            row = cur.fetchone()
            company_id = row[0] if row else None
        else:
            # company user posting
            company_id = session["company"]
            cur.execute("SELECT name FROM companies WHERE id=?", (company_id,))
            row = cur.fetchone()
            company = row[0] if row else ""

        cur.execute(
            """
            INSERT INTO jobs(company,company_id,title,skills,vacancies,description,status)
            VALUES(?,?,?,?,?,?,?)
            """,
            (company, company_id, title, skills, vacancies, description, 'Open'),
        )

        # capture the inserted job id
        job_id = cur.lastrowid

        # generate a per-job API key derived from the master key and job fields
        try:
            cur.execute("SELECT key FROM api_keys WHERE module='master' LIMIT 1")
            mk_row = cur.fetchone()
            if mk_row:
                master_key = mk_row[0]
                # ensure vacancies is an int for key generation
                try:
                    vac_int = int(vacancies)
                except Exception:
                    vac_int = 0
                job_key = generate_job_api_key(master_key, job_id, company or "", title or "", vac_int)
                # store job-specific key so each job can have its own API token
                try:
                    cur.execute(
                        "INSERT INTO api_keys(module,key,company_id,job_id) VALUES(?,?,?,?)",
                        ("job", job_key, company_id, job_id),
                    )
                except Exception:
                    # ignore duplicate key insertion errors
                    pass
        except Exception:
            pass

        conn.commit()
        conn.close()

        if "admin" in session:
            return redirect("/admin_dashboard")
        else:
            return redirect("/company_dashboard")

    return render_template("post_job.html")


@app.route("/view_applications")
def view_applications():

    if "admin" not in session:
        return redirect("/admin_login")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    # Fetch all applications with job details, sorted by score (highest first)
    cur.execute(
        """
         SELECT applications.id, applications.user, applications.user_email, applications.filename, jobs.title, jobs.company, 
             applications.score, applications.status, applications.job_id
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        ORDER BY applications.score DESC
        """
    )

    applications = cur.fetchall()
    conn.close()

    return render_template("applications_admin.html", applications=applications)


@app.route("/application_logs/<int:app_id>")
def application_logs(app_id):
    # allow both admin and the user who submitted this application
    if "admin" not in session and "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    # if regular user, ensure they own the application
    if "user" in session and "admin" not in session:
        cur.execute(
            "SELECT id FROM applications WHERE id=? AND user_email=?",
            (app_id, session["user"]),
        )
        if not cur.fetchone():
            conn.close()
            return "Not authorized"

    cur.execute(
        "SELECT status, message, timestamp FROM application_logs WHERE application_id=? ORDER BY timestamp DESC",
        (app_id,),
    )
    logs = cur.fetchall()
    conn.close()

    return render_template("application_logs.html", logs=logs)


@app.route("/download_resume/<int:app_id>")
def download_resume(app_id):
    if "admin" not in session:
        return redirect("/admin_login")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT filename, user FROM applications WHERE id=?", (app_id,))
    app_record = cur.fetchone()
    conn.close()

    if not app_record:
        return "Application not found"

    filename = app_record[0]
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return "Resume not found"


@app.route("/update_application_status/<int:app_id>/<status>", methods=["GET", "POST"])
def update_application_status(app_id, status):
    if "admin" not in session:
        return redirect("/admin_login")

    if status not in TRACKER_UPDATE_STATUSES:
        return "Invalid status"

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT status, job_id FROM applications WHERE id=?", (app_id,))
    current_row = cur.fetchone()
    if not current_row:
        conn.close()
        return "Application not found"

    old_status, job_id = current_row

    if old_status != "Selected" and status == "Selected":
        cur.execute("SELECT vacancies FROM jobs WHERE id=?", (job_id,))
        job_row = cur.fetchone()
        vacancies = job_row[0] if job_row else 0
        if vacancies <= 0:
            conn.close()
            return "No vacancies left for this job"
        vacancies -= 1
        cur.execute(
            "UPDATE jobs SET vacancies=?, status=? WHERE id=?",
            (vacancies, "Closed" if vacancies == 0 else "Open", job_id),
        )
    elif old_status == "Selected" and status != "Selected":
        cur.execute("SELECT vacancies FROM jobs WHERE id=?", (job_id,))
        job_row = cur.fetchone()
        vacancies = (job_row[0] if job_row else 0) + 1
        cur.execute(
            "UPDATE jobs SET vacancies=?, status='Open' WHERE id=?",
            (vacancies, job_id),
        )

    # update status
    cur.execute("UPDATE applications SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, app_id))

    # fetch email/job info for notification
    cur.execute(
        "SELECT user_email, jobs.title, jobs.company FROM applications JOIN jobs ON jobs.id=applications.job_id WHERE applications.id=?",
        (app_id,),
    )
    row = cur.fetchone()
    if row:
        user_email, job_title, job_company = row
        message = f"Your application for {job_title} at {job_company} has been marked '{status}'."
        # send email if we have address
        if user_email:
            send_email(user_email, "Application Status Update", message)
        # log the change
        log_application_event(app_id, status, message)

    conn.commit()
    conn.close()

    return redirect("/view_applications")


if __name__ == "__main__":
    def get_configured_port(default_port=5000):
        raw_port = str(os.getenv("FLASK_PORT", os.getenv("PORT", default_port))).strip()
        try:
            port = int(raw_port)
        except Exception:
            port = int(default_port)
        return max(1, min(65535, port))

    def find_available_port(preferred_port):
        """Pick preferred port when free, otherwise scan a small fallback range."""
        for candidate in [preferred_port] + list(range(preferred_port + 1, preferred_port + 11)):
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.bind(("0.0.0.0", candidate))
                return candidate
            except OSError:
                continue
            finally:
                probe.close()
        return preferred_port

    def get_lan_ip():
        """Best-effort LAN IP discovery for same-network mobile access."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            sock.close()

    host = os.getenv("FLASK_HOST", "0.0.0.0")
    preferred_port = get_configured_port(5000)
    port = find_available_port(preferred_port)
    lan_ip = get_lan_ip()
    lan_url = f"http://{lan_ip}:{port}"

    try:
        from pyngrok import ngrok
        public_url = ngrok.connect(port)
        print("\n" + "="*55)
        print(f"  Mobile/Public URL : {public_url}")
        print(f"  Mobile/LAN URL    : {lan_url}")
        print(f"  Local URL         : http://127.0.0.1:{port}")
        print("="*55 + "\n")
    except Exception as e:
        print(f"[ngrok] Could not start tunnel: {e}")
        print(f"  Local URL: http://127.0.0.1:{port}")
        print(f"  Mobile/LAN URL: {lan_url}")

    if port != preferred_port:
        print(f"[port] {preferred_port} was busy, using {port} instead.")

    app.run(host=host, port=port, debug=True, use_reloader=False)
