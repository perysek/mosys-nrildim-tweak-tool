"""Authentication logic — sits between routes and UserRepository.

Login is by MOSYS employee ID only (no email login is exposed anywhere in the
UI); email exists purely as the internal Flask-Login identity key.
"""

from typing import Optional, Tuple

from app.functions.auth_repo import User, UserRepository


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def authenticate_by_employee_id(self, mosys_employee_id: str, password: str
                                     ) -> Tuple[bool, Optional[User], Optional[str]]:
        user = self.user_repo.get_by_mosys_employee_id((mosys_employee_id or '').strip())
        if not user:
            return False, None, 'Invalid employee number or password'
        if not user.is_active:
            return False, None, 'This account is inactive. Contact an administrator.'
        if not self.user_repo.verify_password(user, password):
            return False, None, 'Invalid employee number or password'
        self.user_repo.update_last_login(user.id)
        return True, user, None

    def change_password(self, user_id: int, old_password: str, new_password: str
                         ) -> Tuple[bool, Optional[str]]:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            return False, 'User does not exist'
        if not self.user_repo.verify_password(user, old_password):
            return False, 'Current password is incorrect'
        if len(new_password) < 8:
            return False, 'Password must be at least 8 characters'
        self.user_repo.update_password(user_id, new_password)
        return True, None
