import hashlib
import csv
from io import StringIO
import json
import os
from pathlib import Path
import secrets

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from conciliador.domain import InputError, account_digits, classify, normalize, parse_date
from conciliador.makro import PRIVATE_CHART, chart, export_workbook, learn_workbook, prepare_private_chart, validate_code
from conciliador.readers import read_statement
from conciliador.store import connect

ROOT = Path(__file__).resolve().parent


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024 * 1024, DATABASE=str(ROOT / "data" / "conciliador.sqlite3"), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        key_file = ROOT / "data" / "session.key"
        key_file.parent.mkdir(exist_ok=True)
        if not key_file.exists():
            key_file.write_text(secrets.token_hex(32))
            key_file.chmod(0o600)
        app.config["SECRET_KEY"] = key_file.read_text()

    def db():
        if "db" not in g:
            g.db = connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(error):
        connection = g.pop("db", None)
        if connection:
            connection.close()

    @app.before_request
    def csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(24)
        if request.method == "POST" and not secrets.compare_digest(request.form.get("csrf", ""), session["csrf"]):
            abort(400, "Formulário expirado. Atualize a página e tente novamente.")

    @app.context_processor
    def context():
        return {"csrf": session.get("csrf", ""), "chart": chart(), "private_chart": PRIVATE_CHART.exists()}

    @app.template_filter("brl")
    def brl(cents):
        return f"{cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    @app.errorhandler(InputError)
    def input_error(exc):
        flash(str(exc), "error")
        # Do not redirect to caller-provided hosts.
        return redirect(url_for("home"))

    @app.errorhandler(RequestEntityTooLarge)
    def too_big(exc):
        flash("Arquivo maior que 16 MB. Divida o extrato em arquivos menores.", "error")
        return redirect(url_for("home"))

    @app.get("/")
    def home():
        accounts = db().execute("SELECT a.*,c.name client_name FROM accounts a JOIN clients c ON c.id=a.client_id ORDER BY c.name,a.name").fetchall()
        batches = db().execute("SELECT b.*,a.name account_name,c.name client_name,(SELECT COUNT(*) FROM movements m WHERE m.batch_id=b.id) total FROM batches b JOIN accounts a ON a.id=b.account_id JOIN clients c ON c.id=a.client_id ORDER BY b.id DESC").fetchall()
        return render_template("home.html", clients=db().execute("SELECT * FROM clients ORDER BY name").fetchall(), accounts=accounts, batches=batches)

    @app.post("/clients")
    def add_client():
        name = request.form.get("name", "").strip()
        if not name or len(name) > 160:
            raise InputError("Informe o nome do cliente, com até 160 caracteres.")
        with db():
            db().execute("INSERT INTO clients(name,tax_id) VALUES(?,?)", (name, request.form.get("tax_id", "").strip()))
        flash("Cliente cadastrado.", "success")
        return redirect(url_for("home"))

    @app.post("/chart")
    def upload_chart():
        upload = request.files.get("file")
        if not upload:
            raise InputError("Selecione o plano de contas.")
        try:
            content, count = prepare_private_chart(upload.read(), upload.filename)
        except InputError:
            raise
        except Exception as exc:
            raise InputError("Não foi possível ler o plano de contas; confira o formato.") from exc
        # Existing references must remain valid if a local plan is replaced.
        codes = {int(r["codigo"]) for r in csv.DictReader(StringIO(content.decode("utf-8-sig")), delimiter=";") if r["tipo"] == "A" and r["inativada"] == "nao"}
        referenced = set()
        for query in ["SELECT bank_code,default_in,default_out FROM accounts", "SELECT code FROM rules", "SELECT code FROM movements"]:
            for row in db().execute(query):
                referenced.update(row)
        if not referenced.issubset(codes):
            raise InputError("O novo plano não contém todas as contas já usadas nos cadastros e lotes. Nenhuma alteração foi feita.")
        PRIVATE_CHART.parent.mkdir(parents=True, exist_ok=True)
        temporary = PRIVATE_CHART.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(PRIVATE_CHART)
        flash(f"Plano local carregado: {count} contas. Ele fica em data/, fora do código versionado.", "success")
        return redirect(url_for("home"))

    @app.post("/accounts")
    def add_account():
        client = db().execute("SELECT id FROM clients WHERE id=?", (request.form.get("client_id"),)).fetchone()
        name, number = request.form.get("name", "").strip(), request.form.get("number", "").strip()
        if not client or not name or not account_digits(number):
            raise InputError("Selecione o cliente, informe o nome e o número da conta com dígito.")
        bank = validate_code(request.form.get("bank_code"))
        if not chart()[bank]["conta"].startswith("1.1.2.04."):
            raise InputError("Selecione uma conta analítica do grupo Bancos Conta Corrente.")
        default_in = validate_code(request.form.get("default_in", 106), bank)
        default_out = validate_code(request.form.get("default_out", 106), bank)
        with db():
            db().execute("INSERT INTO accounts(client_id,name,number,bank_code,default_in,default_out) VALUES(?,?,?,?,?,?)", (client[0], name, number, bank, default_in, default_out))
        flash("Conta cadastrada. Regras de classificação serão exclusivas desta conta e cliente.", "success")
        return redirect(url_for("home"))

    def get_account(account_id):
        item = db().execute("SELECT a.*,c.name client_name FROM accounts a JOIN clients c ON c.id=a.client_id WHERE a.id=?", (account_id,)).fetchone()
        if not item:
            abort(404)
        return item

    @app.get("/accounts/<int:account_id>")
    def account_page(account_id):
        return render_template("account.html", account=get_account(account_id), rules=db().execute("SELECT * FROM rules WHERE account_id=? ORDER BY id DESC", (account_id,)).fetchall())

    @app.post("/accounts/<int:account_id>/rules")
    def add_rule(account_id):
        account = get_account(account_id)
        pattern = normalize(request.form.get("pattern", ""))
        kind, direction = request.form.get("kind"), request.form.get("direction")
        if not pattern or kind not in ("exact", "contains") or direction not in ("entrada", "saida"):
            raise InputError("Preencha o texto, o tipo e o sentido da regra.")
        code = validate_code(request.form.get("code"), account["bank_code"])
        with db():
            db().execute("INSERT OR IGNORE INTO rules(account_id,kind,pattern,direction,code) VALUES(?,?,?,?,?)", (account_id, kind, pattern, direction, code))
        flash("Regra salva para próximas importações. Lotes existentes mantêm a revisão realizada.", "success")
        return redirect(url_for("account_page", account_id=account_id))

    @app.post("/accounts/<int:account_id>/rules/<int:rule_id>/delete")
    def delete_rule(account_id, rule_id):
        get_account(account_id)
        with db():
            db().execute("DELETE FROM rules WHERE id=? AND account_id=?", (rule_id, account_id))
        return redirect(url_for("account_page", account_id=account_id))

    @app.post("/accounts/<int:account_id>/learn")
    def learn(account_id):
        account = get_account(account_id)
        upload = request.files.get("file")
        if not upload or not upload.filename.lower().endswith(".xlsx"):
            raise InputError("Envie uma planilha conciliada XLSX no layout Makro.")
        try:
            rules, count = learn_workbook(upload.read(), account["bank_code"])
        except InputError:
            raise
        except Exception as exc:
            raise InputError("A planilha não pôde ser lida. Confira o formato XLSX.") from exc
        with db():
            for kind, pattern, direction, code in rules:
                db().execute("INSERT OR IGNORE INTO rules(account_id,kind,pattern,direction,code) VALUES(?,?,?,?,?)", (account_id, kind, pattern, direction, code))
        flash(f"{count} lançamentos analisados; {len(rules)} regras exatas registradas. Conflitos irão para 106, sem substituir regras anteriores.", "success")
        return redirect(url_for("account_page", account_id=account_id))

    @app.post("/import")
    def import_file():
        account = get_account(request.form.get("account_id"))
        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise InputError("Selecione o extrato.")
        content = upload.read()
        password = request.form.get("password", "")
        try:
            statement = read_statement(content, upload.filename, password, {k: request.form.get("column_" + k, "") for k in ("date", "description", "value")})
        except InputError:
            raise
        except Exception as exc:
            raise InputError("Não foi possível interpretar o arquivo. Verifique o formato e o mapeamento de colunas.") from exc
        if statement.bank_account and account_digits(statement.bank_account) != account_digits(account["number"]):
            raise InputError("A conta identificada no extrato difere da conta selecionada. Confira o cliente e o número, incluindo o dígito.")
        start = parse_date(request.form["start"]) if request.form.get("start") else min(m.date for m in statement.movements)
        end = parse_date(request.form["end"]) if request.form.get("end") else max(m.date for m in statement.movements)
        if start > end:
            raise InputError("A data inicial deve ser anterior ou igual à final.")
        items = [m for m in statement.movements if start <= m.date <= end]
        if not items:
            raise InputError("Não há movimentos no período selecionado.")
        fingerprint = hashlib.sha256(content).hexdigest()
        filename = Path(upload.filename).name
        if password:
            filename = filename.replace(password, "[protegido]")
        if db().execute("SELECT id FROM batches WHERE account_id=? AND source_hash=? AND start=? AND end=?", (account["id"], fingerprint, start.isoformat(), end.isoformat())).fetchone():
            raise InputError("Este arquivo e período já foram importados para esta conta. Abra o lote existente.")
        rules = db().execute("SELECT * FROM rules WHERE account_id=?", (account["id"],)).fetchall()
        with db():
            batch_id = db().execute("INSERT INTO batches(account_id,source_hash,filename,layout,start,end,warnings) VALUES(?,?,?,?,?,?,?)", (account["id"], fingerprint, filename, statement.layout, start.isoformat(), end.isoformat(), json.dumps(statement.warnings, ensure_ascii=False))).lastrowid
            for movement in items:
                code, reason = classify(movement, rules, account["default_in"], account["default_out"])
                # Suspected overlaps stay visible; legitimate equal movements within the same source are retained.
                previous = db().execute("SELECT m.description FROM movements m JOIN batches b ON b.id=m.batch_id WHERE b.account_id=? AND b.id<>? AND m.date=? AND m.cents=?", (account["id"], batch_id, movement.date.isoformat(), movement.cents)).fetchall()
                duplicate = any(normalize(r[0]) == normalize(movement.description) for r in previous)
                db().execute("INSERT INTO movements(batch_id,date,book_date,description,cents,document,code,reason,duplicate,include_row) VALUES(?,?,?,?,?,?,?,?,?,?)", (batch_id, movement.date.isoformat(), movement.book_date.isoformat() if movement.book_date else None, movement.description, movement.cents, movement.document, code, reason, int(duplicate), int(not duplicate)))
        flash(f"{len(items)} movimentos importados. Revise a classificação e os possíveis repetidos.", "success")
        return redirect(url_for("batch_page", batch_id=batch_id))

    def get_batch(batch_id):
        batch = db().execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not batch:
            abort(404)
        return batch, get_account(batch["account_id"])

    @app.get("/batches/<int:batch_id>")
    def batch_page(batch_id):
        batch, account = get_batch(batch_id)
        rows = db().execute("SELECT * FROM movements WHERE batch_id=? ORDER BY id", (batch_id,)).fetchall()
        included = [r for r in rows if r["include_row"]]
        return render_template("batch.html", batch=batch, account=account, rows=rows, warnings=json.loads(batch["warnings"]),
            incoming=sum(r["cents"] for r in included if r["cents"] > 0), outgoing=-sum(r["cents"] for r in included if r["cents"] < 0),
            pending=sum(r["code"] == 106 for r in included), selected=len(included))

    def save_review(batch_id, account):
        rows = db().execute("SELECT * FROM movements WHERE batch_id=?", (batch_id,)).fetchall()
        updates = []
        for row in rows:
            code = validate_code(request.form.get(f"code_{row['id']}", row["code"]), account["bank_code"])
            updates.append((code, int(f"include_{row['id']}" in request.form), row["id"]))
        with db():
            for code, include, movement_id in updates:
                db().execute("UPDATE movements SET reason=CASE WHEN code<>? THEN 'Classificação revisada' ELSE reason END,code=?,include_row=?,reviewed=1 WHERE id=?", (code, code, include, movement_id))

    @app.post("/batches/<int:batch_id>/review")
    def review(batch_id):
        batch, account = get_batch(batch_id)
        save_review(batch_id, account)
        flash("Revisão salva. Movimentos na conta 106 continuam como pendências.", "success")
        return redirect(url_for("batch_page", batch_id=batch_id))

    @app.post("/batches/<int:batch_id>/export")
    def export(batch_id):
        batch, account = get_batch(batch_id)
        save_review(batch_id, account)
        rows = db().execute("SELECT * FROM movements WHERE batch_id=? AND include_row=1 ORDER BY id", (batch_id,)).fetchall()
        return send_file(export_workbook(rows, account["bank_code"]), download_name=f"Makro_{batch_id}_{batch['start']}_{batch['end']}.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.get("/health")
    def health():
        db().execute("SELECT 1").fetchone()
        return {"status": "ok", "application": "conciliador-makro"}

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
