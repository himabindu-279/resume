import os

import requests

from config import CHAT_HISTORY_WINDOW, OPENAI_API_URL, OPENAI_MODEL, OPENAI_TIMEOUT_SECONDS


FAQ = {
    "how to apply": "Browse available jobs, open the job details, and submit your resume from the apply page.",
    "how to upload resume": "Use a PDF or DOCX file on the application form. The system reads the resume automatically after upload.",
    "available jobs": "Open the jobs listing, companies page, or your user dashboard to review current openings.",
}

DEFAULT_CHAT_SUGGESTIONS = [
    "How do I apply for a backend job?",
    "What should I improve in my resume for Python roles?",
    "Give me interview tips for a Flask developer position.",
]

SYSTEM_PROMPT = (
    "You are Hirevue Assistant, a support chatbot for a resume and job portal. "
    "Help users with jobs, resumes, interview preparation, application steps, and career guidance. "
    "Be concise, practical, and accurate. If platform data is unavailable, say so clearly instead of inventing facts."
)


def _read_env_value(name):
    value = os.getenv(name, "").strip()
    if value:
        return value

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return ""

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                env_name, env_value = line.split("=", 1)
                if env_name.strip() == name:
                    return env_value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def get_openai_api_key():
    return _read_env_value("OPENAI_API_KEY")


def get_faq_answer(question):
    question_lower = question.lower()
    for trigger, answer in FAQ.items():
        if trigger in question_lower:
            return answer
    return None


def get_rule_based_answer(question):
    question_lower = question.lower()

    if any(token in question_lower for token in ["resume", "cv"]):
        return (
            "For a stronger resume, keep it role-specific, highlight measurable impact, list your core tech stack, "
            "and make sure the same skills appear in both your project bullets and skills section."
        )
    if any(token in question_lower for token in ["interview", "prepare"]):
        return (
            "For interview preparation, review the job skills one by one, prepare 2 to 3 project stories with outcomes, "
            "and practice explaining architecture, debugging steps, and tradeoffs clearly."
        )
    if any(token in question_lower for token in ["apply", "application"]):
        return (
            "To apply effectively, choose a matching job, tailor the resume to that role, upload the latest resume, "
            "and verify your profile details before submitting."
        )
    if any(token in question_lower for token in ["backend", "flask", "python"]):
        return (
            "For backend roles, focus on Python, Flask or FastAPI, SQL, REST APIs, authentication, testing, and deployment basics. "
            "Projects with clear APIs, database design, and production-style structure will help most."
        )
    return None


def _build_messages(question, history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-CHAT_HISTORY_WINDOW:]:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages


def generate_chat_response(question, history=None):
    question = str(question or "").strip()
    if not question:
        return {"ok": False, "error": "Please enter a question."}

    history = history or []
    api_key = get_openai_api_key()
    api_error = None

    if api_key:
        payload = {
            "model": OPENAI_MODEL,
            "messages": _build_messages(question, history),
            "temperature": 0.3,
            "max_tokens": 350,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                OPENAI_API_URL,
                headers=headers,
                json=payload,
                timeout=OPENAI_TIMEOUT_SECONDS,
            )
            if response.status_code >= 400:
                try:
                    api_error = response.json().get("error", {}).get("message", "Unknown API error")
                except ValueError:
                    api_error = response.text[:200] or "Unknown API error"
            else:
                data = response.json()
                answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if answer:
                    return {"ok": True, "answer": answer, "source": "ai", "model": OPENAI_MODEL}
                api_error = "OpenAI returned an empty response."
        except requests.RequestException as exc:
            api_error = f"Network error while contacting OpenAI: {exc}"
        except (ValueError, KeyError, TypeError):
            api_error = "Unexpected response format from OpenAI API."
    else:
        api_error = "OPENAI_API_KEY is missing."

    faq_answer = get_faq_answer(question)
    if faq_answer:
        return {"ok": True, "answer": faq_answer, "source": "faq", "fallback_reason": api_error}

    rule_answer = get_rule_based_answer(question)
    if rule_answer:
        return {"ok": True, "answer": rule_answer, "source": "rules", "fallback_reason": api_error}

    return {"ok": False, "error": api_error or "Unable to generate a response right now."}


def get_chatbot_health():
    api_key = get_openai_api_key()
    masked_key = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 12 else ("set" if api_key else "missing")
    if not api_key:
        return {"ok": False, "model": OPENAI_MODEL, "key": masked_key, "error": "OPENAI_API_KEY is missing."}

    result = generate_chat_response("Health check. Reply with OK.")
    if result.get("ok") and result.get("source") == "ai":
        return {"ok": True, "model": OPENAI_MODEL, "key": masked_key}

    return {
        "ok": False,
        "model": OPENAI_MODEL,
        "key": masked_key,
        "error": result.get("error") or result.get("fallback_reason") or "AI service check failed.",
    }