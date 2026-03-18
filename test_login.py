#!/usr/bin/env python3
import sqlite3
import sys

print("=" * 60)
print("LOGIN FLOW DIAGNOSTIC TEST")
print("=" * 60)

# Test 1: Database and User Lookup
print("\n[TEST 1] Database Connection and User Lookup")
print("-" * 60)

try:
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    
    # Check if users table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cur.fetchone():
        print("✗ ERROR: users table does not exist!")
        sys.exit(1)
    
    print("✓ Users table exists")
    
    # Test query
    cur.execute("SELECT name FROM users WHERE email=? AND password=?", 
                ("chandakahimabindu6@gmail.com", "hima"))
    result = cur.fetchone()
    
    if result:
        print(f"✓ User found: {result[0]}")
        print(f"  Email: chandakahimabindu6@gmail.com")
        print(f"  Password: hima")
    else:
        print("✗ No user found with these credentials")
        # Try to list all users
        cur.execute("SELECT id, name, email FROM users")
        all_users = cur.fetchall()
        print(f"  Available users: {all_users}")
    
    conn.close()
except Exception as e:
    print(f"✗ Database error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Check auth templates
print("\n[TEST 2] Template Files")
print("-" * 60)

try:
    with open("templates/auth.html", "r") as f:
        content = f.read()
    
    checks = [
        ("authForm", "Form element"),
        ("modeInput", "Mode input field"),
        ("nameInput", "Name input field"),
        ("error", "Error display section"),
        ("method=\"post\"", "POST method"),
        ('action="/auth"', "Auth action"),
    ]
    
    for check, desc in checks:
        if check in content:
            print(f"✓ {desc}: Found")
        else:
            print(f"✗ {desc}: Missing")
    
    print(f"✓ auth.html file readable ({len(content)} bytes)")
    
except Exception as e:
    print(f"✗ Template error: {e}")

# Test 3: Check app routes
print("\n[TEST 3] App Routes")
print("-" * 60)

try:
    with open("app.py", "r") as f:
        app_content = f.read()
    
    routes_to_check = [
        ("@app.route(\"/auth\"", "/auth route"),
        ("session[\"user\"]", "Session user assignment"),
        ("redirect(\"/user_dashboard\")", "Redirect to dashboard"),
        ("@app.route(\"/user_dashboard\")", "/user_dashboard route"),
        ("render_template(\"user_dashboard.html\"", "Dashboard template rendering"),
    ]
    
    for route, desc in routes_to_check:
        if route in app_content:
            print(f"✓ {desc}: Found")
        else:
            print(f"✗ {desc}: Missing")
    
except Exception as e:
    print(f"✗ Route check error: {e}")

# Test 4: Check for app.py errors
print("\n[TEST 4] Python Syntax")
print("-" * 60)

try:
    import py_compile
    py_compile.compile("app.py", doraise=True)
    print("✓ app.py has valid Python syntax")
except py_compile.PyCompileError as e:
    print(f"✗ Syntax error in app.py: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC TEST COMPLETE")
print("=" * 60)
