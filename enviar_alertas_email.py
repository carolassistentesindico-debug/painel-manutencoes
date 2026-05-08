from datetime import date, timedelta
from collections import defaultdict
from app import app, db, Manutencao, Condominio, Sindico
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_REMETENTE = "carolassistentesindico@gmail.com"
EMAIL_SENHA = "nwtp cfaq ljvb nptm"


def verificar_alertas_email():
    hoje = date.today()
    limite = hoje + timedelta(days=30)

    alertas_por_email = defaultdict(list)

    with app.app_context():
        itens = (
            db.session.query(
                Manutencao,
                Condominio.nome.label("condominio_nome"),
                Sindico.nome.label("sindico_nome"),
                Sindico.email.label("sindico_email"),
            )
            .join(Condominio, Condominio.id == Manutencao.condominio_id)
            .join(Sindico, Sindico.id == Condominio.sindico_id)
            .filter(Manutencao.data_vencimento <= limite)
            .filter(Sindico.arquivado == False)
            .filter(Condominio.arquivado == False)
            .order_by(Sindico.nome.asc(), Condominio.nome.asc(), Manutencao.data_vencimento.asc())
            .all()
        )

        for m, condominio_nome, sindico_nome, email in itens:
            if not email:
                print(f"⚠️ Sem e-mail cadastrado para {sindico_nome} - {condominio_nome}")
                continue

            if m.data_vencimento < hoje:
                status = "vencida"
                linha = f"• {condominio_nome} — {m.descricao} — venceu em {m.data_vencimento.strftime('%d/%m/%Y')}"
            elif m.data_vencimento == hoje:
                status = "vence_hoje"
                linha = f"• {condominio_nome} — {m.descricao} — vence HOJE"
            else:
                dias = (m.data_vencimento - hoje).days
                status = "a_vencer"
                linha = f"• {condominio_nome} — {m.descricao} — vence em {dias} dias ({m.data_vencimento.strftime('%d/%m/%Y')})"

            if not any(a["linha"] == linha for a in alertas_por_email[email]):
                alertas_por_email[email].append({
                    "sindico_nome": sindico_nome,
                    "status": status,
                    "linha": linha
                })

        if not alertas_por_email:
            print("Nenhum alerta com e-mail cadastrado encontrado.")
            return

        for email, alertas in alertas_por_email.items():
            sindico_nome = alertas[0]["sindico_nome"]

            vencidas = [a["linha"] for a in alertas if a["status"] == "vencida"]
            vence_hoje = [a["linha"] for a in alertas if a["status"] == "vence_hoje"]
            a_vencer = [a["linha"] for a in alertas if a["status"] == "a_vencer"]

            assunto = "Alerta de manutenções pendentes"

            mensagem = f"Olá, {sindico_nome}!\n\n"
            mensagem += "Você possui manutenções que precisam de atenção:\n\n"

            if vencidas:
                mensagem += "🚨 VENCIDAS\n"
                mensagem += "\n".join(vencidas)
                mensagem += "\n\n"

            if vence_hoje:
                mensagem += "⚠️ VENCEM HOJE\n"
                mensagem += "\n".join(vence_hoje)
                mensagem += "\n\n"

            if a_vencer:
                mensagem += "🔔 PRÓXIMAS DO VENCIMENTO\n"
                mensagem += "\n".join(a_vencer)
                mensagem += "\n\n"

            mensagem += "Favor verificar a execução dessas manutenções.\n\n"
            mensagem += "Atenciosamente,\n\nCaroline Piekazewicz\nAssistente de Síndico"

            try:
                msg = MIMEMultipart()
                msg["From"] = EMAIL_REMETENTE
                msg["To"] = email
                msg["Subject"] = assunto

                msg.attach(MIMEText(mensagem, "plain"))

                servidor = smtplib.SMTP("smtp.gmail.com", 587)
                servidor.starttls()

                servidor.login(EMAIL_REMETENTE, EMAIL_SENHA)

                servidor.send_message(msg)
                servidor.quit()

                print("=" * 50)
                print(f"✅ E-mail enviado para {email}")

            except Exception as erro:
                print("=" * 50)
                print(f"❌ Erro ao enviar para {email}")
                print(erro)


if __name__ == "__main__":
    verificar_alertas_email()