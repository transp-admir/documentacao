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

# --- ROTAS DE UPLOAD DE VALIDADES ---

@admin_bp.route('/upload/doc_fiscal', methods=['POST'])
def upload_doc_fiscal():
    file_input_name = 'documentos-fiscal-file'
    if file_input_name not in request.files:
        flash('Nenhum arquivo fiscal enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))
    arquivo = request.files[file_input_name]
    if arquivo.filename == '':
        flash('Nenhum arquivo fiscal selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))
    try:
        df = pd.read_excel(arquivo, engine='openpyxl', dtype={'Nome': str, 'Tipo evento': str})
        df.columns = [str(col).strip().lower() for col in df.columns]

        # CORREÇÃO: Usa 'nome' como a coluna de identificação
        nome_col, doc_name_col, due_date_col = 'nome', 'tipo evento', 'data vencimento'
        
        required_cols = [nome_col, doc_name_col, due_date_col]
        if not all(col in df.columns for col in required_cols):
            flash(f'Arquivo fiscal deve conter as colunas: "Nome", "Tipo evento", "Data vencimento".', 'danger')
            return redirect(url_for('admin.upload_page'))

        df.dropna(subset=required_cols, inplace=True)

        novos, atualizados, nao_encontrados = 0, 0, set()
        for _, row in df.iterrows():
            nome_empresa, doc_name, vencimento_obj = row.get(nome_col), row.get(doc_name_col), row.get(due_date_col)

            empresa = Empresa.query.filter(Empresa.razao_social.ilike(f"%{str(nome_empresa).strip()}%")).first()
            if not empresa:
                nao_encontrados.add(str(nome_empresa))
                continue
            try:
                data_vencimento = pd.to_datetime(vencimento_obj).date()
            except (ValueError, TypeError):
                continue
                
            doc_existente = DocumentoFiscal.query.filter_by(empresa_id=empresa.id, nome_documento=str(doc_name).upper()).first()
            if doc_existente:
                if doc_existente.data_vencimento != data_vencimento:
                    doc_existente.data_vencimento = data_vencimento
                    atualizados += 1
            else:
                novo_documento = DocumentoFiscal(empresa_id=empresa.id, nome_documento=str(doc_name).upper(), data_vencimento=data_vencimento)
                db.session.add(novo_documento)
                novos += 1
                
        db.session.commit()

        if novos: flash(f'{novos} novas validades fiscais cadastradas.', 'success')
        if atualizados: flash(f'{atualizados} validades fiscais atualizadas.', 'info')
        if nao_encontrados: flash(f'Atenção: As seguintes empresas não foram encontradas: {", ".join(sorted(nao_encontrados))}', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao processar arquivo fiscal: {e}', 'danger')
        
    return redirect(url_for('admin.upload_page'))


@admin_bp.route('/upload/doc_motorista', methods=['POST'])
def upload_doc_motorista():
    if 'documentos-motorista-file' not in request.files:
        flash('Nenhum arquivo de motorista enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))
    file = request.files['documentos-motorista-file']
    if file.filename == '':
        flash('Nenhum arquivo de motorista selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))
    try:
        df = pd.read_excel(file, engine='openpyxl', dtype={'Nome': str, 'Tipo evento': str})
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        
        expected_cols = {'tipo_evento', 'nome', 'data_vencimento'}
        if not expected_cols.issubset(df.columns):
            flash(f"Arquivo de motorista deve conter: 'Tipo evento', 'Nome', 'Data vencimento'.", 'danger')
            return redirect(url_for('admin.upload_page'))

        df.dropna(subset=['tipo_evento', 'nome', 'data_vencimento'], inplace=True)

        novos, atualizados, nao_encontrados, duplicados = 0, 0, set(), set()
        for _, row in df.iterrows():
            nome_doc, nome_mot, venc_obj = row.get('tipo_evento'), row.get('nome'), row.get('data_vencimento')
            
            try:
                venc_date = pd.to_datetime(venc_obj).date()
            except (ValueError, TypeError):
                continue

            motoristas = Motorista.query.filter(Motorista.nome.ilike(str(nome_mot).strip())).all()
            if len(motoristas) == 1:
                motorista = motoristas[0]
            elif len(motoristas) > 1:
                duplicados.add(str(nome_mot).strip())
                continue
            else:
                nao_encontrados.add(str(nome_mot).strip())
                continue

            doc_existente = DocumentoMotorista.query.filter_by(
                motorista_id=motorista.id,
                nome_documento=str(nome_doc).strip().upper()
            ).first()

            if doc_existente:
                if doc_existente.data_vencimento != venc_date:
                    doc_existente.data_vencimento = venc_date
                    atualizados += 1
            else:
                novo_doc = DocumentoMotorista(
                    nome_documento=str(nome_doc).strip().upper(),
                    data_vencimento=venc_date,
                    motorista_id=motorista.id
                )
                db.session.add(novo_doc)
                novos += 1

        db.session.commit()
        
        if novos: flash(f'{novos} novas validades de motoristas cadastradas.', 'success')
        if atualizados: flash(f'{atualizados} validades de motoristas foram atualizadas.', 'info')
        if nao_encontrados: flash(f'Motoristas não encontrados: {", ".join(sorted(list(nao_encontrados)))}', 'warning')
        if duplicados: flash(f'Motoristas com nome duplicado (não processados): {", ".join(sorted(list(duplicados)))}', 'danger')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao processar arquivo de motoristas: {e}', 'danger')
        
    return redirect(url_for('admin.upload_page'))

@admin_bp.route('/upload/doc_veiculo', methods=['POST'])
def upload_doc_veiculo():
    if 'documentos-veiculo-file' not in request.files:
        flash('Nenhum arquivo de veículo enviado.', 'danger')
        return redirect(url_for('admin.upload_page'))
    file = request.files['documentos-veiculo-file']
    if file.filename == '':
        flash('Nenhum arquivo de veículo selecionado.', 'danger')
        return redirect(url_for('admin.upload_page'))
    try:
        df = pd.read_excel(file, engine='openpyxl', dtype={'Nome': str, 'Tipo evento': str})
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        df.rename(columns={'tipo_evento': 'documento', 'nome': 'placa', 'data_vencimento': 'vencimento'}, inplace=True)
        
        expected_cols = {'documento', 'placa', 'vencimento'}
        if not expected_cols.issubset(df.columns):
            flash(f"Arquivo de veículo deve conter: 'Tipo evento', 'Nome' (placa), 'Data vencimento'.", 'danger')
            return redirect(url_for('admin.upload_page'))
        
        df.dropna(subset=['documento', 'placa', 'vencimento'], inplace=True)
        
        novos, atualizados, nao_encontrados = 0, 0, set()
        for _, row in df.iterrows():
            nome_doc, placa_veic, venc_obj = row['documento'], row['placa'], row['vencimento']
            
            try:
                venc_date = pd.to_datetime(venc_obj).date()
            except (ValueError, TypeError):
                continue

            placa_limpa = str(placa_veic).strip().upper()
            veiculo = Veiculo.query.filter(Veiculo.placa.ilike(placa_limpa)).first()
            if not veiculo:
                nao_encontrados.add(placa_limpa)
                continue

            doc_existente = DocumentoVeiculo.query.filter_by(
                veiculo_id=veiculo.id,
                nome_documento=str(nome_doc).strip().upper()
            ).first()

            if doc_existente:
                if doc_existente.data_vencimento != venc_date:
                    doc_existente.data_vencimento = venc_date
                    atualizados += 1
            else:
                novo_doc = DocumentoVeiculo(
                    nome_documento=str(nome_doc).strip().upper(),
                    data_vencimento=venc_date,
                    veiculo_id=veiculo.id
                )
                db.session.add(novo_doc)
                novos += 1
            
        db.session.commit()
        
        if novos: flash(f'{novos} novas validades de veículos cadastradas.', 'success')
        if atualizados: flash(f'{atualizados} validades de veículos foram atualizadas.', 'info')
        if nao_encontrados: flash(f'Placas não encontradas: {", ".join(sorted(list(nao_encontrados)))}', 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao processar arquivo de veículos: {e}', 'danger')
        
    return redirect(url_for('admin.upload_page'))


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

    # Função interna robusta para processar documentos
    def process_docs(query, doc_type, description_format, owner_relation_name, owner_attr_name):
        # A lógica de busca pode ser adicionada aqui se necessário
        for doc in query.all():
            prazo = alert_configs.get(doc.nome_documento.upper(), default_prazo)
            due_date_limit = today + timedelta(days=prazo)

            if doc.data_vencimento <= due_date_limit:
                # 1. Pega o objeto relacionado (motorista, veiculo, empresa) de forma segura
                owner = getattr(doc, owner_relation_name, None)

                # 2. Define nomes padrão
                owner_name = 'Não Associado'
                company_name = 'Não Associado'

                # 3. Se o objeto relacionado existir, pega os nomes corretos
                if owner:
                    owner_name = getattr(owner, owner_attr_name, 'N/A')
                    if doc_type == 'Empresa':
                        company_name = owner_name
                    else:
                        company = getattr(owner, 'empresa', None)
                        company_name = company.razao_social if company else 'Sem Empresa'
                
                item_description = description_format.format(nome=doc.nome_documento, owner=owner_name)
                all_alert_items.append({
                    'item_description': item_description,
                    'item_type': doc_type,
                    'owner_name': company_name,
                    'due_date': doc.data_vencimento,
                    'days_left': (doc.data_vencimento - today).days
                })

    # Processa cada tipo de documento com a nova lógica segura
    process_docs(DocumentoFiscal.query.options(joinedload(DocumentoFiscal.empresa)), 'Empresa', '{nome}', 'empresa', 'razao_social')
    process_docs(DocumentoMotorista.query.options(joinedload(DocumentoMotorista.motorista).joinedload(Motorista.empresa)), 'Motorista', '{nome} de {owner}', 'motorista', 'nome')
    process_docs(DocumentoVeiculo.query.options(joinedload(DocumentoVeiculo.veiculo).joinedload(Veiculo.empresa)), 'Veículo', '{nome} - {owner}', 'veiculo', 'placa')

    vencidos_count = sum(1 for item in all_alert_items if item['days_left'] <= 0)
    critical_alerts_count = sum(1 for item in all_alert_items if 0 < item['days_left'] <= 7)

    display_items = all_alert_items
    if hide_vencidos:
        display_items = [item for item in display_items if item['days_left'] > 0]

    display_items.sort(key=lambda x: x['days_left'])

    return render_template('admin/adm.html',
                           alert_items=display_items,
                           vencidos_count=vencidos_count,
                           critical_alerts_count=critical_alerts_count,
                           total_list_count=len(display_items),
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
