import os

# Obtém o caminho absoluto do diretório do projeto.
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Configurações base para a aplicação."""
    # Chave secreta para proteger sessões e cookies. É crucial para a segurança.
    # Em produção, deve ser carregada de uma variável de ambiente.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'uma-chave-secreta-muito-dificil-de-adivinhar')
    
    # Desativa o rastreamento de modificações do SQLAlchemy para economizar recursos.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    """Configurações para o ambiente de desenvolvimento."""
    DEBUG = True
    # Define o banco de dados como um arquivo SQLite dentro do diretório do projeto.
    # Isso facilita o setup inicial sem a necessidade de um servidor de banco de dados.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')

class ProductionConfig(Config):
    """Configurações para o ambiente de produção."""
    DEBUG = False
    # Em produção, você usaria um banco de dados mais robusto como PostgreSQL ou MySQL.
    # A URL do banco de dados deve ser carregada de uma variável de ambiente.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

# Mapeamento de nomes para as classes de configuração.
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
