from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, ValidationError
from wtforms.validators import DataRequired, EqualTo, Length, Regexp
from ..models import Usuario, Empresa, format_cpf, format_cnpj

# =============================================================================
# Formulário de Cadastro do Administrador Master
# =============================================================================
class RegistrationForm(FlaskForm):
    """Formulário de cadastro para o usuário administrador do sistema (Master)."""
    nome = StringField('Nome Completo', validators=[DataRequired(), Length(min=3, max=120)])
    cpf = StringField('CPF', validators=[
        DataRequired(),
        Regexp(r'^(\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{11})$', 
               message="CPF inválido. Use o formato XXX.XXX.XXX-XX ou apenas 11 dígitos.")
    ])
    login = StringField('Login', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Senha', validators=[
        DataRequired(),
        EqualTo('password2', message='As senhas devem ser iguais.'),
        Length(min=6, message="A senha deve ter pelo menos 6 caracteres.")
    ])
    password2 = PasswordField('Confirme a Senha', validators=[DataRequired()])
    grid = StringField('Grid', validators=[DataRequired(), Length(max=80)])
    operacao = StringField('Operação', validators=[DataRequired(), Length(max=80)])
    submit = SubmitField('Cadastrar')

    def validate_login(self, field):
        if Usuario.query.filter_by(login=field.data.upper()).first():
            raise ValidationError('Este login já está em uso. Por favor, escolha outro.')

    def validate_cpf(self, field):
        try:
            cpf_formatado = format_cpf(field.data)
            if Usuario.query.filter_by(cpf=cpf_formatado).first():
                raise ValidationError('Este CPF já está cadastrado em nosso sistema.')
        except ValueError as e:
            raise ValidationError(str(e))

# =============================================================================
# Formulário de Auto-Registro da Transportadora (CORRIGIDO)
# =============================================================================
class RegistroEmpresaForm(FlaskForm):
    """Formulário para a transportadora se registrar a partir de um convite."""
    # --- Dados da Empresa ---
    razao_social = StringField('Razão Social', validators=[DataRequired(), Length(max=120)])
    cnpj = StringField('CNPJ', validators=[
        DataRequired(),
        Regexp(r'^(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{14})$',
               message="CNPJ inválido. Use o formato XX.XXX.XXX/XXXX-XX ou apenas 14 dígitos.")
    ])

    # --- Dados do Usuário Administrador da Empresa ---
    nome_usuario = StringField('Seu Nome Completo', validators=[DataRequired(), Length(max=120)])
    login = StringField('Seu E-mail (será seu login)', validators=[DataRequired(), Length(max=80)])
    password = PasswordField('Crie uma Senha de Acesso', validators=[
        DataRequired(),
        EqualTo('password2', message='As senhas precisam ser iguais.'),
        Length(min=6, message="A senha deve ter no mínimo 6 caracteres.")
    ])
    password2 = PasswordField('Confirme a Senha', validators=[DataRequired()])
    submit = SubmitField('Finalizar Cadastro e Acessar o Sistema')

    # CORREÇÃO: A validação customizada de login foi removida.
    # A lógica de criação no backend agora é robusta o suficiente para lidar com isso.
    # Isso impede que o formulário falhe silenciosamente ao recarregar a página.
