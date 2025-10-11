import re
import datetime
from . import db
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import validates, relationship
from flask_login import UserMixin

# --- Funções Auxiliares ---

def format_cnpj(cnpj_str):
    if not isinstance(cnpj_str, str):
        return cnpj_str
    digits = re.sub(r'\D', '', cnpj_str)
    if len(digits) != 14:
        raise ValueError("CNPJ deve conter exatamente 14 dígitos.")
    return f'{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}'

def format_cpf(cpf_str):
    if not isinstance(cpf_str, str):
        return cpf_str
    digits = re.sub(r'\D', '', cpf_str)
    if len(digits) != 11:
        raise ValueError("CPF deve conter exatamente 11 dígitos.")
    return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'

def convert_to_uppercase(value):
    if isinstance(value, str):
        return value.upper()
    return value

# --- Modelo de Configuração ---

class ConfiguracaoAlerta(db.Model):
    __tablename__ = 'configuracoes_alertas'
    id = db.Column(db.Integer, primary_key=True)
    nome_documento = db.Column(db.String(120), unique=True, nullable=False)
    prazo_alerta_dias = db.Column(db.Integer, nullable=False, default=30)

    @validates('nome_documento')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)

# --- Modelos Principais ---

class Empresa(db.Model):
    __tablename__ = 'empresas'
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(120), nullable=False)
    cnpj = db.Column(db.String(18), unique=True, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='ativa')
    
    # Relações
    usuarios = relationship('Usuario', backref='empresa', lazy='dynamic')
    motoristas = relationship('Motorista', back_populates='empresa', lazy='dynamic')
    veiculos = relationship('Veiculo', back_populates='empresa', lazy='dynamic')
    documentos_fiscais = relationship('DocumentoFiscal', back_populates='empresa', lazy='dynamic', cascade="all, delete-orphan")

    @validates('cnpj')
    def validate_cnpj_format(self, key, cnpj):
        return format_cnpj(cnpj)

    @validates('razao_social')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    login = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='comum')
    status = db.Column(db.String(50), nullable=False, default='ativo')
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.status == 'ativo'

    @validates('nome', 'login')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)

class Motorista(db.Model):
    __tablename__ = 'motoristas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    cnh = db.Column(db.String(20), unique=True, nullable=True)
    operacao = db.Column(db.String(120), nullable=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)
    
    empresa = relationship('Empresa', back_populates='motoristas')
    documentos = relationship('DocumentoMotorista', back_populates='motorista', lazy='dynamic', cascade="all, delete-orphan")

    @validates('nome', 'operacao')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)
    
    @validates('cpf')
    def validate_cpf_format(self, key, cpf):
        return format_cpf(cpf)

class Veiculo(db.Model):
    __tablename__ = 'veiculos'
    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(10), unique=True, nullable=False)
    operacao = db.Column(db.String(120), nullable=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)

    empresa = relationship('Empresa', back_populates='veiculos')
    documentos = relationship('DocumentoVeiculo', back_populates='veiculo', lazy='dynamic', cascade="all, delete-orphan")

    @validates('placa', 'operacao')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)

# --- Modelos para Documentos / Validades ---

class DocumentoFiscal(db.Model):
    __tablename__ = 'documentos_fiscais'
    id = db.Column(db.Integer, primary_key=True)
    nome_documento = db.Column(db.String(120), nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresas.id'), nullable=False)

    empresa = relationship('Empresa', back_populates='documentos_fiscais')

    __table_args__ = (db.UniqueConstraint('empresa_id', 'nome_documento', name='_empresa_docfiscal_uc'),)

    @validates('nome_documento')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)

class DocumentoMotorista(db.Model):
    __tablename__ = 'documentos_motoristas'
    id = db.Column(db.Integer, primary_key=True)
    nome_documento = db.Column(db.String(120), nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    motorista_id = db.Column(db.Integer, db.ForeignKey('motoristas.id'), nullable=False)

    motorista = relationship('Motorista', back_populates='documentos')

    __table_args__ = (db.UniqueConstraint('motorista_id', 'nome_documento', name='_motorista_documento_uc'),)

    @validates('nome_documento')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)

class DocumentoVeiculo(db.Model):
    __tablename__ = 'documentos_veiculos'
    id = db.Column(db.Integer, primary_key=True)
    nome_documento = db.Column(db.String(120), nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('veiculos.id'), nullable=False)

    veiculo = relationship('Veiculo', back_populates='documentos')

    __table_args__ = (db.UniqueConstraint('veiculo_id', 'nome_documento', name='_veiculo_documento_uc'),)

    @validates('nome_documento')
    def validate_uppercase(self, key, value):
        return convert_to_uppercase(value)
