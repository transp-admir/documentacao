from flask import render_template, redirect, url_for
from datetime import datetime
from . import main_bp

@main_bp.route('/')
def home():
    """Renderiza a página principal (dashboard) para preview."""
    # Redirecionado para a página de index para facilitar o desenvolvimento do layout
    return redirect(url_for('main.index'))

@main_bp.route('/index')
def index():
    """Renderiza a página principal (dashboard)."""
    return render_template('index.html', ano=datetime.now().year)
