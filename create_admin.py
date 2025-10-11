from app import create_app, db
from app.models import Usuario

# Mensagem informativa sobre a finalidade do script
print("""
Este script é utilizado para criar o usuário administrador inicial (master)
necessário para gerenciar o sistema pela primeira vez.

Ele deve ser executado apenas uma vez durante a configuração inicial do ambiente.
""")

def create_master_user():
    """Cria um usuário 'master' padrão se ele não existir."""
    app = create_app()
    with app.app_context():
        # Garante que as tabelas existam antes de qualquer operação
        db.create_all()

        # Verifica se o usuário master já existe
        admin_login = 'admin'
        if Usuario.query.filter(Usuario.login.ilike(admin_login)).first():
            print(f"O usuário '{admin_login}' já existe. Nenhuma ação foi tomada.")
            return

        print(f"Criando o usuário master padrão: '{admin_login}'...")
        try:
            # Cria o usuário master sem o campo CPF
            master_user = Usuario(
                nome='ADMINISTRADOR PRINCIPAL',
                login=admin_login, 
                role='master',
                status='ativo'
            )
            master_user.set_password('179325')  # Define a senha padrão
            
            db.session.add(master_user)
            db.session.commit()
            print("Usuário master criado com sucesso!")
            print("Login: admin")
            print("Senha: 179325")

        except Exception as e:
            db.session.rollback()
            print(f"Ocorreu um erro ao criar o usuário master: {e}")

if __name__ == '__main__':
    create_master_user()
