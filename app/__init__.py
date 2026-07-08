from flask import Flask
from flask_login import LoginManager, current_user
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

from app.functions import auth_db, auth_repo
from auth_config import role_display_name

auth_db.initialize_database()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    try:
        return auth_repo.UserRepository().get_by_id(int(user_id))
    except (TypeError, ValueError):
        return None


@app.context_processor
def inject_auth_context():
    if not current_user.is_authenticated:
        return {'is_superuser': False, 'role_caption': None}
    return {
        'is_superuser': current_user.role == 'superuser',
        'role_caption': role_display_name(current_user.role),
    }


from app import spc_routes  # SPC-Tweaks page
from app import auth_routes
from app import users_routes
from app import employees_routes
from app import roles_routes