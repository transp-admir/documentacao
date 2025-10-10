from flask import render_template, request, redirect, url_for, flash
from datetime import datetime
from . import auth_bp

@auth_bp.route('/')
def login_page():
    """Renderiza a página de login."""
    # O Blueprint 'auth' já procura templates dentro de sua pasta 'templates'.
    # Portanto, não precisamos do prefixo 'auth/'.
    return render_template('admin_login.html', ano=datetime.now().year)

@auth_bp.route('/login', methods=['POST'])
def login():
    """Processa o formulário de login."""
    username = request.form.get('username')
    password = request.form.get('password')

    # Validação fictícia - será substituída por uma consulta ao banco de dados
    if username == 'admin' and password == 'admin':
        flash('Login realizado com sucesso!', 'success')
        # Redireciona para o dashboard principal da aplicação
        return redirect(url_for('main.index'))
    else:
        flash('Usuário ou senha inválido.', 'error')
        # Devolta para a página de login
        return redirect(url_for('auth.login_page'))
