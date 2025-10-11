from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from datetime import datetime
from flask_login import login_user, logout_user, login_required
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from . import auth_bp
from ..models import db, Usuario, Empresa, format_cnpj
from .forms import RegistrationForm, RegistroEmpresaForm


@auth_bp.route('/')
def login_page():
    return render_template('auth/admin_login.html', ano=datetime.now().year)

@auth_bp.route('/login', methods=['POST'])
def login():
    login_form_data = request.form.get('username')
    password = request.form.get('password')
    user = Usuario.query.filter_by(login=login_form_data.upper()).first()
    if user and user.check_password(password) and user.is_active:
        login_user(user)
        flash('Login realizado com sucesso!', 'success')
        if user.role == 'master':
            return redirect(url_for('admin.admin_dashboard'))
        else:
            return redirect(url_for('main.index'))
    else:
        flash('Usuário ou senha inválido, ou sua conta está inativa.', 'danger')
        return redirect(url_for('auth.login_page'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso.', 'info')
    return redirect(url_for('auth.login_page'))

@auth_bp.route('/registrar/<token>', methods=['GET', 'POST'])
def registrar_por_convite(token):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    
    try:
        serializer.loads(token, max_age=3600)
    except (SignatureExpired, BadTimeSignature):
        flash('O link de registro é inválido ou expirou.', 'danger')
        return redirect(url_for('auth.login_page'))

    form = RegistroEmpresaForm()
    if form.validate_on_submit():
        try:
            cnpj_limpo = ''.join(filter(str.isdigit, form.cnpj.data))
            cnpj_formatado_para_busca = format_cnpj(cnpj_limpo)
            
            empresa_alvo = Empresa.query.filter_by(cnpj=cnpj_formatado_para_busca).first()
            
            if not empresa_alvo:
                empresa_alvo = Empresa(
                    razao_social=form.razao_social.data,
                    cnpj=cnpj_limpo 
                )
                db.session.add(empresa_alvo)

            novo_usuario = Usuario(
                nome=form.nome_usuario.data,
                login=form.login.data,
                role='comum',
                status='ativo'
            )
            novo_usuario.set_password(form.password.data)
            novo_usuario.empresa = empresa_alvo
            
            db.session.add(novo_usuario)
            db.session.commit()

            login_user(novo_usuario)
            flash('Cadastro finalizado com sucesso! Bem-vindo(a) ao sistema.', 'success')
            return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"ERRO CRÍTICO NO REGISTRO: {e}", exc_info=True)
            flash('Ocorreu um erro grave durante o cadastro. O CNPJ ou a Razão Social podem já existir. Verifique os dados e tente novamente.', 'danger')

    return render_template('auth/registrar_empresa.html', form=form, ano=datetime.now().year)

# =============================================================================
# ROTA DE CONSULTA DE CNPJ - MODIFICAÇÃO PARA DIAGNÓSTICO
# =============================================================================
@auth_bp.route('/consultar-cnpj/<cnpj>')
def consultar_cnpj(cnpj):
    # TESTE: Força a busca por um CNPJ que sabemos que existe para validar o front-end.
    # Esta é uma medida de diagnóstico temporária.
    empresa = Empresa.query.filter_by(cnpj="81.353.611/0001-15").first()

    if empresa:
        # Se encontrou a empresa hard-coded, retorna os dados dela.
        return jsonify({
            'razao_social': empresa.razao_social,
            'exists': True
        })
    else:
        # Se nem mesmo a busca hard-coded funcionou, retorna 'exists: false'.
        # Isso indicaria um problema de conexão com o banco ou com a recriação da tabela.
        return jsonify({'exists': False, 'error_message': 'Empresa de teste não encontrada no DB.'})


@auth_bp.route('/setup/master_admin', methods=['GET', 'POST'])
@login_required
def cadastro_master():
    form = RegistrationForm()
    if form.validate_on_submit():
        pass
    return render_template('auth/cadastro.html', form=form, ano=datetime.now().year)
