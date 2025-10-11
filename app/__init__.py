from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import config

db = SQLAlchemy()
migrate = Migrate()

# Configuração do LoginManager
login_manager = LoginManager()
login_manager.login_view = 'auth.login_page' # Rota para a qual usuários não logados são redirecionados
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

# FUNÇÃO CRÍTICA QUE ESTAVA FALTANDO
@login_manager.user_loader
def load_user(user_id):
    """Define como o Flask-Login carrega um usuário a partir do ID da sessão."""
    from .models import Usuario
    return Usuario.query.get(int(user_id))

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Registro dos Blueprints
    from .auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/')

    from .main import main_bp
    app.register_blueprint(main_bp, url_prefix='/index')

    from .admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    return app
