"""Layouts de conta corrente com conferência financeira, sem inferir classificação."""

import calendar
from datetime import date
import re

from .bank_layouts import _one
from .domain import InputError, Movement, Statement, money, normalize, parse_date

DATE = r"\d{2}/\d{2}/\d{4}"
AMOUNT = r"\d[\d.]*,\d{2}"
MONTHS = {name: index for index, name in enumerate(
    ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], 1)}
MONTHS.update({name: index for index, name in enumerate(
    ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"], 1)})


def _date(day, month, year):
    try:
        return date(int(year), MONTHS[normalize(month)], int(day))
    except (ValueError, KeyError) as exc:
        raise InputError("Data ou mês não reconhecido no extrato.") from exc


def _period(text, pattern, label):
    first, last = _one(re.findall(pattern, text, re.I), f"o período {label}")
    start, end = parse_date(first), parse_date(last)
    if start > end:
        raise InputError(f"{label}: período invertido.")
    return start, end


def _summary(text, label, signed=False):
    pattern = re.escape(label) + r"\s*(?:R\$\s*)?([+-]?)\s*(?:R\$\s*)?(" + AMOUNT + r")"
    values = re.findall(pattern, text, re.I)
    sign, value = _one(values, label)
    return money(value) * (-1 if signed and sign == "-" else 1)


def _totals(movements, incoming, outgoing, label):
    if sum(m.cents for m in movements if m.cents > 0) != incoming or sum(-m.cents for m in movements if m.cents < 0) != outgoing:
        raise InputError(f"{label}: totais de entradas ou saídas não conferem; nenhuma linha foi importada.")


def read_bb(text):
    account = _one(re.findall(r"Ag[eê]ncia:\s*[\d-]+\s+Conta:\s*([\d.-]+)", text, re.I), "a conta Banco do Brasil")
    movements, current = [], None
    pending_history = None
    history_column = None
    running = None
    checks, repaired, last_checked = 0, False, 0
    page, last_date = 1, None

    def fail(message):
        day = current["date"] if current else last_date
        location = f"página {page}" + (f", data {day}" if day else "")
        raise InputError(f"Banco do Brasil — {location}: {message} Nenhum lançamento foi importado. Gere novamente o PDF completo pelo banco ou envie OFX.")

    def finish():
        nonlocal current, running, last_date
        if current is None:
            return
        try:
            day = parse_date(current["date"])
        except InputError:
            fail("a data do movimento está incompleta ou inválida.")
        if current["amount"] is None or not current["history"]:
            fail("o movimento está incompleto; confira data, histórico e valor.")
        history = " — ".join(normalize(part) for part in current["history"])
        amount = current["amount"]
        if history.startswith("SALDO ANTERIOR"):
            if running is not None:
                fail("o saldo anterior está repetido.")
            running = amount
        else:
            if running is None or movements and day < movements[-1].date:
                fail("o saldo anterior está ausente ou as datas estão fora de ordem.")
            running += amount
            movements.append(Movement(day, history, amount, current["document"]))
        last_date = current["date"]
        current = None

    lines = [(number, line) for number, content in enumerate(text.split("\f"), 1) for line in content.splitlines()]
    for page, line in lines:
        header = re.search(r"Dia\s+Lote\s+Documento\s+Hist[oó]rico\s+Valor", line, re.I)
        if header:
            history_column = re.search(r"Hist[oó]rico", line, re.I).start()
            continue
        if history_column is None or not line.strip():
            continue
        if re.search(r"Total Aplica[çc][õo]es", line, re.I):
            if pending_history:
                fail("há um histórico sem a linha de data e valor correspondente.")
            finish()
            history_column = None
            continue
        if re.match(r"\s*(Extrato de Conta|Cliente\s|Ag[eê]ncia:|Lan[çc]amentos\s*$)", line, re.I):
            continue
        if re.match(r"\s*Per[ií]odo:", line, re.I) and re.search(r"Ag[eê]ncia:\s*[\d-]+\s+Conta:\s*[\d.-]+\s*$", line, re.I):
            continue
        # BB vertically centers date/value beside multiline histories. With
        # three history lines, the Pix title can appear ABOVE the dated row.
        # Keep only these explicit operation titles pending; never skip an
        # arbitrary unrecognized line or attach the title to the previous Pix.
        title = line[history_column:].strip()
        if not line[:history_column].strip() and re.fullmatch(r"Pix\s*-\s*(?:Recebido|Enviado|Agendamento)", title, re.I):
            if pending_history:
                fail("há dois históricos sem a linha de data e valor correspondente.")
            finish()
            pending_history = title
            continue
        # One known BB page break splits the last digit of a year into the next page.
        fragment = re.match(r"^\s*(\d)\s+", line)
        if fragment and current and re.fullmatch(r"\d{2}/\d{2}/\d{3}", current["date"]):
            current["date"] += fragment[1]
            repaired = True
        elif re.match(r"\s*(?:00/00/0000|" + DATE + r")\s+.*(?:Saldo do dia|S A L D O)\s+", line, re.I):
            if pending_history:
                fail("há um histórico sem movimento antes do saldo.")
            finish()
            amount = re.search(r"(" + AMOUNT + r")\s*\(([+-])\)\s*$", line)
            if not amount or running != money(amount[1]) * (-1 if amount[2] == "-" else 1):
                fail("os movimentos não fecham com o saldo diário/final.")
            checks += 1
            last_checked = len(movements)
            continue
        else:
            dated = re.match(r"\s*(\d{2}/\d{2}/\d{3,4})\s+", line)
            if dated:
                finish()
                current = {"date": dated[1], "history": [pending_history] if pending_history else [], "amount": None, "document": ""}
                pending_history = None
            elif current is None:
                fail("há uma linha não reconhecida na tabela de lançamentos.")
        value = re.search(r"(" + AMOUNT + r")\s*\(([+-])\)\s*$", line)
        if value:
            if current["amount"] is not None:
                fail("há dois valores no mesmo movimento.")
            current["amount"] = money(value[1]) * (-1 if value[2] == "-" else 1)
        prefix = line[:history_column].split()
        if len(prefix) >= 2 and prefix[-1].isdigit() and prefix[-2].isdigit():
            current["document"] = prefix[-1]
        history = line[history_column:value.start() if value else None].strip()
        if history:
            current["history"].append(history)
    if pending_history:
        fail("há um histórico sem a linha de data e valor correspondente.")
    finish()
    if not movements or not checks or last_checked != len(movements):
        fail("faltam movimentos ou saldos para conferir o extrato completo.")
    warnings = [f"Banco do Brasil: {checks} saldos diários/final conferidos. Datas de efetivação da coluna Dia preservadas.", "Descrições completas do PDF foram preservadas. Textos simplificados ou completados na planilha de aprendizado podem exigir regras por trecho ou revisão na 106."]
    if repaired:
        warnings.append("Banco do Brasil: uma data dividida entre páginas foi recomposta com o dígito impresso na página seguinte.")
    return Statement("Banco do Brasil — conta corrente", movements, account, warnings)


def read_inter(text):
    start, end = _period(text, r"Per[ií]odo:\s*(" + DATE + r")\s+a\s+(" + DATE + r")", "Inter")
    account = _one(re.findall(r"Banco Inter,.*?Conta:\s*([\d.-]+)", text, re.I), "a conta Inter")
    movements, day = [], None
    expected_daily, running = None, None
    checks = 0

    def check_day():
        if day is not None and (not movements or movements[-1].date != day or running != expected_daily):
            raise InputError("Inter: movimentos não fecham com o saldo do dia.")

    for line in text.splitlines():
        header = re.match(r"\s*(\d{1,2}) de (\w+) de (\d{4})\s+Saldo do dia:\s*R\$\s*(-?" + AMOUNT + r")", line, re.I)
        if header:
            check_day()
            day = _date(*header.groups()[:3])
            if not start <= day <= end or movements and day < movements[-1].date:
                raise InputError("Inter: data fora do período ou da ordem cronológica.")
            expected_daily = money(header[4])
            continue
        if day is None:
            continue
        row = re.fullmatch(r'\s*(.+?):\s*"(.+)"\s+(-?R\$\s*' + AMOUNT + r")\s+(-?R\$\s*" + AMOUNT + r")\s*", line)
        if row:
            amount, balance = money(row[3]), money(row[4])
            event = normalize(row[1])
            if ("RECEBIDO" in event and amount <= 0) or ("ENVIADO" in event and amount >= 0):
                raise InputError("Inter: sinal do valor diverge do sentido da transferência.")
            if running is not None and running + amount != balance:
                raise InputError("Inter: saldo por transação não confere.")
            running = balance
            details = row[2].strip()
            # Preserve the source's Cp prefix used by existing learned workbooks.
            details = "Cp :" + normalize(details[4:]) if details.startswith("Cp :") else normalize(details)
            description = f"{normalize(row[1])} — {details} — Banco Inter, conta {account}"
            movements.append(Movement(day, description, amount))
            checks += 1
        elif "R$" in line or re.match(r"\s*(Pix|Transfer[eê]ncia|Pagamento|Compra)\b", line, re.I):
            raise InputError("Inter: linha financeira fora do layout reconhecido.")
    check_day()
    if not movements:
        raise InputError("Inter: nenhuma transação reconhecida.")
    return Statement("Banco Inter — saldo por transação", movements, account, [f"Inter: {checks} saldos por transação e saldos diários conferidos. O saldo de abertura é deduzido da primeira transação; não consta explicitamente nesse modelo.", "O saldo total do cabeçalho pode ser o saldo na emissão. A conferência usa os saldos das transações do período."])


def read_cora(text):
    start, end = _period(text, r"Extrato do per[ií]odo\s+(" + DATE + r")\s+a\s+(" + DATE + r")", "Cora")
    account = _one(re.findall(r"Ag[eê]ncia:\s*\d+\s*-\s*Conta:\s*([\d.-]+)", text, re.I), "a conta Cora")
    initial = _summary(text, "Saldo inicial disponível", True)
    final = _summary(text, "Saldo final disponível", True)
    incoming, outgoing = _summary(text, "Total de entradas"), _summary(text, "Total de saídas")
    movements, balances, day = [], {}, None
    active = False
    company_headers = {page.strip().splitlines()[0].strip() for page in text.split("\f") if page.strip()}
    for line in text.splitlines():
        if line.strip() == "Transações":
            active = True
            continue
        daily = re.fullmatch(r"\s*(" + DATE + r")\s+Saldo do dia\s+R\$\s*(-?" + AMOUNT + r")\s*", line, re.I)
        if daily:
            day = parse_date(daily[1])
            if not start <= day <= end or day in balances:
                raise InputError("Cora: data fora do período ou saldo diário repetido.")
            balances[day] = money(daily[2])
            continue
        if not active or not line.strip():
            continue
        if re.match(r"\s*(Cora SCFI -|Ouvidoria:|Extrato gerado|CNPJ |Ag[eê]ncia:)", line, re.I):
            continue
        if line.strip() in company_headers:
            continue
        row = re.fullmatch(r"\s*(.+?)\s{2,}(.+?)\s{2,}([+-])\s*R\$\s*(" + AMOUNT + r")\s*", line)
        if not row or day is None:
            raise InputError("Cora: linha de transação incompleta ou fora das colunas reconhecidas.")
        description = " ".join(row[2].split())
        movements.append(Movement(day, description, money(row[4]) * (-1 if row[3] == "-" else 1)))
    _totals(movements, incoming, outgoing, "Cora")
    running = initial
    for day, balance in sorted(balances.items()):
        running += sum(m.cents for m in movements if m.date == day)
        if running != balance:
            raise InputError("Cora: movimentos não fecham com o saldo diário.")
    if not balances or running != final:
        raise InputError("Cora: saldo final não confere.")
    return Statement("Cora — transações e saldos diários", movements, account, [f"Cora: totais de entradas/saídas e {len(balances)} saldos diários conferidos. Ordem do extrato preservada, do mais recente para o mais antigo.", "Descrições usam favorecido e CPF/CNPJ da transação, conforme a planilha de aprendizado. Nomes truncados pelo banco são preservados."])


def read_nubank(text):
    account = _one(re.findall(r"CNPJ\s+[\d./-]+\s+Ag[eê]ncia\s+\d+\s+Conta\s+([\d.-]+)", text, re.I), "a conta Nubank")
    periods = re.findall(r"(\d{2}) DE (\w+) DE (\d{4})\s+a\s+(\d{2}) DE (\w+) DE (\d{4})", text, re.I)
    values = _one(periods, "o período Nubank")
    start, end = _date(*values[:3]), _date(*values[3:])
    if start > end:
        raise InputError("Nubank: período invertido.")
    # Summary occurs before the Movimentações section; daily totals are separate.
    summary, body = text.split("Movimentações", 1)
    initial, final = _summary(summary, "Saldo inicial", True), _summary(summary, "Saldo final do período", True)
    yield_cents = _summary(summary, "Rendimento líquido", True)
    incoming, outgoing = _summary(summary, "Total de entradas"), _summary(summary, "Total de saídas")
    movements, balances, daily_totals = [], {}, {}
    day, side, current = None, None, None

    def finish():
        nonlocal current
        if current:
            description = current["event"] + " — " + " ".join(current["details"])
            movements.append(Movement(current["day"], description, current["amount"]))
            current = None

    for line in body.splitlines():
        if re.match(r"\s*O saldo l[ií]quido", line, re.I):
            finish()
            break
        dated = re.match(r"\s*(\d{2}) (\w{3}) (\d{4})\s+", line)
        if dated:
            finish()
            day = _date(*dated.groups())
            side = None
            if not start <= day <= end or movements and day < movements[-1].date:
                raise InputError("Nubank: data fora do período ou da ordem cronológica.")
            line = line[dated.end():]
        total = re.fullmatch(r"\s*Total de (entradas|sa[ií]das)\s+([+-])\s*(" + AMOUNT + r")\s*", line, re.I)
        if total:
            finish()
            side = 1 if normalize(total[1]) == "ENTRADAS" else -1
            if day is None or total[2] != ("+" if side == 1 else "-") or (day, side) in daily_totals:
                raise InputError("Nubank: total diário ambíguo.")
            daily_totals[day, side] = money(total[3])
            continue
        balance = re.fullmatch(r"\s*Saldo do dia\s+(-?" + AMOUNT + r")\s*", line, re.I)
        if balance:
            finish()
            if day is None or day in balances:
                raise InputError("Nubank: saldo diário ambíguo.")
            balances[day] = money(balance[1])
            continue
        row = re.fullmatch(r"\s*(.+?)\s{2,}(.+?)\s{2,}(" + AMOUNT + r")\s*", line)
        if row:
            finish()
            if day is None or side is None:
                raise InputError("Nubank: transação sem data ou sentido.")
            event = normalize(row[1])
            if ("RECEBIDA" in event and side != 1) or ("ENVIADA" in event and side != -1):
                raise InputError("Nubank: sentido da transferência diverge do total diário.")
            current = {"day": day, "event": row[1].strip(), "details": [row[2].strip()], "amount": money(row[3]) * side}
            continue
        if line.strip():
            if current and not re.search(r"\d[\d.]*,\d{2}|Total de|Saldo do dia", line):
                current["details"].append(" ".join(line.split()))
            else:
                raise InputError("Nubank: linha não reconhecida na área de movimentações.")
    finish()
    _totals(movements, incoming, outgoing, "Nubank")
    for (day, side), total in daily_totals.items():
        if sum(abs(m.cents) for m in movements if m.date == day and (1 if m.cents > 0 else -1) == side) != total:
            raise InputError("Nubank: total diário de transações não confere.")
    if initial + incoming - outgoing + yield_cents != final:
        raise InputError("Nubank: saldo final não fecha com os totais e o rendimento.")
    running, accrued = initial, 0
    for day, balance in sorted(balances.items()):
        running += sum(m.cents for m in movements if m.date == day)
        increment = balance - running
        if (yield_cents >= 0 and increment < 0) or (yield_cents < 0 and increment > 0):
            raise InputError("Nubank: saldo diário diverge dos movimentos e rendimentos.")
        accrued += increment
        if abs(accrued) > abs(yield_cents):
            raise InputError("Nubank: diferença dos saldos diários excede o rendimento informado.")
        running = balance
    if not balances or set(balances) != {m.date for m in movements}:
        raise InputError("Nubank: faltam saldos diários para conferir as transações.")
    warnings = ["Nubank: totais do período, totais diários e saldos conferidos considerando o rendimento do resumo. Descrições completas de cada transação foram preservadas."]
    if yield_cents:
        yield_text = f"{yield_cents / 100:.2f}".replace(".", ",")
        warnings.append(f"ATENÇÃO: rendimento líquido de R$ {yield_text} consta apenas no resumo, sem lançamento datado. Não foi criado movimento para esse valor. Confira e registre o rendimento separadamente no Makro.")
    return Statement("Nubank — movimentações", movements, account, warnings)


def read_caixa(text, ocr=False):
    account = _one(re.findall(r"Conta\s+\d+\s*/\s*([\d.]+-\d)", text, re.I), "a conta Caixa")
    start, end = _period(text, r"(" + DATE + r")\s*at[eé]\s*(" + DATE + r")", "Caixa")
    opening = re.search(r"SALDO ANTERIOR\s+(?:R[S$]\s*)?(" + AMOUNT + r")\s*([CD])", text, re.I)
    if not opening:
        raise InputError("Caixa: saldo anterior ausente.")
    initial = money(opening[1]) * (-1 if opening[2].upper() == "D" else 1)
    records, active = [], False
    for line in text.splitlines():
        if re.search(r"Hist[oó]rico/Complemento", line, re.I) and re.search(r"Valor", line):
            active = True
            continue
        if not active or not line.strip():
            continue
        if re.match(r"\s*Al[oô]\s+CA[IL]XA", line, re.I):
            active = False
            continue
        row = re.fullmatch(r"\s*(" + DATE + r")\s*-\s*(\d{2}:\d{2}:\d{2})\s{2,}(\d{6})\s{2,}(.+?)\s{2,}(" + AMOUNT + r")\s*([CD])\s{2,}(" + AMOUNT + r")\s*([CD])\s*", line, re.I)
        if not row:
            raise InputError("Caixa: linha ilegível ou incompleta; nenhum movimento foi importado.")
        day = parse_date(row[1])
        month_end = date(end.year, end.month, calendar.monthrange(end.year, end.month)[1])
        if not start <= day <= month_end:
            raise InputError("Caixa: movimento fora do mês do período.")
        fields = re.split(r"\s{2,}", row[4].strip())
        if len(fields) > 3:
            raise InputError("Caixa: colunas de descrição não reconhecidas.")
        history = fields[0]
        beneficiary = fields[1] if len(fields) >= 2 else ""
        amount = money(row[5]) * (-1 if row[6].upper() == "D" else 1)
        balance = money(row[7]) * (-1 if row[8].upper() == "D" else 1)
        description = history + (" — " + beneficiary if beneficiary else "") + f" — Documento {row[3]} — Caixa, conta {account}"
        records.append((day, row[2], normalize(history) == "SALDO DIA", amount, balance, description, row[3]))
    if not records:
        raise InputError("Caixa: nenhum registro reconhecido.")
    # This layout is reverse chronological, including same-time fee/withdrawal rows.
    running, movements = initial, []
    last_day = None
    for day, time, is_balance, amount, balance, description, document in reversed(records):
        if last_day and day < last_day:
            raise InputError("Caixa: datas fora da ordem do layout.")
        last_day = day
        if is_balance:
            if amount != 0:
                raise InputError("Caixa: linha de saldo contém valor de transação.")
        else:
            running += amount
            movements.append(Movement(day, description, amount, document))
        if running != balance:
            raise InputError("Caixa: movimentos não fecham com o saldo. Confira a legibilidade do PDF e os sinais C/D.")
    warnings = [f"Caixa: {len(records)} saldos por linha conferidos; saldos de dia não foram importados como transações."]
    if any(m.date > end for m in movements):
        warnings.append("ATENÇÃO: o PDF contém movimentos do mesmo mês posteriores ao fim escrito no cabeçalho. Eles foram preservados; confira o filtro de datas antes de exportar.")
    if ocr:
        warnings.append("ATENÇÃO: PDF digitalizado lido por OCR local. Saldos conferidos, mas nomes e acentos podem conter erros de leitura; revise as descrições e as regras antes de exportar.")
    return Statement("Caixa — extrato por período" + (" (OCR local)" if ocr else ""), movements, account, warnings)
