r"""Bootstrap the first superuser account — run once before anyone can log in.

Solves the chicken-and-egg problem: nothing in the app can create a user
until someone is already logged in as superuser. This CLI creates (or
promotes) one directly against the local auth.sqlite, reusing the same
EmployeeRepository / UserRepository code the web app uses — a green run
here means the actual login path will work too.

Usage (from the repo root, venv active)
----------------------------------------
    # Normal case — looks the employee up live via STAAMPDB.OPERATORI:
    .\venv\Scripts\python.exe scripts\seed_superuser.py --mosys-id 9001

    # MOSYS unreachable / offline testing — supply the name directly:
    .\venv\Scripts\python.exe scripts\seed_superuser.py --mosys-id 9001 --name "Jan Kowalski"

Idempotent: running it again for the same --mosys-id promotes the existing
account to superuser (or reports it already is one) — it never creates a
duplicate.
"""

import argparse
import os
import secrets
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.functions import auth_db  # noqa: E402
from app.functions.auth_repo import EmployeeRepository, UserRepository  # noqa: E402
from app.functions.mosys import fetch_operatori  # noqa: E402


def _resolve_employee(mosys_id, name_override, employee_repo):
    conn = auth_db.get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM employees WHERE mosys_employee_id = ?", (mosys_id,)
        ).fetchone()
    finally:
        conn.close()
    if existing:
        return existing

    if name_override:
        employee_repo.sync_from_mosys([{'mosys_id': mosys_id, 'full_name': name_override}])
    else:
        try:
            mosys_employees = fetch_operatori()
        except Exception as e:
            print(f"Could not reach MOSYS ({e}). Pass --name to create the employee offline.")
            sys.exit(1)
        match = next((e for e in mosys_employees if e['mosys_id'] == mosys_id), None)
        if not match:
            print(f"Employee ID {mosys_id} was not found in STAAMPDB.OPERATORI. "
                  f"Pass --name to create it manually.")
            sys.exit(1)
        employee_repo.sync_from_mosys([match])

    conn = auth_db.get_connection()
    try:
        return conn.execute(
            "SELECT * FROM employees WHERE mosys_employee_id = ?", (mosys_id,)
        ).fetchone()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mosys-id', required=True,
                         help='MOSYS employee ID (STAAMPDB.OPERATORI CODICE)')
    parser.add_argument('--name', help='Full name override — use when MOSYS is unreachable')
    args = parser.parse_args()

    auth_db.initialize_database()
    employee_repo = EmployeeRepository()
    user_repo = UserRepository()

    employee = _resolve_employee(args.mosys_id, args.name, employee_repo)

    if employee['user_id']:
        user = user_repo.get_by_id(employee['user_id'])
        if user.role == 'superuser':
            print(f"{user.full_name} (ID {args.mosys_id}) is already a superuser. Nothing to do.")
            return
        user_repo.update_user(user.id, user.full_name, 'superuser')
        print(f"Promoted {user.full_name} (ID {args.mosys_id}) to superuser.")
        return

    email = f"{args.mosys_id}@mosys.local"
    temp_password = secrets.token_urlsafe(12)  # unusable in practice — see auth_routes.first_login
    user_id = user_repo.create_user(email, temp_password, employee['full_name'],
                                     role='superuser', must_change_password=True)
    employee_repo.link_user(employee['id'], user_id)
    print(f"Created superuser {employee['full_name']} (ID {args.mosys_id}).")
    print(f"Log in at /login with employee ID {args.mosys_id} — "
          f"you'll be prompted to set a password on first login.")


if __name__ == '__main__':
    main()
