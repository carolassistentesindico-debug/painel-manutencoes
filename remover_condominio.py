from app import app, db, Condominio, Manutencao

with app.app_context():

    condos = Condominio.query.filter(
        Condominio.nome == "Parque das Flores"
    ).all()

    for c in condos:

        manutencoes = Manutencao.query.filter_by(
            condominio_id=c.id
        ).all()

        for m in manutencoes:
            db.session.delete(m)

        db.session.delete(c)

    db.session.commit()

    print("Parque das Flores e manutenções removidos.")