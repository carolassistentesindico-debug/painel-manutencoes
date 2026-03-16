from flask import Flask, render_template, request, redirect, url_for, make_response, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, case, or_
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from urllib.parse import quote
import os

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

database_url = os.getenv("DATABASE_URL")
if database_url:
    # Alguns provedores usam postgres:// e o SQLAlchemy moderno prefere postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(INSTANCE_DIR, "painel.db")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.getenv("SECRET_KEY", "troque_esta_chave_em_producao")

USUARIO_ADMIN = os.getenv("ADMIN_USER", "caroline")
SENHA_ADMIN = os.getenv("ADMIN_PASSWORD", "carol089208")

db = SQLAlchemy(app)

_tabelas_criadas = False

@app.before_request
def criar_tabelas():
    global _tabelas_criadas
    if not _tabelas_criadas:
        db.create_all()
        _tabelas_criadas = True

# =======================
# MODELOS
# =======================

class Sindico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    arquivado = db.Column(db.Boolean, default=False)

    condominios = db.relationship("Condominio", backref="sindico", lazy=True)


class Condominio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    endereco = db.Column(db.String(200))
    cnpj = db.Column(db.String(18))
    sindico_id = db.Column(db.Integer, db.ForeignKey("sindico.id"), nullable=False)
    arquivado = db.Column(db.Boolean, default=False)

    manutencoes = db.relationship("Manutencao", backref="condominio", lazy=True)


class Manutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    duracao_meses = db.Column(db.Integer, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)
    empresa_ultima = db.Column(db.String(120))
    telefone_empresa = db.Column(db.String(30))
    valor_servico = db.Column(db.Float)
    condominio_id = db.Column(db.Integer, db.ForeignKey("condominio.id"), nullable=False)

    @property
    def status(self):
        hoje = date.today()
        if self.data_vencimento < hoje:
            return "Vencida"
        if (self.data_vencimento - hoje).days <= 30:
            return "A vencer"
        return "Em dia"


class HistoricoManutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    manutencao_id = db.Column(db.Integer, db.ForeignKey("manutencao.id"), nullable=False)
    data_execucao = db.Column(db.Date, nullable=False)
    empresa = db.Column(db.String(120))
    telefone_empresa = db.Column(db.String(30))
    valor_servico = db.Column(db.Float)
    observacao = db.Column(db.String(300))

    manutencao = db.relationship("Manutencao", backref="historicos")


with app.app_context():
    db.create_all()

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        if usuario == USUARIO_ADMIN and senha == SENHA_ADMIN:
            session["usuario_logado"] = usuario
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", erro="Usuário ou senha inválidos.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("usuario_logado", None)
    return redirect(url_for("login"))

# =======================
# DASHBOARD
# =======================

@app.route("/dashboard")
def dashboard():
    if "usuario_logado" not in session:
        return redirect(url_for("login"))

    hoje = date.today()
    limite = hoje + timedelta(days=30)

    vencidas_expr = func.coalesce(
        func.sum(
            case(
                (Manutencao.data_vencimento < hoje, 1),
                else_=0
            )
        ),
        0
    )

    a_vencer_expr = func.coalesce(
        func.sum(
            case(
                (
                    (Manutencao.data_vencimento >= hoje) &
                    (Manutencao.data_vencimento <= limite),
                    1
                ),
                else_=0
            )
        ),
        0
    )

    em_dia_expr = func.coalesce(
        func.sum(
            case(
                (Manutencao.data_vencimento > limite, 1),
                else_=0
            )
        ),
        0
    )

    total_expr = func.count(Manutencao.id)

    sindicos = (
        db.session.query(
            Sindico.id.label("sindico_id"),
            Sindico.nome.label("nome"),
            Sindico.email.label("email"),
            Sindico.telefone.label("telefone"),
            total_expr.label("total"),
            vencidas_expr.label("vencidas"),
            a_vencer_expr.label("a_vencer"),
            em_dia_expr.label("em_dia"),
        )
        .outerjoin(Condominio, Condominio.sindico_id == Sindico.id)
        .outerjoin(Manutencao, Manutencao.condominio_id == Condominio.id)
        .filter(
            (Sindico.arquivado.is_(False)) | (Sindico.arquivado.is_(None))
        )
        .group_by(Sindico.id, Sindico.nome, Sindico.email, Sindico.telefone)
        .order_by(vencidas_expr.desc(), Sindico.nome.asc())
        .all()
    )

    vencidas = sum(s.vencidas for s in sindicos)
    a_vencer = sum(s.a_vencer for s in sindicos)
    em_dia = sum(s.em_dia for s in sindicos)

    return render_template(
        "dashboard.html",
        sindicos=sindicos,
        vencidas=vencidas,
        a_vencer=a_vencer,
        em_dia=em_dia
    )

# =======================
# SÍNDICOS / CONDOMÍNIOS
# =======================

@app.route("/novo_sindico", methods=["POST"])
def novo_sindico():
    
    nome = request.form["nome"]
    email = request.form["email"]
    telefone = request.form["telefone"]

    novo = Sindico(nome=nome, email=email, telefone=telefone)
    db.session.add(novo)
    db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/sindico/<int:id>")
def ver_sindico(id):
    if "usuario_logado" not in session:
        return redirect(url_for("login"))
    sindico = Sindico.query.get_or_404(id)

    condominios = (
        Condominio.query
        .filter_by(sindico_id=id, arquivado=False)
        .order_by(Condominio.nome.asc())
        .all()
    )

    return render_template(
        "condominios.html",
        sindico=sindico,
        condominios=condominios
    )

@app.route("/sindico/<int:id>/condominios_arquivados")
def condominios_arquivados(id):
    sindico = Sindico.query.get_or_404(id)

    condominios = (
        Condominio.query
        .filter_by(sindico_id=id, arquivado=True)
        .order_by(Condominio.nome.asc())
        .all()
    )

    return render_template(
        "condominios_arquivados.html",
        sindico=sindico,
        condominios=condominios
    )


@app.route("/novo_condominio/<int:sindico_id>", methods=["POST"])
def novo_condominio(sindico_id):
    nome = request.form["nome"]
    endereco = request.form.get("endereco")
    cnpj = request.form.get("cnpj")

    if cnpj:
        cnpj = "".join(ch for ch in cnpj if ch.isdigit())
        if len(cnpj) != 14:
            return "CNPJ inválido (precisa ter 14 dígitos).", 400

    novo = Condominio(
        nome=nome,
        endereco=endereco,
        cnpj=cnpj,
        sindico_id=sindico_id
    )

    db.session.add(novo)
    db.session.commit()

    return redirect(url_for("ver_sindico", id=sindico_id))


@app.route("/sindico/<int:id>/arquivar", methods=["POST"])
def arquivar_sindico(id):
    s = Sindico.query.get_or_404(id)
    s.arquivado = True
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/sindico/<int:id>/desarquivar", methods=["POST"])
def desarquivar_sindico(id):
    s = Sindico.query.get_or_404(id)
    s.arquivado = False
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/sindico/<int:id>/excluir", methods=["POST"])
def excluir_sindico(id):
    s = Sindico.query.get_or_404(id)

    if s.condominios:
        return "Não é possível excluir: este síndico possui condomínios. Use ARQUIVAR.", 400

    db.session.delete(s)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/condominio/<int:id>/editar", methods=["GET", "POST"])
def editar_condominio(id):
    condominio = Condominio.query.get_or_404(id)

    if request.method == "POST":
        nome = request.form.get("nome")
        endereco = request.form.get("endereco")
        cnpj = request.form.get("cnpj")

        if cnpj:
            cnpj = "".join(ch for ch in cnpj if ch.isdigit())
            if len(cnpj) != 14:
                return "CNPJ inválido (precisa ter 14 dígitos).", 400

        condominio.nome = nome
        condominio.endereco = endereco
        condominio.cnpj = cnpj

        db.session.commit()
        return redirect(url_for("ver_sindico", id=condominio.sindico_id))

    return render_template("editar_condominio.html", condominio=condominio)

@app.route("/condominio/<int:id>/arquivar", methods=["POST"])
def arquivar_condominio(id):
    condominio = Condominio.query.get_or_404(id)
    condominio.arquivado = True
    db.session.commit()
    return redirect(url_for("ver_sindico", id=condominio.sindico_id))

@app.route("/condominio/<int:id>/desarquivar", methods=["POST"])
def desarquivar_condominio(id):
    condominio = Condominio.query.get_or_404(id)
    condominio.arquivado = False
    db.session.commit()
    return redirect(url_for("ver_sindico", id=condominio.sindico_id))

# =======================
# MANUTENÇÕES
# =======================

@app.route("/condominio/<int:id>")
def ver_condominio(id):
    if "usuario_logado" not in session:
        return redirect(url_for("login"))
    condominio = Condominio.query.get_or_404(id)

    filtro = request.args.get("filtro", "todos")
    busca = (request.args.get("q") or "").strip()

    q = Manutencao.query.filter_by(condominio_id=id)

    hoje = date.today()
    limite = hoje + timedelta(days=30)

    if filtro == "vencidas":
        q = q.filter(Manutencao.data_vencimento < hoje)
    elif filtro == "a_vencer":
        q = q.filter(Manutencao.data_vencimento >= hoje, Manutencao.data_vencimento <= limite)
    elif filtro == "em_dia":
        q = q.filter(Manutencao.data_vencimento > limite)
    else:
        filtro = "todos"

    if busca:
        q = q.filter(func.lower(Manutencao.descricao).like(f"%{busca.lower()}%"))

    manutencoes = q.order_by(Manutencao.data_vencimento.asc()).all()

    return render_template(
        "manutencoes.html",
        condominio=condominio,
        manutencoes=manutencoes,
        filtro=filtro,
        busca=busca
    )


@app.route("/nova_manutencao/<int:condominio_id>", methods=["GET", "POST"])
def nova_manutencao(condominio_id):
    if request.method == "POST":
        descricao = request.form.get("descricao")
        data_inicio_str = request.form.get("data_inicio")
        duracao_meses_str = request.form.get("duracao_meses")
        empresa_ultima = request.form.get("empresa_ultima") or None
        telefone_empresa = request.form.get("telefone_empresa") or None
        valor_servico_str = request.form.get("valor_servico")
        valor_servico = float(valor_servico_str) if valor_servico_str else None

        if not data_inicio_str:
            return "Erro: data não informada."

        data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()
        duracao_meses = int(duracao_meses_str) if duracao_meses_str else 0
        data_vencimento = data_inicio + relativedelta(months=duracao_meses)

        nova = Manutencao(
            descricao=descricao,
            data_inicio=data_inicio,
            duracao_meses=duracao_meses,
            data_vencimento=data_vencimento,
            empresa_ultima=empresa_ultima,
            telefone_empresa=telefone_empresa,
            valor_servico=valor_servico,
            condominio_id=condominio_id
        )

        db.session.add(nova)
        db.session.commit()

        return redirect(url_for("ver_condominio", id=condominio_id))

    return render_template("nova_manutencao.html", condominio_id=condominio_id)


@app.route("/manutencao/<int:manutencao_id>/excluir", methods=["POST"])
def excluir_manutencao(manutencao_id):
    m = Manutencao.query.get_or_404(manutencao_id)
    condominio_id = m.condominio_id
    db.session.delete(m)
    db.session.commit()
    return redirect(url_for("ver_condominio", id=condominio_id))


@app.route("/manutencao/<int:manutencao_id>/editar", methods=["GET", "POST"])
def editar_manutencao(manutencao_id):
    m = Manutencao.query.get_or_404(manutencao_id)

    if request.method == "POST":
        m.descricao = request.form.get("descricao")
        data_inicio_str = request.form.get("data_inicio")
        m.duracao_meses = int(request.form.get("duracao_meses") or 0)
        m.empresa_ultima = request.form.get("empresa_ultima") or None
        m.telefone_empresa = request.form.get("telefone_empresa") or None

        valor_str = request.form.get("valor_servico")
        m.valor_servico = float(valor_str) if valor_str else None

        if data_inicio_str:
            m.data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date()

        m.data_vencimento = m.data_inicio + relativedelta(months=m.duracao_meses)

        db.session.commit()
        return redirect(url_for("ver_condominio", id=m.condominio_id))

    return render_template("editar_manutencao.html", m=m)


@app.route("/manutencao/<int:manutencao_id>/executar", methods=["GET", "POST"])
def executar_manutencao(manutencao_id):
    m = Manutencao.query.get_or_404(manutencao_id)

    if request.method == "POST":
        data_execucao_str = request.form.get("data_execucao")
        empresa = request.form.get("empresa") or None
        telefone_empresa = request.form.get("telefone_empresa") or None
        valor_str = request.form.get("valor_servico")
        observacao = request.form.get("observacao") or None

        data_execucao = datetime.strptime(data_execucao_str, "%Y-%m-%d").date()
        valor_servico = float(valor_str) if valor_str else None

        hist = HistoricoManutencao(
            manutencao_id=m.id,
            data_execucao=data_execucao,
            empresa=empresa,
            telefone_empresa=telefone_empresa,
            valor_servico=valor_servico,
            observacao=observacao
        )
        db.session.add(hist)

        m.data_inicio = data_execucao
        m.data_vencimento = data_execucao + relativedelta(months=m.duracao_meses)
        m.empresa_ultima = empresa
        m.telefone_empresa = telefone_empresa
        m.valor_servico = valor_servico

        db.session.commit()
        return redirect(url_for("ver_condominio", id=m.condominio_id))

    return render_template("executar_manutencao.html", m=m)


@app.route("/manutencao/<int:manutencao_id>/historico")
def historico_manutencao(manutencao_id):
    m = Manutencao.query.get_or_404(manutencao_id)

    historicos = (
        HistoricoManutencao.query
        .filter_by(manutencao_id=manutencao_id)
        .order_by(HistoricoManutencao.data_execucao.desc())
        .all()
    )

    return render_template("historico_manutencao.html", m=m, historicos=historicos)

# =======================
# ALERTAS
# =======================

@app.route("/alertas")
def alertas():
    if "usuario_logado" not in session:
        return redirect(url_for("login"))
    hoje = date.today()
    limite = hoje + timedelta(days=30)

    itens = (
        db.session.query(
            Manutencao,
            Condominio.nome.label("condominio_nome"),
            Sindico.nome.label("sindico_nome"),
            Sindico.telefone.label("sindico_telefone"),
            Condominio.id.label("condominio_id"),
        )
        .join(Condominio, Condominio.id == Manutencao.condominio_id)
        .join(Sindico, Sindico.id == Condominio.sindico_id)
        .filter(Sindico.arquivado == 0)
        .filter(
            or_(
                Manutencao.data_vencimento < hoje,
                Manutencao.data_vencimento <= limite
            )
        )
        .order_by(Sindico.nome.asc(), Condominio.nome.asc(), Manutencao.data_vencimento.asc())
        .all()
    )

    alertas_dict = {}

    for m, cond_nome, sind_nome, sindico_telefone, cond_id in itens:
        if sind_nome not in alertas_dict:
            alertas_dict[sind_nome] = {
                "telefone": sindico_telefone,
                "itens": []
            }

        if m.data_vencimento < hoje:
            dias = (hoje - m.data_vencimento).days
            status = "vencida"
        else:
            dias = (m.data_vencimento - hoje).days
            status = "a_vencer"

        alertas_dict[sind_nome]["itens"].append({
            "descricao": m.descricao,
            "condominio": cond_nome,
            "condominio_id": cond_id,
            "data": m.data_vencimento,
            "dias": dias,
            "status": status
        })

    for sindico, dados in alertas_dict.items():
        linhas = []
        linhas.append(f"*📌 Alertas de manutenção (até {limite.strftime('%d/%m/%Y')})*")
        linhas.append("")

        if dados["itens"]:
            condominio = dados["itens"][0]["condominio"]
            linhas.append(f"*🏢 {sindico} — {condominio}*")
            linhas.append("")

        for i in dados["itens"]:
            status = "🔴 Vencida" if i["status"] == "vencida" else "🟡 A vencer"
            linhas.append(f"* {i['descricao']} — vence {i['data'].strftime('%d/%m/%Y')} ({status})")

        texto = "\n".join(linhas)
        telefone = "".join(ch for ch in (dados["telefone"] or "") if ch.isdigit())

        if telefone:
            if not telefone.startswith("55"):
                telefone = "55" + telefone
            dados["whatsapp_url"] = f"https://wa.me/{telefone}?text={quote(texto)}"
        else:
            dados["whatsapp_url"] = None

        dados["texto"] = texto

    return render_template("alertas.html", alertas=alertas_dict)





@app.route("/relatorios/historico_pdf")
def relatorio_historico_pdf():
    if "usuario_logado" not in session:
        return redirect(url_for("login"))

    condominio_id = (request.args.get("condominio_id") or "").strip()
    servico = (request.args.get("servico") or "").strip()
    data_inicio = (request.args.get("data_inicio") or "").strip()
    data_fim = (request.args.get("data_fim") or "").strip()

    query = (
        db.session.query(
            HistoricoManutencao,
            Manutencao.descricao,
            Condominio.nome.label("condominio_nome")
        )
        .join(Manutencao, Manutencao.id == HistoricoManutencao.manutencao_id)
        .join(Condominio, Condominio.id == Manutencao.condominio_id)
        .filter((Condominio.arquivado.is_(False)) | (Condominio.arquivado.is_(None)))
    )

    if condominio_id:
        query = query.filter(Condominio.id == int(condominio_id))

    if servico:
        query = query.filter(Manutencao.descricao == servico)

    if data_inicio:
        dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        query = query.filter(HistoricoManutencao.data_execucao >= dt_inicio)

    if data_fim:
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d").date()
        query = query.filter(HistoricoManutencao.data_execucao <= dt_fim)

    registros = query.order_by(
        HistoricoManutencao.data_execucao.desc(),
        Condominio.nome.asc()
    ).all()

    nome_condominio = "Todos"
    if condominio_id:
        cond = Condominio.query.get(int(condominio_id))
        if cond:
            nome_condominio = cond.nome

    response = make_response()
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=relatorio_historico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    pdf = canvas.Canvas(response.stream, pagesize=A4)
    largura, altura = A4

    margem_esq = 35
    margem_dir = largura - 35
    y = altura - 40
    hoje = date.today()

    MARROM = (0.40, 0.18, 0.06)
    BEGE = (0.96, 0.83, 0.74)
    OFFWHITE = (0.96, 0.93, 0.93)
    LINHA = (0.88, 0.82, 0.78)

    def rodape():
        pdf.setStrokeColorRGB(*LINHA)
        pdf.line(margem_esq, 30, margem_dir, 30)
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawString(margem_esq, 18, "Desenvolvido por Caroline Piekazewicz - Assistente de Síndico")
        pdf.drawRightString(margem_dir, 18, f"Página {pdf.getPageNumber()}")
        pdf.setFillColorRGB(0, 0, 0)

    def cabecalho():
        nonlocal y
        pdf.setFillColorRGB(*MARROM)
        pdf.rect(0, altura - 74, largura, 74, fill=1, stroke=0)

        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(margem_esq, altura - 34, "Relatório de Histórico de Manutenções")

        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(margem_dir, altura - 54, f"Emitido em {hoje.strftime('%d/%m/%Y')}")
        pdf.setFillColorRGB(0, 0, 0)
        y = altura - 100

    def bloco_filtros():
        nonlocal y
        pdf.setFillColorRGB(*OFFWHITE)
        pdf.setStrokeColorRGB(*LINHA)
        pdf.roundRect(margem_esq, y - 62, margem_dir - margem_esq, 62, 12, fill=1, stroke=1)

        pdf.setFillColorRGB(*MARROM)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margem_esq + 12, y - 16, "FILTROS APLICADOS")

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margem_esq + 12, y - 32, f"Condomínio: {nome_condominio}")
        pdf.drawString(margem_esq + 250, y - 32, f"Manutenção: {servico or 'Todas do condomínio'}")
        pdf.drawString(margem_esq + 12, y - 46, f"Período: {data_inicio or '-'} até {data_fim or '-'}")

        y -= 80

    def cabecalho_tabela():
        nonlocal y
        pdf.setFillColorRGB(*BEGE)
        pdf.rect(35, y - 4, 525, 18, fill=1, stroke=0)

        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColorRGB(*MARROM)
        pdf.drawString(42, y, "Condomínio")
        pdf.drawString(180, y, "Manutenção")
        pdf.drawString(320, y, "Execução")
        pdf.drawString(390, y, "Empresa")
        pdf.drawRightString(548, y, "Valor")

        pdf.setFillColorRGB(0, 0, 0)
        y -= 18

    def nova_pagina():
        nonlocal y
        rodape()
        pdf.showPage()
        cabecalho()
        bloco_filtros()
        cabecalho_tabela()

    cabecalho()
    bloco_filtros()
    cabecalho_tabela()

    if not registros:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margem_esq, y, "Nenhum registro encontrado para os filtros informados.")
    else:
        linha = 0
        for hist, descricao, condominio_nome in registros:
            if y < 70:
                nova_pagina()

            empresa = (hist.empresa or "-")[:18]
            valor = f"R$ {hist.valor_servico:.2f}" if hist.valor_servico is not None else "-"
            data_execucao = hist.data_execucao.strftime("%d/%m/%Y") if hist.data_execucao else "-"

            if linha % 2 == 0:
                pdf.setFillColorRGB(0.995, 0.985, 0.98)
                pdf.rect(35, y - 4, 525, 16, fill=1, stroke=0)
                pdf.setFillColorRGB(0, 0, 0)

            pdf.setFont("Helvetica", 8)
            pdf.drawString(42, y, condominio_nome[:24])
            pdf.drawString(180, y, descricao[:24])
            pdf.drawString(320, y, data_execucao)
            pdf.drawString(390, y, empresa)
            pdf.drawRightString(548, y, valor)

            y -= 18
            linha += 1

    rodape()
    pdf.save()
    return response


@app.route("/relatorios/alertas_pdf")
def relatorio_alertas_pdf():
    if "usuario_logado" not in session:
        return redirect(url_for("login"))

    hoje = date.today()
    limite = hoje + timedelta(days=30)
    tipo = request.args.get("tipo", "todos")

    query = (
        db.session.query(
            Manutencao,
            Condominio.nome.label("condominio_nome"),
            Sindico.nome.label("sindico_nome")
        )
        .join(Condominio, Condominio.id == Manutencao.condominio_id)
        .join(Sindico, Sindico.id == Condominio.sindico_id)
        .filter(
            ((Sindico.arquivado.is_(False)) | (Sindico.arquivado.is_(None))),
            ((Condominio.arquivado.is_(False)) | (Condominio.arquivado.is_(None)))
        )
    )

    if tipo == "vencidas":
        query = query.filter(Manutencao.data_vencimento < hoje)
        titulo = "Relatório de Manutenções Vencidas"
    elif tipo == "a_vencer":
        query = query.filter(
            Manutencao.data_vencimento >= hoje,
            Manutencao.data_vencimento <= limite
        )
        titulo = "Relatório de Manutenções a Vencer"
    else:
        query = query.filter(
            or_(
                Manutencao.data_vencimento < hoje,
                Manutencao.data_vencimento <= limite
            )
        )
        titulo = "Relatório de Manutenções Vencidas e a Vencer"

    itens = query.order_by(
        Sindico.nome.asc(),
        Condominio.nome.asc(),
        Manutencao.data_vencimento.asc()
    ).all()

    response = make_response()
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=relatorio_alertas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    pdf = canvas.Canvas(response.stream, pagesize=A4)
    largura, altura = A4

    margem_esq = 35
    margem_dir = largura - 35
    y = altura - 40

    MARROM = (0.40, 0.18, 0.06)
    BEGE = (0.96, 0.83, 0.74)
    LINHA = (0.88, 0.82, 0.78)

    def rodape():
        pdf.setStrokeColorRGB(*LINHA)
        pdf.line(margem_esq, 30, margem_dir, 30)
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawString(margem_esq, 18, "Desenvolvido por Caroline Piekazewicz - Assistente de Síndico")
        pdf.drawRightString(margem_dir, 18, f"Página {pdf.getPageNumber()}")
        pdf.setFillColorRGB(0, 0, 0)

    def cabecalho():
        nonlocal y
        pdf.setFillColorRGB(*MARROM)
        pdf.rect(0, altura - 74, largura, 74, fill=1, stroke=0)

        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(margem_esq, altura - 34, titulo)

        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(margem_dir, altura - 54, f"Emitido em {hoje.strftime('%d/%m/%Y')}")
        pdf.setFillColorRGB(0, 0, 0)
        y = altura - 100

    def cabecalho_tabela():
        nonlocal y
        pdf.setFillColorRGB(*BEGE)
        pdf.rect(35, y - 4, 525, 18, fill=1, stroke=0)

        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColorRGB(*MARROM)
        pdf.drawString(42, y, "Síndico")
        pdf.drawString(155, y, "Condomínio")
        pdf.drawString(300, y, "Manutenção")
        pdf.drawString(430, y, "Vencimento")
        pdf.drawString(510, y, "Status")
        pdf.setFillColorRGB(0, 0, 0)
        y -= 18

    def nova_pagina():
        nonlocal y
        rodape()
        pdf.showPage()
        cabecalho()
        cabecalho_tabela()

    cabecalho()
    cabecalho_tabela()

    if not itens:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margem_esq, y, "Nenhum registro encontrado.")
    else:
        linha = 0
        for m, cond_nome, sind_nome in itens:
            if y < 70:
                nova_pagina()

            status = "Vencida" if m.data_vencimento < hoje else "A vencer"

            if linha % 2 == 0:
                pdf.setFillColorRGB(0.995, 0.985, 0.98)
                pdf.rect(35, y - 4, 525, 16, fill=1, stroke=0)
                pdf.setFillColorRGB(0, 0, 0)

            pdf.setFont("Helvetica", 8)
            pdf.drawString(42, y, sind_nome[:18])
            pdf.drawString(155, y, cond_nome[:24])
            pdf.drawString(300, y, m.descricao[:24])
            pdf.drawString(430, y, m.data_vencimento.strftime("%d/%m/%Y"))
            pdf.drawString(510, y, status)

            y -= 18
            linha += 1

    rodape()
    pdf.save()
    return response

@app.route("/sindico/<int:id>/relatorio_pdf")
def relatorio_sindico_pdf(id):
    if "usuario_logado" not in session:
        return redirect(url_for("login"))

    sindico = Sindico.query.get_or_404(id)

    condominios = (
        Condominio.query
        .filter(
            Condominio.sindico_id == id,
            ((Condominio.arquivado.is_(False)) | (Condominio.arquivado.is_(None)))
        )
        .order_by(Condominio.nome.asc())
        .all()
    )

    response = make_response()
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=relatorio_sindico_{sindico.nome}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    pdf = canvas.Canvas(response.stream, pagesize=A4)
    largura, altura = A4

    margem_esq = 35
    margem_dir = largura - 35
    y = altura - 40
    hoje = date.today()

    MARROM = (0.40, 0.18, 0.06)
    BEGE = (0.96, 0.83, 0.74)
    OFFWHITE = (0.96, 0.93, 0.93)
    LINHA = (0.88, 0.82, 0.78)

    def rodape():
        pdf.setStrokeColorRGB(*LINHA)
        pdf.line(margem_esq, 30, margem_dir, 30)
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawString(margem_esq, 18, "Desenvolvido por Caroline Piekazewicz - Assistente de Síndico")
        pdf.drawRightString(margem_dir, 18, f"Página {pdf.getPageNumber()}")
        pdf.setFillColorRGB(0, 0, 0)

    def status_info(manutencao):
        if manutencao.data_vencimento < hoje:
            return {"texto": "Vencida", "bg": (1.00, 0.91, 0.92), "fg": (0.69, 0.00, 0.13)}
        elif (manutencao.data_vencimento - hoje).days <= 30:
            return {"texto": "A vencer", "bg": (1.00, 0.96, 0.90), "fg": (0.70, 0.42, 0.00)}
        return {"texto": "Em dia", "bg": (0.92, 0.98, 0.94), "fg": (0.04, 0.42, 0.16)}

    def desenhar_status(x, y_base, manutencao):
        info = status_info(manutencao)
        largura_box = 50
        altura_box = 12

        pdf.setFillColorRGB(*info["bg"])
        pdf.setStrokeColorRGB(*info["bg"])
        pdf.roundRect(x, y_base - 3, largura_box, altura_box, 6, fill=1, stroke=1)

        pdf.setFillColorRGB(*info["fg"])
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(x + largura_box / 2, y_base, info["texto"])

        pdf.setFillColorRGB(0, 0, 0)

    def cabecalho():
        nonlocal y
        pdf.setFillColorRGB(*MARROM)
        pdf.rect(0, altura - 74, largura, 74, fill=1, stroke=0)

        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(margem_esq, altura - 34, "Relatório de Manutenções por Síndico")

        pdf.setFont("Helvetica", 9)
        pdf.drawString(margem_esq, altura - 54, f"Síndico: {sindico.nome}")
        pdf.drawRightString(margem_dir, altura - 54, f"Emitido em {hoje.strftime('%d/%m/%Y')}")

        pdf.setFillColorRGB(0, 0, 0)
        y = altura - 100

    def bloco_sindico():
        nonlocal y
        pdf.setFillColorRGB(*OFFWHITE)
        pdf.setStrokeColorRGB(*LINHA)
        pdf.roundRect(margem_esq, y - 62, margem_dir - margem_esq, 62, 12, fill=1, stroke=1)

        pdf.setFillColorRGB(*MARROM)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margem_esq + 12, y - 16, "DADOS DO SÍNDICO")

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margem_esq + 12, y - 32, f"Nome: {sindico.nome}")
        pdf.drawString(margem_esq + 12, y - 46, f"E-mail: {sindico.email or '-'}")
        pdf.drawString(margem_esq + 300, y - 32, f"Telefone: {sindico.telefone or '-'}")

        y -= 80

    def cabecalho_tabela():
        nonlocal y
        pdf.setFillColorRGB(*BEGE)
        pdf.rect(35, y - 4, 525, 18, fill=1, stroke=0)

        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColorRGB(*MARROM)
        pdf.drawString(42, y, "Descrição")
        pdf.drawString(205, y, "Empresa")
        pdf.drawString(300, y, "Serviço")
        pdf.drawString(385, y, "Vencimento")
        pdf.drawString(448, y, "Status")
        pdf.drawRightString(548, y, "Valor")

        pdf.setFillColorRGB(0, 0, 0)
        y -= 18

    def nova_pagina():
        nonlocal y
        rodape()
        pdf.showPage()
        cabecalho()
        bloco_sindico()

    cabecalho()
    bloco_sindico()

    for cond in condominios:
        manutencoes = (
            Manutencao.query
            .filter_by(condominio_id=cond.id)
            .order_by(Manutencao.data_vencimento.asc())
            .all()
        )

        if y < 120:
            nova_pagina()

        pdf.setFillColorRGB(*MARROM)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(margem_esq, y, f"Condomínio: {cond.nome}")
        pdf.setFillColorRGB(0, 0, 0)
        y -= 15

        pdf.setFont("Helvetica", 9)
        pdf.drawString(margem_esq, y, f"Endereço: {cond.endereco or '-'}")
        y -= 14
        pdf.drawString(margem_esq, y, f"CNPJ: {cond.cnpj or '-'}")
        y -= 18

        cabecalho_tabela()

        if not manutencoes:
            pdf.setFont("Helvetica", 9)
            pdf.drawString(margem_esq, y, "Nenhuma manutenção cadastrada.")
            y -= 24
            continue

        linha = 0
        for m in manutencoes:
            if y < 70:
                nova_pagina()
                cabecalho_tabela()

            descricao = m.descricao
            empresa = (m.empresa_ultima or "-").title()
            servico = m.data_inicio.strftime("%d/%m/%Y") if m.data_inicio else "-"
            vencimento = m.data_vencimento.strftime("%d/%m/%Y") if m.data_vencimento else "-"
            valor = f"R$ {m.valor_servico:.2f}" if m.valor_servico is not None else "-"

            if linha % 2 == 0:
                pdf.setFillColorRGB(0.995, 0.985, 0.98)
                pdf.rect(35, y - 4, 525, 16, fill=1, stroke=0)
                pdf.setFillColorRGB(0, 0, 0)

            pdf.setFont("Helvetica", 8)
            pdf.drawString(42, y, descricao[:38])
            pdf.drawString(205, y, empresa[:18])
            pdf.drawString(300, y, servico)
            pdf.drawString(385, y, vencimento)
            desenhar_status(448, y, m)
            pdf.drawRightString(548, y, valor)

            y -= 18
            linha += 1

        y -= 10

    rodape()
    pdf.save()
    return response

@app.route("/relatorios")
def relatorios():
    if "usuario_logado" not in session:
        return redirect(url_for("login"))

    condominios = (
        db.session.query(Condominio)
        .join(Sindico, Sindico.id == Condominio.sindico_id)
        .filter(
            ((Condominio.arquivado.is_(False)) | (Condominio.arquivado.is_(None))),
            ((Sindico.arquivado.is_(False)) | (Sindico.arquivado.is_(None)))
        )
        .order_by(Condominio.nome.asc())
        .all()
    )

    sindicos = (
        Sindico.query
        .filter(
            (Sindico.arquivado.is_(False)) | (Sindico.arquivado.is_(None))
        )
        .order_by(Sindico.nome.asc())
        .all()
    )

    return render_template(
        "relatorios.html",
        condominios=condominios,
        sindicos=sindicos
    )

@app.route("/api/manutencoes_por_condominio/<int:condominio_id>")
def api_manutencoes_por_condominio(condominio_id):
    if "usuario_logado" not in session:
        return {"erro": "não autorizado"}, 401

    condominio = (
        Condominio.query
        .filter(
            Condominio.id == condominio_id,
            (Condominio.arquivado.is_(False)) | (Condominio.arquivado.is_(None))
        )
        .first()
    )

    if not condominio:
        return {"manutencoes": []}

    manutencoes = (
        db.session.query(Manutencao.descricao)
        .filter(Manutencao.condominio_id == condominio_id)
        .distinct()
        .order_by(Manutencao.descricao.asc())
        .all()
    )

    return {
        "manutencoes": [m[0] for m in manutencoes if m[0]]
    }

@app.route("/condominio/<int:id>/relatorio_pdf")
def relatorio_condominio_pdf(id):
    if "usuario_logado" not in session:
        return redirect(url_for("login"))

    condominio = (
        Condominio.query
        .filter(
            Condominio.id == id,
            (Condominio.arquivado.is_(False)) | (Condominio.arquivado.is_(None))
        )
        .first_or_404()
    )

    manutencoes = (
        Manutencao.query
        .filter(Manutencao.condominio_id == condominio.id)
        .order_by(Manutencao.data_vencimento.asc())
        .all()
    )

    response = make_response()
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=relatorio_condominio_{condominio.nome}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    pdf = canvas.Canvas(response.stream, pagesize=A4)
    largura, altura = A4

    margem_esq = 35
    margem_dir = largura - 35
    y = altura - 40
    hoje = date.today()

    MARROM = (0.40, 0.18, 0.06)
    BEGE = (0.96, 0.83, 0.74)
    OFFWHITE = (0.96, 0.93, 0.93)
    LINHA = (0.88, 0.82, 0.78)

    def rodape():
        pdf.setStrokeColorRGB(*LINHA)
        pdf.line(margem_esq, 30, margem_dir, 30)
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawString(margem_esq, 18, "Desenvolvido por Caroline Piekazewicz - Assistente de Síndico")
        pdf.drawRightString(margem_dir, 18, f"Página {pdf.getPageNumber()}")
        pdf.setFillColorRGB(0, 0, 0)

    def status_info(manutencao):
        if manutencao.data_vencimento < hoje:
            return {"texto": "Vencida", "bg": (1.00, 0.91, 0.92), "fg": (0.69, 0.00, 0.13)}
        elif (manutencao.data_vencimento - hoje).days <= 30:
            return {"texto": "A vencer", "bg": (1.00, 0.96, 0.90), "fg": (0.70, 0.42, 0.00)}
        return {"texto": "Em dia", "bg": (0.92, 0.98, 0.94), "fg": (0.04, 0.42, 0.16)}

    def desenhar_status(x, y_base, manutencao):
        info = status_info(manutencao)
        largura_box = 50
        altura_box = 12

        pdf.setFillColorRGB(*info["bg"])
        pdf.setStrokeColorRGB(*info["bg"])
        pdf.roundRect(x, y_base - 3, largura_box, altura_box, 6, fill=1, stroke=1)

        pdf.setFillColorRGB(*info["fg"])
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(x + largura_box / 2, y_base, info["texto"])
        pdf.setFillColorRGB(0, 0, 0)

    def cabecalho():
        nonlocal y
        pdf.setFillColorRGB(*MARROM)
        pdf.rect(0, altura - 74, largura, 74, fill=1, stroke=0)

        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(margem_esq, altura - 34, "Relatório de Manutenções por Condomínio")

        pdf.setFont("Helvetica", 9)
        pdf.drawString(margem_esq, altura - 54, f"Condomínio: {condominio.nome}")
        pdf.drawRightString(margem_dir, altura - 54, f"Emitido em {hoje.strftime('%d/%m/%Y')}")

        pdf.setFillColorRGB(0, 0, 0)
        y = altura - 100

    def bloco_condominio():
        nonlocal y
        pdf.setFillColorRGB(*OFFWHITE)
        pdf.setStrokeColorRGB(*LINHA)
        pdf.roundRect(margem_esq, y - 62, margem_dir - margem_esq, 62, 12, fill=1, stroke=1)

        pdf.setFillColorRGB(*MARROM)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margem_esq + 12, y - 16, "DADOS DO CONDOMÍNIO")

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(margem_esq + 12, y - 32, f"Nome: {condominio.nome}")
        pdf.drawString(margem_esq + 12, y - 46, f"Endereço: {condominio.endereco or '-'}")
        pdf.drawString(margem_esq + 320, y - 32, f"CNPJ: {condominio.cnpj or '-'}")

        y -= 80

    def cabecalho_tabela():
        nonlocal y
        pdf.setFillColorRGB(*BEGE)
        pdf.rect(35, y - 4, 525, 18, fill=1, stroke=0)

        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColorRGB(*MARROM)
        pdf.drawString(42, y, "Descrição")
        pdf.drawString(205, y, "Empresa")
        pdf.drawString(300, y, "Último serviço")
        pdf.drawString(385, y, "Vencimento")
        pdf.drawString(448, y, "Status")
        pdf.drawRightString(548, y, "Valor")

        pdf.setFillColorRGB(0, 0, 0)
        y -= 18

    def nova_pagina():
        nonlocal y
        rodape()
        pdf.showPage()
        cabecalho()
        bloco_condominio()
        cabecalho_tabela()

    cabecalho()
    bloco_condominio()
    cabecalho_tabela()

    if not manutencoes:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margem_esq, y, "Nenhuma manutenção cadastrada para este condomínio.")
    else:
        linha = 0
        for m in manutencoes:
            if y < 70:
                nova_pagina()

            descricao = m.descricao[:38]
            empresa = (m.empresa_ultima or "-").title()[:18]
            servico = m.data_inicio.strftime("%d/%m/%Y") if m.data_inicio else "-"
            vencimento = m.data_vencimento.strftime("%d/%m/%Y") if m.data_vencimento else "-"
            valor = f"R$ {m.valor_servico:.2f}" if m.valor_servico is not None else "-"

            if linha % 2 == 0:
                pdf.setFillColorRGB(0.995, 0.985, 0.98)
                pdf.rect(35, y - 4, 525, 16, fill=1, stroke=0)
                pdf.setFillColorRGB(0, 0, 0)

            pdf.setFont("Helvetica", 8)
            pdf.drawString(42, y, descricao)
            pdf.drawString(205, y, empresa)
            pdf.drawString(300, y, servico)
            pdf.drawString(385, y, vencimento)
            desenhar_status(448, y, m)
            pdf.drawRightString(548, y, valor)

            y -= 18
            linha += 1

    rodape()
    pdf.save()
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)