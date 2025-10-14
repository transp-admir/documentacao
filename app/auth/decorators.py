from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    """Garante que o usuário logado seja um administrador (master) ou um transportador (comum)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Permite o acesso se o usuário for 'master' OU 'comum'
        if not current_user.is_authenticated or getattr(current_user, 'role', None) not in ['master', 'comum']:
            flash('Acesso negado. Você não tem permissão para ver esta página.', 'danger')
            # Redireciona para a página de login, que é mais apropriada em caso de falha de permissão.
            return redirect(url_for('auth.login_page'))
            
        return f(*args, **kwargs)
    return decorated_function
