from datetime import date, timedelta
from collections import defaultdict
from app import app, db, Manutencao, Condominio, Sindico


def verificar_alertas():
    hoje = date.today()
    limite = hoje + timedelta(days=30)

    alertas_por_telefone = defaultdict(list)

    with app.app_context():
        itens = (
            db.session.query(
                Manutencao,
                Condominio.nome.label("condominio_nome"),
                Sindico.nome.label("sindico_nome"),
                Sindico.telefone.label("sindico_telefone"),
            )
            .join(Condominio, Condominio.id == Manutencao.condominio_id)
            .join(Sindico, Sindico.id == Condominio.sindico_id)
            .filter(Manutencao.data_vencimento <= limite)
            .order_by(Sindico.nome.asc(), Condominio.nome.asc(), Manutencao.data_vencimento.asc())
            .all()
        )

        for m, condominio_nome, sindico_nome, telefone in itens:
            if not telefone:
                print(f"⚠️ Sem telefone cadastrado para {sindico_nome} - {condominio_nome}")
                continue

            telefone_limpo = "".join(filter(str.isdigit, telefone))

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

            alertas_por_telefone[telefone_limpo].append({
                "sindico_nome": sindico_nome,
                "status": status,
                "linha": linha
            })

        if not alertas_por_telefone:
            print("Nenhum alerta com telefone cadastrado encontrado.")
            return

        for telefone, alertas in alertas_por_telefone.items():
            sindico_nome = alertas[0]["sindico_nome"]

            vencidas = [a["linha"] for a in alertas if a["status"] == "vencida"]
            vence_hoje = [a["linha"] for a in alertas if a["status"] == "vence_hoje"]
            a_vencer = [a["linha"] for a in alertas if a["status"] == "a_vencer"]

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

            mensagem += "Favor verificar a execução dessas manutenções."

            print("=" * 50)
            print(f"Enviar para: {telefone}")
            print(mensagem)


if __name__ == "__main__":
    verificar_alertas()