from flask import render_template, redirect, url_for, flash, current_app, request
from . import admin_bp
from ..auth.decorators import admin_required
from itsdangerous import URLSafeTimedSerializer
import re
from datetime import date, timedelta
from sqlalchemy.orm import joinedload
from sqlalchemy import distinct

# Imports para a nova funcionalidade de upload
import pandas as pd
from datetime import datetime
from .. import db
from ..models import (Empresa, DocumentoFiscal, Motorista, Veiculo, DocumentoMotorista, 
DocumentoVeiculo, ConfiguracaoAlerta, format_cnpj, format_cpf)

# Aplica o decorador a TODAS as rotas deste blueprint
@admin_bp.before_request
@admin_required
def require_admin_access():
    pass

# --- ROTAS DE GERENCIAMENTO ---

@admin_bp.route('/empresas')
def gerenciar_empresas():
    # Ordena as empresas pelo nome para melhor visualização
    todas_empresas = Empresa.query.order_by(Empresa.razao_social).all()
    return render_template('admin/gerenciar_empresas.html', empresas=todas_empresas)

@admin_bp.route('/motoristas')
def gerenciar_motoristas():
    # Usar 'options' com 'joinedload' para otimizar a busca, evitando múltiplas queries para buscar a empresa de cada motorista.
    todos_motoristas = Motorista.query.options(db.joinedload(Motorista.empresa)).order_by(Motorista.nome).all()
    return render_template('admin/gerenciar_motoristas.html', motoristas=todos_motoristas)

@admin_bp.route('/veiculos')
def gerenciar_veiculos():
    # Otimização similar para veículos, carregando a empresa associada.
    todos_veiculos = Veiculo.query.options(db.joinedload(Veiculo.empresa)).order_by(Veiculo.placa).all()
    return render_template('admin/gerenciar_veiculos.html', veiculos=todos_veiculos)

# --- Rota da página de Upload ---
@admin_bp.route('/upload_page')
def upload_page():
    return render_template('admin/upload_documentos.html')

# --- Geração de Link de Registro ---
@admin_bp.route('/convites/gerar')
def gerar_convite():
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = serializer.dumps('register-user')
    link_convite = url_for('auth.registrar_por_convite', token=token, _external=True)
    flash('Novo link de registro gerado com sucesso! Válido por 1 hora.', 'success')
    return render_template('admin/exibir_convite.html', link_convite=link_convite)


# --- BLOCO 1: ROTAS DE CADASTRO EM MASSA (COM CORREÇÃO DE ENCODING) ---

@admin_bp.route('/upload/empresas', methods=['POST'])
def upload_empresas():
    if 'arquivo' not in request.files:
        flash('Nenhum arquivo foi enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    arquivo = request.files['arquivo']
    if arquivo.filename == '':
        flash('Nenhum arquivo foi selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    extensao = arquivo.filename.rsplit('.', 1)[1].lower()
    if extensao not in ['csv', 'xlsx', 'xls']:
        flash('Formato de arquivo inválido. Por favor, envie um arquivo .csv, .xls ou .xlsx', 'danger')
        return redirect(url_for('admin.upload_page'))

    try:
        if extensao == 'csv':
            df = pd.read_csv(arquivo.stream, dtype=str, encoding='latin-1')
        else:
            df = pd.read_excel(arquivo.stream, dtype=str)

        df.columns = [str(col).strip().lower() for col in df.columns]
        colunas_esperadas = ['razao_social', 'cnpj']

        if not all(col in df.columns for col in colunas_esperadas):
            flash(f'O arquivo para empresas deve conter as colunas: {", ".join(colunas_esperadas)}', 'danger')
            return redirect(url_for('admin.upload_page'))

        novas_empresas = 0
        for _, row in df.iterrows():
            cnpj = row.get('cnpj')
            razao_social = row.get('razao_social')

            if pd.isna(cnpj) or pd.isna(razao_social):
                continue

            cnpj_limpo = re.sub(r'[^0-9]', '', str(cnpj))
            if len(cnpj_limpo) != 14:
                continue

            empresa_existente = Empresa.query.filter_by(cnpj=format_cnpj(cnpj_limpo)).first()

            if not empresa_existente:
                nova_empresa = Empresa(
                    razao_social=str(razao_social).upper(),
                    cnpj=cnpj_limpo
                )
                db.session.add(nova_empresa)
                novas_empresas += 1
        
        if novas_empresas > 0:
            db.session.commit()
            flash(f'{novas_empresas} novas empresas foram cadastradas com sucesso!', 'success')
        else:
            flash('Nenhuma nova empresa para cadastrar. Os CNPJs enviados já podem existir no sistema.', 'info')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao processar o arquivo de empresas: {e}', 'danger')

    return redirect(url_for('admin.upload_page'))

@admin_bp.route('/upload/motoristas', methods=['POST'])
def upload_motoristas():
    if 'arquivo' not in request.files:
        flash('Nenhum arquivo foi enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    arquivo = request.files['arquivo']
    if arquivo.filename == '':
        flash('Nenhum arquivo foi selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    extensao = arquivo.filename.rsplit('.', 1)[1].lower()
    if extensao not in ['csv', 'xlsx', 'xls']:
        flash('Formato de arquivo inválido.', 'danger')
        return redirect(url_for('admin.upload_page'))

    try:
        if extensao == 'csv':
            df = pd.read_csv(arquivo.stream, dtype=str, encoding='latin-1')
        else:
            df = pd.read_excel(arquivo.stream, dtype=str)

        df.columns = [str(col).strip().lower() for col in df.columns]
        colunas_esperadas = ['nome', 'cpf', 'cnpj_transportador']

        if not all(col in df.columns for col in colunas_esperadas):
            flash(f'O arquivo para motoristas deve conter as colunas: {", ".join(colunas_esperadas)}', 'danger')
            return redirect(url_for('admin.upload_page'))

        novos_motoristas = 0
        empresas_nao_encontradas = set()

        for _, row in df.iterrows():
            nome = row.get('nome')
            cpf = row.get('cpf')
            cnpj_transportador = row.get('cnpj_transportador')
            cnh = row.get('cnh')
            operacao = row.get('operacao')

            if pd.isna(nome) or pd.isna(cpf) or pd.isna(cnpj_transportador):
                continue

            cnpj_limpo = re.sub(r'[^0-9]', '', str(cnpj_transportador))
            if len(cnpj_limpo) != 14:
                continue

            empresa = Empresa.query.filter_by(cnpj=format_cnpj(cnpj_limpo)).first()

            if not empresa:
                empresas_nao_encontradas.add(cnpj_transportador)
                continue

            cpf_limpo = re.sub(r'[^0-9]', '', str(cpf))
            if len(cpf_limpo) != 11:
                continue

            motorista_existente = Motorista.query.filter_by(cpf=format_cpf(cpf_limpo)).first()

            if not motorista_existente:
                novo_motorista = Motorista(
                    nome=str(nome).upper(),
                    cpf=cpf_limpo,
                    cnh=str(cnh) if pd.notna(cnh) else None,
                    operacao=str(operacao).upper() if pd.notna(operacao) else None,
                    empresa_id=empresa.id
                )
                db.session.add(novo_motorista)
                novos_motoristas += 1
        
        if novos_motoristas > 0:
            db.session.commit()
            flash(f'{novos_motoristas} novos motoristas foram cadastrados com sucesso!', 'success')
        else:
            flash('Nenhum novo motorista para cadastrar. Os CPFs enviados já podem existir no sistema.', 'info')

        if empresas_nao_encontradas:
            flash(f'Atenção: As seguintes empresas (CNPJ) não foram encontradas: {", ".join(empresas_nao_encontradas)}', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao processar o arquivo de motoristas: {e}', 'danger')

    return redirect(url_for('admin.upload_page'))

@admin_bp.route('/upload/veiculos', methods=['POST'])
def upload_veiculos():
    if 'arquivo' not in request.files:
        flash('Nenhum arquivo foi enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    arquivo = request.files['arquivo']
    if arquivo.filename == '':
        flash('Nenhum arquivo foi selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    extensao = arquivo.filename.rsplit('.', 1)[1].lower()
    if extensao not in ['csv', 'xlsx', 'xls']:
        flash('Formato de arquivo inválido.', 'danger')
        return redirect(url_for('admin.upload_page'))

    try:
        if extensao == 'csv':
            df = pd.read_csv(arquivo.stream, dtype=str, encoding='latin-1')
        else:
            df = pd.read_excel(arquivo.stream, dtype=str)

        df.columns = [str(col).strip().lower() for col in df.columns]
        colunas_esperadas = ['placa', 'cnpj_transportador']

        if not all(col in df.columns for col in colunas_esperadas):
            flash(f'O arquivo para veículos deve conter as colunas: {", ".join(colunas_esperadas)}', 'danger')
            return redirect(url_for('admin.upload_page'))

        novos_veiculos = 0
        empresas_nao_encontradas = set()

        for _, row in df.iterrows():
            placa = row.get('placa')
            cnpj_transportador = row.get('cnpj_transportador')
            operacao = row.get('operacao')

            if pd.isna(placa) or pd.isna(cnpj_transportador):
                continue

            cnpj_limpo = re.sub(r'[^0-9]', '', str(cnpj_transportador))
            if len(cnpj_limpo) != 14:
                continue

            empresa = Empresa.query.filter_by(cnpj=format_cnpj(cnpj_limpo)).first()

            if not empresa:
                empresas_nao_encontradas.add(cnpj_transportador)
                continue
            
            placa_upper = str(placa).upper()
            veiculo_existente = Veiculo.query.filter_by(placa=placa_upper).first()

            if not veiculo_existente:
                novo_veiculo = Veiculo(
                    placa=placa_upper,
                    operacao=str(operacao).upper() if pd.notna(operacao) else None,
                    empresa_id=empresa.id
                )
                db.session.add(novo_veiculo)
                novos_veiculos += 1
        
        if novos_veiculos > 0:
            db.session.commit()
            flash(f'{novos_veiculos} novos veículos foram cadastrados com sucesso!', 'success')
        else:
            flash('Nenhum novo veículo para cadastrar. As placas enviadas já podem existir no sistema.', 'info')

        if empresas_nao_encontradas:
            flash(f'Atenção: As seguintes empresas (CNPJ) não foram encontradas: {", ".join(empresas_nao_encontradas)}', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao processar o arquivo de veículos: {e}', 'danger')

    return redirect(url_for('admin.upload_page'))


# --- BLOCO 2: ROTAS DE VALIDADE DE DOCUMENTOS (COM CORREÇÃO DE ENCODING) ---

def process_document_validity(df, id_col, id_type_name, model, find_entity_func, entity_fk_name):
    novos, atualizados, nao_encontrados = 0, 0, set()

    for _, row in df.iterrows():
        entity_identifier = row.get(id_col)
        doc_name = row.get('nome_documento')
        vencimento_str = row.get('data_vencimento')

        if pd.isna(entity_identifier) or pd.isna(doc_name) or pd.isna(vencimento_str):
            continue

        entity = find_entity_func(entity_identifier)
        if not entity:
            nao_encontrados.add(str(entity_identifier))
            continue

        try:
            data_vencimento = pd.to_datetime(vencimento_str, dayfirst=True, errors='coerce').date()
            if pd.isna(data_vencimento):
                continue
        except (ValueError, TypeError):
            continue

        documento_existente = model.query.filter(
            getattr(model, entity_fk_name) == entity.id,
            model.nome_documento == str(doc_name).upper()
        ).first()

        if documento_existente:
            if documento_existente.data_vencimento != data_vencimento:
                documento_existente.data_vencimento = data_vencimento
                atualizados += 1
        else:
            novo_documento = model(**{
                entity_fk_name: entity.id,
                'nome_documento': str(doc_name).upper(),
                'data_vencimento': data_vencimento
            })
            db.session.add(novo_documento)
            novos += 1
            
    if novos > 0:
        flash(f'{novos} novas validades de documentos foram cadastradas.', 'success')
    if atualizados > 0:
        flash(f'{atualizados} validades de documentos foram atualizadas.', 'success')
    if not novos and not atualizados:
        flash('Nenhum documento novo ou atualização necessária com base no arquivo enviado.', 'info')
    if nao_encontrados:
        flash(f'Atenção: Os seguintes {id_type_name} não foram encontrados: {", ".join(nao_encontrados)}', 'warning')

def handle_upload_and_process(required_cols, process_func):
    if 'arquivo' not in request.files:
        flash('Nenhum arquivo foi enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))
    
    arquivo = request.files['arquivo']
    if arquivo.filename == '':
        flash('Nenhum arquivo foi selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    extensao = arquivo.filename.rsplit('.', 1)[1].lower()
    if extensao not in ['csv', 'xlsx', 'xls']:
        flash('Formato de arquivo inválido. Use .csv, .xls ou .xlsx', 'danger')
        return redirect(url_for('admin.upload_page'))
        
    try:
        if extensao == 'csv':
            df = pd.read_csv(arquivo.stream, dtype=str, encoding='latin-1')
        else:
            df = pd.read_excel(arquivo.stream, dtype=str)
        
        df.columns = [str(col).strip().lower() for col in df.columns]

        if not all(col in df.columns for col in required_cols):
            flash(f'O arquivo deve conter as colunas: {", ".join(required_cols)}', 'danger')
            return redirect(url_for('admin.upload_page'))
        
        process_func(df)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao processar o arquivo: {e}', 'danger')

    return redirect(url_for('admin.upload_page'))

# --- Rota corrigida para Upload de Documento Fiscal ---
@admin_bp.route('/upload/doc_fiscal', methods=['POST'])
def upload_doc_fiscal():
    required_cols = ['nome', 'tipo evento', 'data vencimento']
    id_col_in_file = 'nome'
    doc_name_col = 'tipo evento'
    due_date_col = 'data vencimento'

    if 'arquivo' not in request.files:
        flash('Nenhum arquivo foi enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    arquivo = request.files['arquivo']
    if arquivo.filename == '':
        flash('Nenhum arquivo foi selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))

    extensao = arquivo.filename.rsplit('.', 1)[1].lower()
    if extensao not in ['csv', 'xlsx', 'xls']:
        flash('Formato de arquivo inválido. Use .csv, .xls ou .xlsx', 'danger')
        return redirect(url_for('admin.upload_page'))

    try:
        if extensao == 'csv':
            df = pd.read_csv(arquivo.stream, dtype=str, encoding='latin-1')
        else:
            df = pd.read_excel(arquivo.stream, dtype=str)

        df.columns = [str(col).strip().lower() for col in df.columns]

        if not all(col in df.columns for col in required_cols):
            flash(f'O arquivo deve conter as colunas: {", ".join(required_cols)}', 'danger')
            return redirect(url_for('admin.upload_page'))

        novos, atualizados, nao_encontrados = 0, 0, set()

        for _, row in df.iterrows():
            razao_social = row.get(id_col_in_file)
            doc_name = row.get(doc_name_col)
            vencimento_str = row.get(due_date_col)

            if pd.isna(razao_social) or pd.isna(doc_name) or pd.isna(vencimento_str):
                continue

            empresa = Empresa.query.filter(Empresa.razao_social.ilike(f"%{str(razao_social).strip()}%")).first()

            if not empresa:
                nao_encontrados.add(str(razao_social))
                continue

            try:
                data_vencimento = pd.to_datetime(vencimento_str, dayfirst=True, errors='coerce').date()
                if pd.isna(data_vencimento):
                    continue
            except (ValueError, TypeError):
                continue

            documento_existente = DocumentoFiscal.query.filter_by(
                empresa_id=empresa.id,
                nome_documento=str(doc_name).upper()
            ).first()

            if documento_existente:
                if documento_existente.data_vencimento != data_vencimento:
                    documento_existente.data_vencimento = data_vencimento
                    atualizados += 1
            else:
                novo_documento = DocumentoFiscal(
                    empresa_id=empresa.id,
                    nome_documento=str(doc_name).upper(),
                    data_vencimento=data_vencimento
                )
                db.session.add(novo_documento)
                novos += 1

        db.session.commit()

        if novos > 0:
            flash(f'{novos} novas validades de documentos fiscais foram cadastradas.', 'success')
        if atualizados > 0:
            flash(f'{atualizados} validades de documentos fiscais foram atualizadas.', 'success')
        if not novos and not atualizados:
            flash('Nenhum documento novo ou atualização necessária com base no arquivo enviado.', 'info')
        if nao_encontrados:
            flash(f'Atenção: As seguintes empresas (Razão Social) não foram encontradas: {", ".join(nao_encontrados)}', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro inesperado ao processar o arquivo: {e}', 'danger')

    return redirect(url_for('admin.upload_page'))


@admin_bp.route('/upload/doc_motorista', methods=['POST'])
def upload_doc_motorista():
    required = ['cpf_motorista', 'nome_documento', 'data_vencimento']
    def process(df):
        find_motorista = lambda cpf: Motorista.query.filter_by(cpf=format_cpf(re.sub(r'\D', '', str(cpf)))).first()
        process_document_validity(df, 'cpf_motorista', 'CPFs', DocumentoMotorista, find_motorista, 'motorista_id')
    return handle_upload_and_process(required, process)

@admin_bp.route('/upload/doc_veiculo', methods=['POST'])
def upload_doc_veiculo():
    required = ['placa_veiculo', 'nome_documento', 'data_vencimento']
    def process(df):
        find_veiculo = lambda placa: Veiculo.query.filter_by(placa=str(placa).upper()).first()
        process_document_validity(df, 'placa_veiculo', 'Placas', DocumentoVeiculo, find_veiculo, 'veiculo_id')
    return handle_upload_and_process(required, process)


# --- ROTA DO PAINEL PRINCIPAL (DASHBOARD) ---

@admin_bp.route('/')
def admin_dashboard():
    today = date.today()
    search_term = request.args.get('q', '').strip()
    hide_vencidos = request.args.get('hide_vencidos', 'false').lower() == 'true'

    configs = ConfiguracaoAlerta.query.all()
    alert_configs = {config.nome_documento: config.prazo_alerta_dias for config in configs}
    default_prazo = 30

    all_alert_items = []

    # Funções para buscar e processar documentos
    def process_docs(query, type, description_format):
        if search_term:
            if type == 'Empresa':
                query = query.join(Empresa).filter(Empresa.razao_social.ilike(f"%{search_term}%"))
            else:
                OwnerModel = Motorista if type == 'Motorista' else Veiculo
                query = query.join(OwnerModel).join(Empresa).filter(Empresa.razao_social.ilike(f"%{search_term}%"))
        
        for doc in query.all():
            prazo = alert_configs.get(doc.nome_documento, default_prazo)
            due_date_limit = today + timedelta(days=prazo)
            if doc.data_vencimento <= due_date_limit:
                owner_name = ''
                if type == 'Empresa':
                    owner_name = doc.empresa.razao_social
                    item_description = description_format.format(nome=doc.nome_documento)
                elif type == 'Motorista':
                    owner_name = doc.motorista.empresa.razao_social
                    item_description = description_format.format(nome=doc.nome_documento, owner=doc.motorista.nome.split()[0])
                elif type == 'Veículo':
                    owner_name = doc.veiculo.empresa.razao_social
                    item_description = description_format.format(nome=doc.nome_documento, owner=doc.veiculo.placa)

                all_alert_items.append({
                    'item_description': item_description,
                    'item_type': type,
                    'owner_name': owner_name,
                    'due_date': doc.data_vencimento,
                    'days_left': (doc.data_vencimento - today).days
                })

    # Processa todos os tipos de documentos
    process_docs(DocumentoFiscal.query.options(joinedload(DocumentoFiscal.empresa)), 'Empresa', '{nome}')
    process_docs(DocumentoMotorista.query.options(joinedload(DocumentoMotorista.motorista).joinedload(Motorista.empresa)), 'Motorista', '{nome} de {owner}')
    process_docs(DocumentoVeiculo.query.options(joinedload(DocumentoVeiculo.veiculo).joinedload(Veiculo.empresa)), 'Veículo', '{nome} - {owner}')

    # Calcula as contagens ANTES de qualquer filtro de visualização
    vencidos_count = sum(1 for item in all_alert_items if item['days_left'] <= 0)
    critical_alerts_count = sum(1 for item in all_alert_items if 0 < item['days_left'] <= 7)

    # Agora, aplica o filtro de visualização para a tabela
    display_items = all_alert_items
    if hide_vencidos:
        display_items = [item for item in display_items if item['days_left'] > 0]

    display_items.sort(key=lambda x: x['days_left'])

    return render_template('admin/adm.html',
                           alert_items=display_items,
                           vencidos_count=vencidos_count, # Novo contador
                           critical_alerts_count=critical_alerts_count, # Contador corrigido
                           total_list_count=len(display_items), # Contador para o card de total
                           search_term=search_term,
                           hide_vencidos=hide_vencidos)



@admin_bp.route('/configuracoes', methods=['GET'])
def gerenciar_configuracoes():
    # Coleta todos os nomes de documentos únicos de todas as tabelas de documentos
    doc_fiscais = db.session.query(distinct(DocumentoFiscal.nome_documento)).all()
    doc_motoristas = db.session.query(distinct(DocumentoMotorista.nome_documento)).all()
    doc_veiculos = db.session.query(distinct(DocumentoVeiculo.nome_documento)).all()

    # Unifica e formata a lista de tipos de documento
    all_doc_types = sorted(list(set([item[0] for item in doc_fiscais + doc_motoristas + doc_veiculos])))

    # Busca as configurações existentes
    configs = ConfiguracaoAlerta.query.all()
    configs_dict = {config.nome_documento: config.prazo_alerta_dias for config in configs}

    # Monta o dicionário final para o template, garantindo que todos os tipos de documento tenham uma entrada
    # Se uma configuração não existir, usa o default do modelo (30 dias)
    final_configs = {doc_type: configs_dict.get(doc_type, 30) for doc_type in all_doc_types}
    
    return render_template('admin/configuracoes.html', configuracoes=final_configs)

@admin_bp.route('/configuracoes/salvar', methods=['POST'])
def salvar_configuracoes():
    try:
        for key, value in request.form.items():
            if key.startswith('prazo_'):
                doc_name = key.replace('prazo_', '')
                prazo_dias = int(value)

                config = ConfiguracaoAlerta.query.filter_by(nome_documento=doc_name).first()
                if config:
                    config.prazo_alerta_dias = prazo_dias
                else:
                    nova_config = ConfiguracaoAlerta(nome_documento=doc_name, prazo_alerta_dias=prazo_dias)
                    db.session.add(nova_config)
        
        db.session.commit()
        flash('Configurações de alerta salvas com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao salvar as configurações: {e}', 'danger')

    return redirect(url_for('admin.gerenciar_configuracoes'))
