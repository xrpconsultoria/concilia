"""Leitores adicionais de PDF, isolados dos layouts já suportados."""

import calendar
from datetime import date
import re

from .domain import InputError, Movement, Statement, money, normalize, parse_date

AMOUNT = r"-?\d[\d.]*,\d{2}"
DATE = r"\d{2}/\d{2}/\d{4}"


def _one(values, label):
    values = set(values)
    if len(values) != 1:
        raise InputError(f"Não foi possível identificar {label} de forma única no extrato.")
    return next(iter(values))


def _sicredi_amounts(line, columns):
    values = {}
    for match in re.finditer(AMOUNT, line):
        closest = min(columns, key=lambda column: abs(columns[column] - match.end()))
        if abs(columns[closest] - match.end()) <= 1:
            if closest in values:
                raise InputError("Sicredi: valores sobrepostos em uma coluna; confira o layout.")
            values[closest] = (money(match[0]), match.start())
        elif match.end() > columns["debit"] - 20:
            raise InputError("Sicredi: um valor está fora das colunas reconhecidas; nenhuma linha foi importada.")
    return values


def read_sicredi(text):
    """Read the monospaced Documento/Histórico/Débito/Crédito/Saldo report."""
    periods = re.findall(r"PER[IÍ]ODO:\s*DE\s*(\d{2})/(\d{4})\s+A\s+(\d{2})/(\d{4})", text, re.I)
    begin_month, begin_year, end_month, end_year = map(int, _one(periods, "o período Sicredi"))
    try:
        begin = date(begin_year, begin_month, 1)
        end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    except ValueError as exc:
        raise InputError("Sicredi: período inválido.") from exc
    if begin > end:
        raise InputError("Sicredi: o período inicial é posterior ao final.")
    accounts = re.findall(r"^\s+.+?\s{2,}(\d{4,}-\d)\s*$", text, re.M)
    account = _one(accounts, "a conta Sicredi")
    movements, columns = [], {}
    running = None
    balance_checks = 0
    in_table = False
    totals = {}
    unusual_text = False
    for line in text.splitlines():
        header = re.search(r"DOCUMENTO\s+HIST[OÓ]RICO\s+D[EÉ]BITO\s+CR[EÉ]DITO\s+SALDO", line, re.I)
        if header:
            columns = {key: re.search(pattern, line, re.I).end() for key, pattern in [("debit", r"D[EÉ]BITO"), ("credit", r"CR[EÉ]DITO"), ("balance", r"SALDO")]}
            in_table = True
            continue
        summary = re.match(r"\s*(D[EÉ]BITOS|CR[EÉ]DITOS)\.+:\s*(" + AMOUNT + r")", line, re.I)
        if summary:
            key = "debit" if normalize(summary[1]).startswith(("DE", "DÉ")) else "credit"
            if key in totals and totals[key] != money(summary[2]):
                raise InputError("Sicredi: totais divergentes entre as páginas.")
            totals[key] = money(summary[2])
        closing = re.match(r"\s*SALDO ATUAL\.+:\s*(" + AMOUNT + r")", line, re.I)
        if closing:
            if running is None or running != money(closing[1]):
                raise InputError("Sicredi: os movimentos não fecham com o saldo atual.")
            balance_checks += 1
            in_table = False
            continue
        if not in_table:
            continue
        if re.match(r"\s*\*\*/\*\*/\*{4}", line):
            marker = re.sub(r"\s", "", line).upper()
            values = _sicredi_amounts(line, columns)
            if "balance" not in values or any(k in values for k in ("credit", "debit")):
                raise InputError("Sicredi: saldo de abertura ou transporte inválido.")
            if "SALDOANTERIOR" in marker:
                if running is not None:
                    raise InputError("Sicredi: mais de um saldo de abertura identificado.")
                running = values["balance"][0]
            elif "DETRANSPORTE" in marker:
                if running != values["balance"][0]:
                    raise InputError("Sicredi: o saldo de transporte não confere com a página anterior.")
                balance_checks += 1
            else:
                raise InputError("Sicredi: marcador de saldo não reconhecido.")
            continue
        dated = re.match(r"\s*(" + DATE + r")\s+", line)
        if dated:
            if running is None:
                raise InputError("Sicredi: saldo anterior ausente; não foi possível conferir os movimentos.")
            day = parse_date(dated[1])
            if not begin <= day <= end or (movements and day < movements[-1].date):
                raise InputError("Sicredi: movimento fora do período ou da ordem cronológica.")
            row = re.match(r"\s*" + DATE + r"\s+(\S+)\s+", line)
            if not row:
                raise InputError("Sicredi: documento ou histórico não reconhecido.")
            values = _sicredi_amounts(line, columns)
            sides = [key for key in ("debit", "credit") if key in values]
            if len(sides) != 1 or values[sides[0]][0] <= 0:
                raise InputError("Sicredi: cada movimento precisa ter um valor positivo em débito ou crédito.")
            side = sides[0]
            amount, amount_start = values[side]
            history = line[row.end():amount_start].strip()
            if not history:
                raise InputError("Sicredi: movimento sem histórico.")
            # Two-space gaps separate location/detail fields in this monospaced report.
            history = " — ".join(normalize(part) for part in re.split(r"\s{2,}", history))
            unusual_text = unusual_text or "¶" in history or "\ufffd" in history
            cents = amount if side == "credit" else -amount
            running += cents
            if "balance" in values:
                if running != values["balance"][0]:
                    raise InputError(f"Sicredi: os movimentos não fecham com o saldo de {day.strftime('%d/%m/%Y')}.")
                balance_checks += 1
            description = f"{history} — Documento {row[1]} — Sicredi, conta {account}"
            movements.append(Movement(day, description, cents, row[1]))
            continue
        stripped = line.strip()
        if not stripped or set(stripped) == {"="}:
            continue
        # Future entries and bank summaries are not posted transactions.
        if "|" in line or re.match(r"\s*(SALDO |BLOQUEIO |IOF |Custo |Taxa |Continua |Poderao |Ouvidoria |LIMITE)", line, re.I):
            in_table = False
            continue
        raise InputError("Sicredi: linha não reconhecida no histórico; confira o layout antes de importar.")
    for side, total in totals.items():
        actual = sum(abs(m.cents) for m in movements if (m.cents < 0) == (side == "debit"))
        if actual != total:
            raise InputError("Sicredi: total de débitos ou créditos não confere com os movimentos.")
    warnings = [f"Sicredi: {balance_checks} saldos conferidos; lançamentos futuros e resumos não foram importados."]
    if totals:
        warnings.append("Totais de débitos e créditos conferidos com o extrato completo, antes do filtro de período.")
    if unusual_text:
        warnings.append("O PDF contém caracteres incomuns em uma descrição (como ¶). A grafia foi preservada; confira essa descrição na revisão.")
    return Statement("Sicredi — débito e crédito", movements, account, warnings)


def read_cresol(text):
    """Read the daily-balance layout with signed BRL values and wrapped details."""
    start_text, end_text = _one(re.findall(r"Per[ií]odo de\s+(" + DATE + r")\s+a\s+(" + DATE + r")", text, re.I), "o período Cresol")
    begin, end = parse_date(start_text), parse_date(end_text)
    if begin > end:
        raise InputError("Cresol: período inicial posterior ao final.")
    account = _one(re.findall(r"Ag[eê]ncia\s+\d+\s+Conta\s+([\d.]+-\d)", text, re.I), "a conta Cresol")
    balances, movements = {}, []
    initial = None
    current = None
    active = False
    daily_date = None

    def finish():
        nonlocal current
        if current is None:
            return
        if len(current["documents"]) > 1:
            raise InputError("Cresol: mais de um documento identificado no mesmo movimento.")
        document = current["documents"][0] if current["documents"] else ""
        history = normalize(" ".join(current["description"]))
        desc = f"{history} — Documento {document or 'não informado'} — Cresol, conta {account}"
        movements.append(Movement(current["date"], desc, current["cents"], document))
        current = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "Lançamentos":
            active = True
            continue
        opening = re.fullmatch(r"Saldo Anterior:\s*([+-])\s*R\$\s*([\d.]+,\d{2})", stripped, re.I)
        if opening:
            finish()
            amount = money(opening[2]) * (-1 if opening[1] == "-" else 1)
            if initial is not None and initial != amount:
                raise InputError("Cresol: saldos anteriores divergentes entre as páginas.")
            initial = amount
            active = False
            continue
        if stripped.startswith("Consulta Posição"):
            finish()
            active = False
        if not active:
            continue
        daily = re.fullmatch(r"(" + DATE + r")\s+Saldo do Dia:\s*([+-])\s*R\$\s*([\d.]+,\d{2})", stripped, re.I)
        if daily:
            finish()
            daily_date = parse_date(daily[1])
            amount = money(daily[3]) * (-1 if daily[2] == "-" else 1)
            if not begin <= daily_date <= end or daily_date in balances and balances[daily_date] != amount:
                raise InputError("Cresol: saldo diário fora do período ou divergente entre páginas.")
            balances[daily_date] = amount
            continue
        dated = re.match(r"^" + DATE + r"(?:\s|$)", stripped)
        if dated:
            finish()
            row = re.fullmatch(r"(" + DATE + r")\s+(.+?)\s+([+-])\s*R\$\s*([\d.]+,\d{2})", stripped)
            if not row:
                raise InputError("Cresol: movimento sem descrição, sinal ou valor reconhecido.")
            day = parse_date(row[1])
            if not begin <= day <= end or day != daily_date:
                raise InputError("Cresol: movimento fora do período ou sem o saldo diário correspondente.")
            current = {"date": day, "description": [row[2]], "cents": money(row[4]) * (-1 if row[3] == "-" else 1), "documents": []}
            continue
        if current:
            if re.fullmatch(r"\d[\d.-]*", stripped):
                current["documents"].append(stripped)
            elif re.search(r"R\$|Saldo do Dia|Saldo Anterior", stripped, re.I):
                raise InputError("Cresol: valor ou saldo em uma linha fora do layout reconhecido.")
            else:
                current["description"].append(stripped)
        else:
            raise InputError("Cresol: linha não reconhecida na área de lançamentos.")
    finish()
    if initial is None or not balances:
        raise InputError("Cresol: saldo anterior ou saldos diários ausentes; não foi possível validar o arquivo.")
    # Stable sorting keeps separate legitimate equal entries and the original order within a day.
    movements.sort(key=lambda movement: movement.date)
    running = initial
    for day, balance in sorted(balances.items()):
        running += sum(m.cents for m in movements if m.date == day)
        if running != balance:
            raise InputError(f"Cresol: os movimentos não fecham com o saldo de {day.strftime('%d/%m/%Y')}.")
    account_balance = re.search(r"Saldo em Conta\s+Limite de Cr[eé]dito\s+Saldo Dispon[ií]vel\s+R\$\s*([\d.]+,\d{2})", text, re.I)
    if account_balance and running != money(account_balance[1]):
        raise InputError("Cresol: o saldo final não confere com o resumo da conta.")
    return Statement("Cresol — saldos diários", movements, account, [f"Cresol: {len(balances)} saldos diários conferidos; movimentos organizados por data.", "Créditos de estorno foram preservados como entradas; não foram compensados ou removidos."])
