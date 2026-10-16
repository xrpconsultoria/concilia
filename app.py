import hashlib
import csv
from io import StringIO
import json
import os
from pathlib import Path
import secrets

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from conciliador.domain import InputError, RuleClassifier, account_digits, classify, normalize, parse_date
from conciliador.makro import PRIVATE_CHART, chart, export_workbook, learn_workbook, prepare_private_chart, validate_code
from conciliador.readers import read_statement
from conciliador.store import connect

ROOT = Path(__file__).resolve().parent


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024 * 1024, MAX_FORM_PARTS=50000, MAX_FORM_MEMORY_SIZE=4 * 1024 * 1024, DATABASE=str(ROOT / "data" / "conciliador.sqlite3"), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
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

    @app.template_filter("brdate")
    def brdate(value):
        return parse_date(value).strftime("%d/%m/%Y")

    def wants_json():
        return request.accept_mimetypes.best == "application/json"

    def go_to(endpoint, **values):
        target = url_for(endpoint, **values)
        return {"redirect": target} if wants_json() else redirect(target)

    def error_target():
        account_id = request.view_args.get("account_id") if request.view_args else None
        if request.endpoint == "import_file":
            return url_for("new_reconciliation", account_id=request.form.get("account_id", ""))
        if request.endpoint in ("review", "export"):
            return url_for("batch_page", batch_id=request.view_args["batch_id"])
        if request.endpoint == "setup_account":
            return url_for("setup_account")
        if request.endpoint == "edit_account":
            return url_for("edit_account", account_id=account_id)
        if account_id:
            return url_for("account_page", account_id=account_id)
        if request.endpoint in ("upload_chart", "add_client", "add_account"):
            return url_for("setup_account") if request.form.get("destination") == "setup" else url_for("settings")
        return url_for("home")

    @app.errorhandler(InputError)
    def input_error(exc):
        if wants_json():
            result = {"error": str(exc)}
            if exc.account_mismatch and request.endpoint == "import_file" and request.form.get("account_id", "").isdigit():
                result["account_url"] = url_for("edit_account", account_id=int(request.form["account_id"]))
            return result, 422
        flash(str(exc), "error")
        return redirect(error_target())

    @app.errorhandler(RequestEntityTooLarge)
    def too_big(exc):
        message = "Arquivo maior que 16 MB. Divida o extrato em arquivos menores."
        if request.endpoint in ("review", "export"):
            message = "A revisão excedeu o limite de campos ou de tamanho do envio. Reenvie o extrato em períodos menores para gerar lotes menores. Os dados já salvos continuam disponíveis."
        if wants_json():
            return {"error": message}, 413
        flash(message, "error")
        return redirect(url_for("home"))

    def all_accounts():
        return db().execute("SELECT a.*,c.name client_name FROM accounts a JOIN clients c ON c.id=a.client_id ORDER BY c.name,a.name").fetchall()

    def all_batches():
        return db().execute("""SELECT b.*,a.name account_name,c.name client_name,
            (SELECT COUNT(*) FROM movements m WHERE m.batch_id=b.id) total,
            (SELECT COUNT(*) FROM movements m WHERE m.batch_id=b.id AND m.code=106 AND m.include_row=1) pending
            FROM batches b JOIN accounts a ON a.id=b.account_id JOIN clients c ON c.id=a.client_id ORDER BY b.id DESC""").fetchall()

    @app.get("/")
    def home():
        return render_template("home.html", clients=db().execute("SELECT * FROM clients ORDER BY name").fetchall(), accounts=all_accounts(), batches=all_batches())

    @app.get("/new")
    def new_reconciliation():
        accounts = all_accounts()
        if not accounts:
            return redirect(url_for("setup_account"))
        account_id = request.args.get("account_id", type=int)
        account = get_account(account_id) if account_id else None
        rules_count = db().execute("SELECT COUNT(*) FROM rules WHERE account_id=?", (account_id,)).fetchone()[0] if account else 0
        return render_template("new.html", accounts=accounts, clients=db().execute("SELECT * FROM clients ORDER BY name").fetchall(), account=account, rules_count=rules_count, active_step=2 if account else 1)

    @app.get("/settings")
    def settings():
        return render_template("settings.html", accounts=all_accounts(), clients=db().execute("SELECT * FROM clients ORDER BY name").fetchall())

    @app.route("/setup", methods=["GET", "POST"])
    def setup_account():
        if request.method == "GET":
            return render_template("setup.html", clients=db().execute("SELECT * FROM clients ORDER BY name").fetchall())
        name, number = request.form.get("account_name", "").strip(), request.form.get("number", "").strip()
        if not name or len(name) > 160 or not account_digits(number):
            raise InputError("Informe o banco e o número completo da conta, incluindo o dígito.")
        bank = validate_code(request.form.get("bank_code"))
        if not chart()[bank]["conta"].startswith("1.1.2.04."):
            raise InputError("Selecione a conta bancária correspondente no plano do Makro.")
        client_id = request.form.get("client_id")
        client = db().execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone() if client_id else None
        client_name = request.form.get("client_name", "").strip()
        if client_id and not client:
            raise InputError("Selecione um cliente válido.")
        if not client and (not client_name or len(client_name) > 160):
            raise InputError("Informe o nome ou razão social do cliente.")
        if client:
            existing = db().execute("SELECT * FROM accounts WHERE client_id=?", (client["id"],)).fetchall()
            same = next((a for a in existing if account_digits(a["number"]) == account_digits(number)), None)
            if same:
                flash("Essa conta já está cadastrada. Continue enviando o extrato.", "success")
                return go_to("new_reconciliation", account_id=same["id"])
        with db():
            if not client:
                client_id = db().execute("INSERT INTO clients(name,tax_id) VALUES(?,?)", (client_name, request.form.get("tax_id", "").strip())).lastrowid
            account_id = db().execute("INSERT INTO accounts(client_id,name,number,bank_code,default_in,default_out) VALUES(?,?,?,?,106,106)", (client_id, name, number, bank)).lastrowid
        flash("Cliente e conta prontos. Agora envie o extrato bancário.", "success")
        return go_to("new_reconciliation", account_id=account_id)

    @app.route("/accounts/<int:account_id>/edit", methods=["GET", "POST"])
    def edit_account(account_id):
        account = get_account(account_id)
        if request.method == "GET":
            return render_template("edit_account.html", account=account)
        name, number = request.form.get("name", "").strip(), request.form.get("number", "").strip()
        if not name or not account_digits(number):
            raise InputError("Informe o banco e o número completo da conta, incluindo o dígito.")
        bank = validate_code(request.form.get("bank_code"))
        if not chart()[bank]["conta"].startswith("1.1.2.04."):
            raise InputError("Selecione uma conta bancária do plano do Makro.")
        if bank != account["bank_code"] or account_digits(number) != account_digits(account["number"]):
            if db().execute("SELECT 1 FROM batches WHERE account_id=?", (account_id,)).fetchone():
                raise InputError("Esta conta já tem conciliações. Cadastre uma nova conta para manter o histórico vinculado ao banco correto.")
            if bank != account["bank_code"] and db().execute("SELECT 1 FROM rules WHERE account_id=?", (account_id,)).fetchone():
                raise InputError("Esta conta já tem regras. Para usar outro código bancário, cadastre uma nova conta.")
        default_in = validate_code(request.form.get("default_in", account["default_in"]), bank)
        default_out = validate_code(request.form.get("default_out", account["default_out"]), bank)
        with db():
            db().execute("UPDATE accounts SET name=?,number=?,bank_code=?,default_in=?,default_out=? WHERE id=?", (name, number, bank, default_in, default_out, account_id))
        flash("Cadastro atualizado. Continue enviando o extrato.", "success")
        return go_to("new_reconciliation", account_id=account_id)

    @app.post("/clients")
    def add_client():
        name = request.form.get("name", "").strip()
        if not name or len(name) > 160:
            raise InputError("Informe o nome do cliente, com até 160 caracteres.")
        with db():
            db().execute("INSERT INTO clients(name,tax_id) VALUES(?,?)", (name, request.form.get("tax_id", "").strip()))
        flash("Cliente cadastrado.", "success")
        return go_to("settings")

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
        flash(f"Plano de contas salvo: {count} contas disponíveis.", "success")
        if request.form.get("destination") == "setup":
            flash("Próximo passo: cadastre o cliente e a conta bancária.", "success")
        return go_to("setup_account" if request.form.get("destination") == "setup" else "settings")

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
        return go_to("new_reconciliation", account_id=db().execute("SELECT last_insert_rowid()").fetchone()[0])

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
        return go_to("account_page", account_id=account_id)

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
        flash(f"Classificações salvas: {count} linhas analisadas e {len(rules)} regras exatas registradas. Próximo passo: enviar o extrato bancário.", "success")
        return go_to("new_reconciliation", account_id=account_id)

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
            raise InputError("O arquivo não pôde ser processado. Para PDF, gere novamente o extrato completo no banco ou envie OFX; para tabela, confira as colunas de data, descrição e valor com sinal. Se persistir, informe o formato, o banco e o período para analisarmos esse modelo.") from exc
        if statement.bank_account and account_digits(statement.bank_account) != account_digits(account["number"]):
            raise InputError(f"A conta identificada no extrato ({statement.bank_account}) difere da conta selecionada ({account['number']}). Confira o cadastro ou escolha a conta correta.", account_mismatch=True)
        start = parse_date(request.form["start"]) if request.form.get("start") else min(m.date for m in statement.movements)
        end = parse_date(request.form["end"]) if request.form.get("end") else max(m.date for m in statement.movements)
        if start > end:
            raise InputError("A data inicial deve ser anterior ou igual à final.")
        items = [m for m in statement.movements if start <= m.date <= end]
        if not items:
            raise InputError("Não há movimentos no período selecionado.")
        if len(items) > 20000:
            raise InputError(f"O período selecionado contém {len(items)} movimentos. O limite por conciliação é 20.000; preencha De/Até com um período menor ou gere extratos separados no banco.")
        fingerprint = hashlib.sha256(content).hexdigest()
        filename = Path(upload.filename).name
        if password:
            filename = filename.replace(password, "[protegido]")
        existing = db().execute("SELECT id FROM batches WHERE account_id=? AND source_hash=? AND start=? AND end=?", (account["id"], fingerprint, start.isoformat(), end.isoformat())).fetchone()
        if existing:
            flash("Este arquivo e período já foram importados. Abrimos a conciliação existente para você revisar e baixar o Excel.", "success")
            return go_to("batch_page", batch_id=existing["id"])
        rules = RuleClassifier(db().execute("SELECT * FROM rules WHERE account_id=?", (account["id"],)).fetchall())
        previous_rows = db().execute("SELECT m.date,m.cents,m.description FROM movements m JOIN batches b ON b.id=m.batch_id WHERE b.account_id=? AND m.date>=? AND m.date<=?", (account["id"], start.isoformat(), end.isoformat())).fetchall()
        previous_keys = {(row["date"], row["cents"], normalize(row["description"])) for row in previous_rows}
        with db():
            batch_id = db().execute("INSERT INTO batches(account_id,source_hash,filename,layout,start,end,warnings) VALUES(?,?,?,?,?,?,?)", (account["id"], fingerprint, filename, statement.layout, start.isoformat(), end.isoformat(), json.dumps(statement.warnings, ensure_ascii=False))).lastrowid
            for movement in items:
                code, reason = classify(movement, rules, account["default_in"], account["default_out"])
                # Suspected overlaps stay visible; legitimate equal movements within the same source are retained.
                duplicate = (movement.date.isoformat(), movement.cents, normalize(movement.description)) in previous_keys
                db().execute("INSERT INTO movements(batch_id,date,book_date,description,cents,document,code,reason,duplicate,include_row) VALUES(?,?,?,?,?,?,?,?,?,?)", (batch_id, movement.date.isoformat(), movement.book_date.isoformat() if movement.book_date else None, movement.description, movement.cents, movement.document, code, reason, int(duplicate), int(not duplicate)))
        flash(f"{len(items)} movimentos importados. Revise a classificação e os possíveis repetidos.", "success")
        return go_to("batch_page", batch_id=batch_id)

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
        return render_template("batch.html", batch=batch, account=account, rows=rows, warnings=json.loads(batch["warnings"]), active_step=3,
            incoming=sum(r["cents"] for r in included if r["cents"] > 0), outgoing=-sum(r["cents"] for r in included if r["cents"] < 0),
            pending=sum(r["code"] == 106 for r in included), selected=len(included))

    def save_review(batch_id, account):
        rows = db().execute("SELECT * FROM movements WHERE batch_id=?", (batch_id,)).fetchall()
        updates = []
        changed = False
        accounts = chart()
        for row in rows:
            code = validate_code(request.form.get(f"code_{row['id']}", row["code"]), account["bank_code"], accounts=accounts)
            include = int(f"include_{row['id']}" in request.form)
            changed = changed or code != row["code"] or include != row["include_row"]
            updates.append((code, include, row["id"]))
        with db():
            for code, include, movement_id in updates:
                db().execute("UPDATE movements SET reason=CASE WHEN code<>? THEN 'Classificação revisada' ELSE reason END,code=?,include_row=?,reviewed=1 WHERE id=?", (code, code, include, movement_id))
            if changed:
                db().execute("UPDATE batches SET exported_at=NULL WHERE id=?", (batch_id,))

    @app.post("/batches/<int:batch_id>/review")
    def review(batch_id):
        batch, account = get_batch(batch_id)
        save_review(batch_id, account)
        flash("Revisão salva. Movimentos na conta 106 continuam como pendências.", "success")
        return go_to("batch_page", batch_id=batch_id)

    @app.post("/batches/<int:batch_id>/export")
    def export(batch_id):
        batch, account = get_batch(batch_id)
        save_review(batch_id, account)
        rows = db().execute("SELECT * FROM movements WHERE batch_id=? AND include_row=1 ORDER BY id", (batch_id,)).fetchall()
        output = export_workbook(rows, account["bank_code"])
        with db():
            db().execute("UPDATE batches SET exported_at=CURRENT_TIMESTAMP WHERE id=?", (batch_id,))
        return send_file(output, download_name=f"Makro_{batch_id}_{batch['start']}_{batch['end']}.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.get("/health")
    def health():
        db().execute("SELECT 1").fetchone()
        return {"status": "ok", "application": "conciliador-makro"}

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
