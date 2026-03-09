from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Sindico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    telefone = db.Column(db.String(20))

    condominios = db.relationship("Condominio", backref="sindico", lazy=True)

class Condominio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    endereco = db.Column(db.String(200))

    sindico_id = db.Column(db.Integer, db.ForeignKey("sindico.id"), nullable=False)

    manutencoes = db.relationship("Manutencao", backref="condominio", lazy=True)

from datetime import date

class Manutencao(db.Model):
    __tablename__ = "manutencao"

    id = db.Column(db.Integer, primary_key=True)
    condominio_id = db.Column(db.Integer, db.ForeignKey("condominio.id"), nullable=False)

    descricao = db.Column(db.String(200), nullable=False)

    # datas
    data_inicio = db.Column(db.Date, nullable=False)           # data do serviço
    duracao_meses = db.Column(db.Integer, nullable=False)
    data_vencimento = db.Column(db.Date, nullable=False)       # vence

    # novos campos:
    empresa_ultima = db.Column(db.String(120), nullable=True)  # última empresa que fez
    telefone_empresa = db.Column(db.String(30))
    valor_servico = db.Column(db.Float, nullable=True)         # valor pago no serviço
    

    @property
    def status(self):
        if not self.data_vencimento:
            return "Sem vencimento"
        hoje = date.today()
        if self.data_vencimento < hoje:
            return "Vencida"
        if (self.data_vencimento - hoje).days <= 30:
            return "A vencer"
        return "Em dia"