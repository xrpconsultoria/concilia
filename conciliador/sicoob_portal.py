"""Extrato Sicoob Internet Banking: Documento em coluna, descrições e páginas longas."""

from collections import defaultdict
import re

from .domain import InputError, Movement, Statement, money, normalize, parse_date

AMOUNT = r"\d[\d.]*,\d{2}"


def read_sicoob_portal(text):
    periods = set(re.findall(r"PER[IÍ]ODO:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text, re.I))
    accounts = set(re.findall(r"CONTA:\s*([\d.-]+)\s*/", text, re.I))
    if len(periods) != 1 or len(accounts) != 1:
        raise InputError("Sicoob Internet Banking: conta ou período ausente ou divergente entre páginas. Gere novamente o extrato completo de uma única conta.")
    start, end = map(parse_date, next(iter(periods)))
    if start > end:
        raise InputError("Sicoob Internet Banking: período inicial posterior ao final.")
    account = next(iter(accounts))
    current, active, page = None, False, 1
    movements, balances = [], {}
    initial, blocked = None, 0
    printed_pages, page_totals = set(), set()

    def fail(message, record=None):
        record = record or current
        location = f"página {record['page']}, data {record['day']}" if record else f"página {page}"
        raise InputError(f"Sicoob Internet Banking — {location}: {message} Gere novamente o PDF completo pelo banco, com texto selecionável, ou use OFX.")

    def full_date(day):
        dates = []
        for year in range(start.year, end.year + 1):
            try:
                candidate = parse_date(f"{day}/{year}")
            except InputError:
                continue
            if start <= candidate <= end:
                dates.append(candidate)
        if len(dates) != 1:
            fail("a data não pertence ao período ou é ambígua.")
        return dates[0]

    def finish():
        nonlocal current, initial, blocked
        if current is None:
            return
        history = normalize(" ".join(current["parts"]))
        if re.search(r"(?:SALDO BLOQUEADO ANTERIOR|DEP\.CHEQUE BLOQ\.\d+D)\s+R\$\s*" + AMOUNT + r"\*\s*$", history):
            blocked += 1
            current = None
            return
        amounts = list(re.finditer(r"R\$\s*(" + AMOUNT + r")\s*([CD])\b", history))
        if len(amounts) != 1 or history.count("R$") != 1:
            fail("não foi reconhecido exatamente um valor com sinal C/D nesse registro.")
        found = amounts[0]
        description = normalize(history[:found.start()] + " " + history[found.end():])
        amount = money(found[1]) * (-1 if found[2] == "D" else 1)
        if description == "SALDO ANTERIOR":
            if initial is not None:
                fail("há mais de um saldo anterior.")
            initial = amount
        else:
            day = full_date(current["day"])
            if description == "SALDO DO DIA":
                if day in balances:
                    fail("há mais de um saldo para o mesmo dia.")
                balances[day] = amount
            elif not description or not current["document"]:
                fail("o documento ou o histórico do movimento está vazio.")
            else:
                # Only known presentation variants of this exact source text/document.
                # Names and identifiers are never removed, completed or guessed.
                clean_parts = [normalize(re.sub(r"R\$\s*" + AMOUNT + r"\s*[CD]\b", "", part)) for part in current["parts"]]
                clean_parts = [part for part in clean_parts if part]
                event, *details = clean_parts
                document = current["document"]
                labelled_details = [re.sub(r"^FAV\.:\s*", "", part) for part in details]
                variants = (
                    event + (" - " + " ".join(details) if details else "") + f" - DOC {document}",
                    f"{document} {description}",
                    event + ": " + (" | ".join(details) if details else event) + f" — Documento: {document}",
                    event + (" - " + " - ".join(labelled_details) if details else "") + f" - DOC {document}",
                )
                movements.append(Movement(day, description, amount, document, description_variants=variants))
        current = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        footer = re.fullmatch(r"https://(?:www|ib)\.sicoob\.com\.br/sicoobnet/ib/\S*\s+(\d+)/(\d+)", line)
        if footer:
            number, total = map(int, footer.groups())
            if number in printed_pages or number < 1 or number > total or total > 200:
                fail("a numeração das páginas está repetida ou inválida.")
            printed_pages.add(number)
            page_totals.add(total)
            page = int(footer[1]) + 1
            continue
        if re.fullmatch(r"\d{2}/\d{2}/\d{4},\s*\d{2}:\d{2}\s+Sicoob\s*\|\s*Internet Banking", line, re.I):
            continue
        if re.fullmatch(r"Data\s+Documento\s*Hist[oó]rico\s+Valor", line, re.I):
            continue
        if normalize(line) == "HISTÓRICO DE MOVIMENTAÇÃO":
            active = True
            continue
        if normalize(line) == "RESUMO":
            finish()
            active = False
            continue
        if not active:
            continue
        dated = re.fullmatch(r"(\d{2}/\d{2})(?!/\d{4})(.*)", line)
        if dated:
            finish()
            tail = dated[2].strip()
            current = dict(day=dated[1], document=tail, parts=[], page=page)
            if "R$" in tail:
                # Blocked deposits and opening blocked balance are printed on one line.
                current["document"] = ""
                current["parts"].append(tail)
        elif current:
            current["parts"].append(line)
        else:
            fail("foi encontrada uma continuação sem movimento anterior.")
    finish()
    if printed_pages:
        if len(page_totals) != 1:
            fail("o total de páginas mudou no documento; há extratos misturados.")
        missing = sorted(set(range(1, next(iter(page_totals)) + 1)) - printed_pages)
        if missing:
            raise InputError(f"Sicoob Internet Banking: faltam páginas do extrato ({', '.join(map(str, missing[:8]))}). Gere novamente o PDF completo, incluindo todas as páginas, ou envie OFX.")
    if initial is None or not movements or not balances:
        fail("faltam saldo anterior, movimentos ou saldos diários para conferir o arquivo.")
    totals = defaultdict(int)
    for movement in movements:
        totals[movement.date] += movement.cents
    if set(totals) != set(balances):
        fail("faltam saldos diários para uma ou mais datas com movimentos.")
    running = initial
    for day, balance in sorted(balances.items()):
        running += totals[day]
        if running != balance:
            raise InputError(f"Sicoob Internet Banking: saldo de {day.strftime('%d/%m/%Y')} divergente. Calculado R$ {running / 100:.2f}; extrato R$ {balance / 100:.2f}. Não foi importada nenhuma linha. Confira se todas as páginas estão no PDF ou envie OFX.")
    summary = re.search(r"Saldo em conta:\s*(" + AMOUNT + r")\s*([CD])", text, re.I)
    if not summary or running != money(summary[1]) * (-1 if summary[2].upper() == "D" else 1):
        fail("o saldo final não confere com o resumo da conta.")
    movements.sort(key=lambda movement: movement.date)
    warnings = [f"Sicoob Internet Banking: {len(movements)} movimentos, {len(balances)} saldos diários e saldo final conferidos. Ordem cronológica, preservando a ordem original dentro de cada dia.", "Documento preservado para consulta. A coluna Conta do Excel contém o histórico e os complementos do banco; descrições editadas em planilhas anteriores podem exigir revisão na 106."]
    if blocked:
        warnings.append(f"{blocked} registros de saldo ou depósito bloqueado, marcados com *, não são movimentos do saldo disponível e ficaram fora da exportação. Liberações e estornos com C/D foram preservados.")
    return Statement("Sicoob Internet Banking — Documento/Histórico/Valor", movements, account, warnings)
