from flask import render_template, redirect, url_for, flash, current_app, request
from . import admin_bp
from ..auth.decorators import admin_required
from itsdangerous import URLSafeTimedSerializer
import re
from datetime import date, timedelta
from sqlalchemy.orm import joinedload
from sqlalchemy import distinct
from sqlalchemy import or_, func, literal_column
import re


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




@admin_bp.route('/empresa/<int:empresa_id>/toggle_status', methods=['POST'])
@admin_required
def toggle_empresa_status(empresa_id):
    """
    Ativa ou desativa uma empresa transportadora.
    """
    empresa = Empresa.query.get_or_404(empresa_id)
    empresa.ativo = not empresa.ativo
    db.session.commit()
    
    status = "ativada" if empresa.ativo else "desativada"
    flash(f'A empresa "{empresa.razao_social}" foi {status} com sucesso.', 'success')
    
    return redirect(url_for('admin.gerenciar_empresas'))


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
        cnpjs_ignorados = set()
        razoes_ignoradas = set()

        for _, row in df.iterrows():
            cnpj = row.get('cnpj')
            razao_social = row.get('razao_social')

            if pd.isna(cnpj) or pd.isna(razao_social):
                continue

            cnpj_limpo = re.sub(r'[^0-9]', '', str(cnpj))
            if len(cnpj_limpo) != 14:
                continue
            
            razao_social_upper = str(razao_social).strip().upper()
            cnpj_formatado = format_cnpj(cnpj_limpo)

            # Verifica se o CNPJ ou a Razão Social já existem
            empresa_por_cnpj = Empresa.query.filter_by(cnpj=cnpj_formatado).first()
            empresa_por_razao = Empresa.query.filter_by(razao_social=razao_social_upper).first()

            if empresa_por_cnpj:
                cnpjs_ignorados.add(f"{razao_social_upper} ({cnpj_formatado})")
                continue
            
            if empresa_por_razao:
                razoes_ignoradas.add(f"{razao_social_upper} ({cnpj_formatado})")
                continue

            # Se nenhum existir, cria a nova empresa
            nova_empresa = Empresa(
                razao_social=razao_social_upper,
                cnpj=cnpj_limpo
            )
            db.session.add(nova_empresa)
            novas_empresas += 1
        
        if novas_empresas > 0:
            db.session.commit()
            flash(f'{novas_empresas} novas empresas foram cadastradas com sucesso!', 'success')
        else:
            flash('Nenhuma nova empresa para cadastrar.', 'info')

        # Informa sobre as duplicatas ignoradas
        if cnpjs_ignorados:
            flash(f'<b>CNPJs já existentes (ignorados):</b><br>' + '<br>'.join(sorted(list(cnpjs_ignorados))), 'warning')
        if razoes_ignoradas:
            flash(f'<b>Razões Sociais já existentes (ignoradas):</b><br>' + '<br>'.join(sorted(list(razoes_ignoradas))), 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro inesperado ao processar o arquivo: {e}', 'danger')

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
    """
    Painel principal (Dashboard) que exibe um resumo dos vencimentos de documentos,
    respeitando e aplicando corretamente os prazos de alerta configurados pelo usuário.
    """
    today = date.today()
    
    entidade_filter = request.args.get('entidade', '')
    empresa_id_filter = request.args.get('empresa_id', '')
    status_filter = request.args.get('status', '')
    search_query = request.args.get('q', '').strip()
    hide_expired = request.args.get('hide_expired', 'false').lower() == 'true'

    configs = ConfiguracaoAlerta.query.all()
    configs_dict = {config.nome_documento.upper(): config.prazo_alerta_dias for config in configs}
    default_prazo = 30
    # **CORREÇÃO: 'CVVTR' foi adicionado à lista para consistência**
    known_generic_types = ['CVVTR', 'CIV', 'CIPP', 'CRLV', 'ANTT', 'CNH', 'ASO', 'ALVARÁ', 'LICENCIAMENTO']

    queries = []
    q_motoristas = db.session.query(literal_column("'Motorista'").label('type'), Motorista.nome.label('name'), DocumentoMotorista.nome_documento.label('document_type'), Empresa.razao_social.label('empresa_name'), DocumentoMotorista.data_vencimento.label('due_date'), Motorista.id.label('owner_id'), Empresa.id.label('empresa_id')).join(Motorista, DocumentoMotorista.motorista_id == Motorista.id).join(Empresa, Motorista.empresa_id == Empresa.id)
    q_veiculos = db.session.query(literal_column("'Veículo'").label('type'), Veiculo.placa.label('name'), DocumentoVeiculo.nome_documento.label('document_type'), Empresa.razao_social.label('empresa_name'), DocumentoVeiculo.data_vencimento.label('due_date'), Veiculo.id.label('owner_id'), Empresa.id.label('empresa_id')).join(Veiculo, DocumentoVeiculo.veiculo_id == Veiculo.id).join(Empresa, Veiculo.empresa_id == Empresa.id)
    q_empresas = db.session.query(literal_column("'Empresa'").label('type'), Empresa.razao_social.label('name'), DocumentoFiscal.nome_documento.label('document_type'), Empresa.razao_social.label('empresa_name'), DocumentoFiscal.data_vencimento.label('due_date'), Empresa.id.label('owner_id'), Empresa.id.label('empresa_id')).join(Empresa, DocumentoFiscal.empresa_id == Empresa.id)

    if not entidade_filter or entidade_filter == 'motorista': queries.append(q_motoristas)
    if not entidade_filter or entidade_filter == 'veiculo': queries.append(q_veiculos)
    if not entidade_filter or entidade_filter == 'empresa': queries.append(q_empresas)

    final_items = []
    if queries:
        unioned_query = queries[0].union_all(*queries[1:])
        subquery = unioned_query.subquery()
        query_to_filter = db.session.query(subquery)

        if empresa_id_filter:
            query_to_filter = query_to_filter.filter(subquery.c.empresa_id == empresa_id_filter)
        if search_query:
            search_term = f"%{search_query}%"
            query_to_filter = query_to_filter.filter(or_(subquery.c.name.ilike(search_term), subquery.c.document_type.ilike(search_term)))
        
        all_results = query_to_filter.all()

        for row in all_results:
            doc_name_upper = str(row.document_type).upper()
            prazo_alerta = default_prazo
            
            found_generic = False
            for generic_type in known_generic_types:
                type_to_check = 'ALVARA' if generic_type == 'ALVARÁ' else generic_type
                if type_to_check in doc_name_upper:
                    prazo_alerta = configs_dict.get(generic_type, default_prazo)
                    found_generic = True
                    break
            
            if not found_generic:
                cleaned_name_for_logic = re.sub(r'[\s\d.-]+$', '', doc_name_upper.replace('DOCUMENTO', '').strip()).strip()
                if cleaned_name_for_logic in configs_dict:
                    prazo_alerta = configs_dict.get(cleaned_name_for_logic, default_prazo)

            days_left = (row.due_date - today).days
            
            current_status = 'ok'
            if days_left < 0:
                current_status = 'vencido'
            elif days_left <= prazo_alerta:
                current_status = 'vencendo'
            
            if not status_filter and current_status == 'ok':
                continue
            if status_filter and current_status != status_filter:
                continue
            if hide_expired and current_status == 'vencido':
                continue

            cleaned_doc_display_name = str(row.document_type)
            cleaned_doc_display_name = re.sub(r'\s*(NAME|DTYPE):.*', '', cleaned_doc_display_name, flags=re.IGNORECASE).strip()
            cleaned_doc_display_name = re.sub(r'DOCUMENTO', '', cleaned_doc_display_name, flags=re.IGNORECASE).strip()
            cleaned_doc_display_name = re.sub(r'\s+', ' ', cleaned_doc_display_name).strip().upper()

            url = url_for('admin.gerenciar_empresas')
            if row.type == 'Motorista': url = url_for('admin.gerenciar_motoristas')
            elif row.type == 'Veículo': url = url_for('admin.gerenciar_veiculos')

            final_items.append({
                'type': row.type, 'name': row.name, 'document_type': cleaned_doc_display_name,
                'empresa_name': row.empresa_name, 'due_date': row.due_date,
                'days_left': days_left, 'url': url,
                'status': current_status
            })
        
        final_items.sort(key=lambda x: x['days_left'])

    t_plus_30 = today + timedelta(days=30)
    counts = {
        'vencidos': (db.session.query(func.count(DocumentoMotorista.id)).filter(DocumentoMotorista.data_vencimento < today).scalar() + db.session.query(func.count(DocumentoVeiculo.id)).filter(DocumentoVeiculo.data_vencimento < today).scalar() + db.session.query(func.count(DocumentoFiscal.id)).filter(DocumentoFiscal.data_vencimento < today).scalar()),
        'vencendo_30d': (db.session.query(func.count(DocumentoMotorista.id)).filter(DocumentoMotorista.data_vencimento.between(today, t_plus_30)).scalar() + db.session.query(func.count(DocumentoVeiculo.id)).filter(DocumentoVeiculo.data_vencimento.between(today, t_plus_30)).scalar() + db.session.query(func.count(DocumentoFiscal.id)).filter(DocumentoFiscal.data_vencimento.between(today, t_plus_30)).scalar()),
        'empresas': db.session.query(func.count(Empresa.id)).scalar(),
        'motoristas': db.session.query(func.count(Motorista.id)).scalar()
    }
    todas_empresas = Empresa.query.order_by(Empresa.razao_social).all()
    
    return render_template('admin/adm.html', items=final_items, counts=counts, empresas=todas_empresas, hide_expired=hide_expired, request=request)



@admin_bp.route('/configuracoes', methods=['GET'])
def gerenciar_configuracoes():
    """
    Exibe a página de configurações, agrupando todos os documentos por tipos genéricos
    e limpando os nomes para facilitar a configuração dos prazos de alerta.
    """
    doc_fiscais = db.session.query(distinct(DocumentoFiscal.nome_documento)).all()
    doc_motoristas = db.session.query(distinct(DocumentoMotorista.nome_documento)).all()
    doc_veiculos = db.session.query(distinct(DocumentoVeiculo.nome_documento)).all()

    raw_doc_names = [item[0] for item in doc_fiscais + doc_motoristas + doc_veiculos if item and item[0]]

    # **CORREÇÃO: 'CVVTR' foi adicionado à lista**
    known_generic_types = ['CVVTR', 'CIV', 'CIPP', 'CRLV', 'ANTT', 'CNH', 'ASO', 'ALVARÁ', 'LICENCIAMENTO']
    
    clean_doc_types = set()

    for raw_name in raw_doc_names:
        name_upper = str(raw_name).upper()
        name_upper = re.sub(r'\s*(NAME|DTYPE):.*', '', name_upper).strip()

        if not name_upper:
            continue

        found = False
        for generic_type in known_generic_types:
            type_to_check = 'ALVARA' if generic_type == 'ALVARÁ' else generic_type
            if type_to_check in name_upper:
                clean_doc_types.add(generic_type)
                found = True
                break
        
        if not found:
            cleaned_name = name_upper.replace('DOCUMENTO', '').strip()
            cleaned_name = re.sub(r'[\s\d.-]+$', '', cleaned_name).strip()
            if cleaned_name:
                clean_doc_types.add(cleaned_name)

    sorted_doc_types = sorted(list(clean_doc_types))

    configs = ConfiguracaoAlerta.query.all()
    configs_dict = {config.nome_documento.upper(): config.prazo_alerta_dias for config in configs}

    default_prazo = 30
    final_configs = {doc_type: configs_dict.get(doc_type, default_prazo) for doc_type in sorted_doc_types}
    
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
