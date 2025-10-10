from flask_sqlalchemy import SQLAlchemy

# Cria uma instância do SQLAlchemy. 
# Esta instância será "conectada" à nossa aplicação Flask no momento da criação da app,
# permitindo que ela interaja com o banco de dados configurado.
db = SQLAlchemy()
