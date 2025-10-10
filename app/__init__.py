from flask import Flask
from config import config
from .extensions import db

def create_app(config_name='default'):
    """Application Factory: Cria e configura a instância da aplicação Flask."""
    
    app = Flask(__name__)
    
    # 1. Carrega as configurações
    app.config.from_object(config[config_name])
    
    # 2. Inicializa as extensões
    db.init_app(app)
    
    # 3. Registra os Blueprints
    # O Blueprint de autenticação
    from .auth import auth_bp as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    # O Blueprint principal da aplicação
    from .main import main_bp as main_blueprint
    app.register_blueprint(main_blueprint, url_prefix='/')

    return app
