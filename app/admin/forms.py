
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, Regexp

class EmpresaForm(FlaskForm):
    """Formulário para adicionar ou editar uma Empresa."""
    nome_fantasia = StringField(
        'Nome Fantasia',
        validators=[DataRequired(), Length(min=2, max=120)]
    )
    razao_social = StringField(
        'Razão Social',
        validators=[DataRequired(), Length(min=2, max=120)]
    )
    # Validador de CNPJ (aceita com ou sem formatação)
    cnpj = StringField(
        'CNPJ',
        validators=[
            DataRequired(),
            Regexp(r'^(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})$',
                   message="CNPJ inválido. Use o formato XX.XXX.XXX/XXXX-XX.")
        ]
    )
    status = SelectField(
        'Status',
        choices=[('ativa', 'Ativa'), ('inativa', 'Inativa')],
        validators=[DataRequired()]
    )
    submit = SubmitField('Salvar')
