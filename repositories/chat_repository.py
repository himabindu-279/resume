import sqlite3
import uuid

from config import DATABASE_PATH


def _get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_chat_tables(connection):
    cur = connection.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT UNIQUE,
            user_email TEXT,
            title TEXT DEFAULT 'New chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(chat_session_id) REFERENCES chat_sessions(id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_token ON chat_sessions(session_token)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(chat_session_id)")


def _normalize_session(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_token": row["session_token"],
        "user_email": row["user_email"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_chat_session(session_token):
    if not session_token:
        return None

    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chat_sessions WHERE session_token=?", (session_token,))
    row = cur.fetchone()
    conn.close()
    return _normalize_session(row)


def create_chat_session(user_email=None, session_token=None, title="New chat"):
    existing = get_chat_session(session_token)
    if existing:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP, user_email=COALESCE(?, user_email) WHERE session_token=?",
            (user_email, session_token),
        )
        conn.commit()
        conn.close()
        return get_chat_session(session_token)

    token = session_token or uuid.uuid4().hex
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_sessions(session_token,user_email,title) VALUES(?,?,?)",
        (token, user_email, title),
    )
    conn.commit()
    conn.close()
    return get_chat_session(token)


def save_chat_message(session_token, user_email, role, content):
    chat_session = create_chat_session(user_email=user_email, session_token=session_token)
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_messages(chat_session_id,role,content) VALUES(?,?,?)",
        (chat_session["id"], role, content),
    )
    if role == "user" and chat_session["title"] == "New chat":
        cur.execute(
            "UPDATE chat_sessions SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            ((content[:57] + "...") if len(content) > 60 else content, chat_session["id"]),
        )
    else:
        cur.execute(
            "UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (chat_session["id"],),
        )
    conn.commit()
    conn.close()


def get_chat_messages(session_token, user_email=None, limit=12):
    chat_session = create_chat_session(user_email=user_email, session_token=session_token)
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content, created_at FROM chat_messages WHERE chat_session_id=? ORDER BY id DESC LIMIT ?",
        (chat_session["id"], limit),
    )
    rows = cur.fetchall()
    conn.close()
    messages = []
    for row in reversed(rows):
        messages.append(
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
        )
    return messages