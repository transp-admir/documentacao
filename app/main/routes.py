from flask import render_template, redirect, url_for
from datetime import datetime
from . import main_bp

@main_bp.route('/')
def home():
    """Redireciona a rota raiz para a página de login."""
    return redirect(url_for('auth.login_page'))

@main_bp.route('/index')
def index():
    """Renderiza a página principal (dashboard)."""
    return render_template('index.html', ano=datetime.now().year)
