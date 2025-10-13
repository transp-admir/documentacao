
# check_cnpjs.py
import os
from app import create_app, db
from app.models import Empresa

# Assume que a configuração padrão é 'development', que é o usual para scripts de manutenção
config_name = os.getenv('FLASK_CONFIG') or 'development'
app = create_app(config_name)

def consulta_empresas():
    """
    Script para consultar e exibir o CNPJ e a Razão Social de todas as empresas
    salvas no banco de dados, para fins de verificação.
    """
    with app.app_context():
        print("\n--- INICIANDO CONSULTA DE EMPRESAS (CNPJ E RAZÃO SOCIAL) ---")
        try:
            # Busca todas as empresas, ordenadas por Razão Social para facilitar a leitura
            empresas = Empresa.query.order_by(Empresa.razao_social).all()
            
            if not empresas:
                print(">>> Nenhuma empresa encontrada no banco de dados.")
            else:
                print(f">>> Total de {len(empresas)} empresas encontradas. Exibindo dados:")
                # Define um cabeçalho para a tabela
                print("-" * 80)
                print(f"{'ID':<5} | {'CNPJ':<20} | {'RAZÃO SOCIAL'}")
                print("-" * 80)
                
                # Itera sobre cada empresa e imprime os dados formatados
                for empresa in empresas:
                    print(f"{empresa.id:<5} | {empresa.cnpj:<20} | {empresa.razao_social}")
                
                print("-" * 80)

        except Exception as e:
            print(f"!!! OCORREU UM ERRO AO ACESSAR O BANCO DE DADOS: {e}")
        
        print("--- CONSULTA FINALIZADA ---\n")

if __name__ == '__main__':
    consulta_empresas()
