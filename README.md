# Job Portal Application

This Flask-based job portal supports users, companies, and a restricted admin.

## Backend Module Plan For A Bigger Project

If you want to grow this into a larger backend, the clean module split should be:

- `config.py` for environment variables, keys, model names, and database paths.
- `services/` for business logic such as chatbot generation, resume scoring, notifications, and job imports.
- `repositories/` for database access code so route handlers stay small.
- `routes/` later, when you split `app.py` into Blueprints for auth, jobs, chatbot, admin, and companies.
- `templates/` and `static/` for UI only, without backend logic inside templates.

The first real-world module added in this project is the chatbot backend:

- `services/chatbot_service.py` handles AI requests, FAQ fallback, and rule-based support answers.
- `repositories/chat_repository.py` stores chat sessions and chat history in SQLite.
- `config.py` centralizes model and secret configuration.

## Key Features

- User registration/login with email and password (passwords require 6+ characters).
- Users apply to jobs; their resumes are hashed and scored against job skills.
- Companies can register, post jobs, and see applicants.
- Admin has a single confidential account (`himabindu`/`hima`).
- API-key infrastructure: a master key is stored (`7738501078msh629d88695c19b1bp1c4eeajsn556ca45ae6af`),
  and each posted job generates a derived key which companies can view on their dashboard
  for programmatic access.
- Demo jobs are removed from production and real company data seeded.
- Career guidance and application logging included.

## Configuration and Extending with External Data

The database (`database.db`) is created automatically when you run `app.py`.  Some
columns are appended during migrations to maintain backwards compatibility.

### Using an External API for Real Company Jobs

The current seed data includes realistic descriptions for well-known firms.  If you
wish to populate jobs directly from a third‑party service (for example, an ATS or
jobs API), follow these general steps:

1. **Obtain API credentials** from the service provider.  The master API key in the
   `api_keys` table is only for your own application's internal derivations; it does
   not grant access to external vendor data.
2. **Read the provider's documentation** to learn the endpoints and parameters.
3. **Make HTTP requests** using a library such as `requests`:
   ```python
   import requests

   resp = requests.get(
       'https://provider.example.com/v1/jobs',
       headers={'Authorization': 'Bearer YOUR_VENDOR_KEY'},
       params={'company': 'Google'}
   )
   data = resp.json()
   # iterate and insert into local `jobs` table
   ```
4. You can automate this by creating a new route (`/import_jobs`) or a scheduled
   script that fetches and inserts/updates job records.  Remember to apply the
   `generate_job_api_key` function if you want per-job API tokens.

If the API key you provided earlier (`7738501078msh629d88695c19b1bp1c4eeajsn556ca45ae6af`)
is for a third-party vendor, you'll need to consult that vendor's support to
understand its scopes; typically you'll use it in your HTTP `Authorization` header
when calling their endpoints.

For convenience a sample route `/import_jobs` has been added to `app.py` that
shows how to use the master key to fetch job data and insert it into the local
`jobs` table.  Visit that URL in a browser after logging in as admin to trigger
an import (modify the placeholder URL/parameters to match the actual API).


## Running the App

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000` in your browser.

## Chatbot Setup

1. Copy `.env.example` into `.env`.
2. Set `OPENAI_API_KEY`.
3. Run the Flask app.
4. Open `/chat` to use the chatbot with persistent session history.

## Fetching Real Job Data

The application comes with hardcoded demo jobs initially. To replace these with **real job postings**
from major tech companies:

1. **Log in as admin:**
   - Username: `himabindu`
   - Password: `hima`

2. **Navigate to `/import_jobs`** in your browser (or visit it directly).
   This endpoint uses your RapidAPI key (`7738501078msh629d88695c19b1bp1c4eeajsn556ca45ae6af`) to
   fetch real job postings from the JSearch API across Google, Microsoft, Amazon, Apple, and IBM.
   
3. The system will:
   - Fetch real job titles and descriptions from actual postings
   - Extract required skills from each listing
   - Delete old demo jobs
   - Insert new jobs with auto-generated API keys
   - Display the count of jobs imported

**Note:** If the import shows 0 jobs, your RapidAPI key may have expired or the endpoint may be
rate-limited. Check your RapidAPI dashboard or contact RapidAPI support if needed.


## Notes

- The admin dashboard and company dashboards show the generated API keys for each job.
- The login form hides the "Name" field unless the user switches to the registration mode.
- Existing accounts created with short passwords can still log in; to enforce length
  retroactively, either delete them or set a policy.
