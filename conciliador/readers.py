import csv
from datetime import date, datetime
from io import BytesIO, StringIO
import re

from openpyxl import load_workbook
from pypdf import PdfReader

from .domain import InputError, Movement, Statement, money, normalize, parse_date
from .bank_layouts import read_cresol, read_sicredi


def read_pdf(content, password=""):
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(password):
            raise InputError("PDF protegido: informe a senha correta. A senha não é armazenada.")
        if len(reader.pages) > 200:
            raise InputError("Importe PDFs com até 200 páginas por arquivo.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except InputError:
        raise
    except Exception as exc:
        raise InputError("Não foi possível ler o PDF. Verifique o arquivo e a senha.") from exc
    if "Plano de Contas" in text and "Tipo de Saldo" in text:
        raise InputError("Este PDF é um plano de contas. Salve-o em Clientes e configurações. Aqui, escolha o extrato bancário com os movimentos.")
    if "SICOOB" in text and "HISTÓRICO DE MOVIMENTAÇÃO" in text:
        result = read_sicoob(text)
    elif "C6" in text and "Data" in text and "contábil" in text:
        result = read_c6(text)
    elif "SICREDI" in text.upper() and "EXTRATO DE CONTA CORRENTE" in text:
        result = read_sicredi(_positioned_text(reader))
    elif all(marker in text for marker in ["Saldo em Conta", "Saldo Disponível", "Lançamentos", "Consulta Posição consolidada", "Saldo Anterior:"]):
        result = read_cresol(_positioned_text(reader))
    else:
        raise InputError("Layout PDF ainda não reconhecido. Esta versão lê Sicoob SISBR, C6 com duas datas, Sicredi com débito/crédito e Cresol com saldos diários. PDFs digitalizados precisam de um leitor com OCR.")
    if not result.movements:
        raise InputError("Nenhum movimento foi identificado; o arquivo não foi importado.")
    return result


def _positioned_text(reader):
    try:
        return "\n\f\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    except Exception as exc:
        raise InputError("Não foi possível separar as colunas do PDF. Confira se o arquivo tem texto selecionável.") from exc


def read_sicoob(text):
    period = re.search(r"PERÍODO:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", text)
    if not period:
        raise InputError("O período do extrato Sicoob não foi reconhecido.")
    start, end = (parse_date(x) for x in period.groups())
    account = re.search(r"CONTA:\s*([\d.\-]+)", text)
    blocks = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if line == "RESUMO":
            break
        match = re.match(r"^(\d{2}/\d{2})\s+(.+)$", line)
        if match:
            if current:
                blocks.append(current)
            current = (match[1], [match[2]])
        elif current and line:
            current[1].append(line)
    if current:
        blocks.append(current)
    movements, balances = [], []
    for day, original in blocks:
        parts = list(original)
        if parts[0].startswith("SALDO BLOQ"):
            continue
        match = re.search(r"(\d[\d.]*,\d{2})([CD])?$", parts[0])
        try:
            if match:
                amount, sign = match.groups()
                desc, rest = parts[0][:match.start()].strip(), parts[1:]
                if sign is None:
                    sign = rest.pop(0)
            else:
                desc, amount, sign, *rest = parts
            if sign not in ("C", "D"):
                raise ValueError()
            cents = money(amount) * (1 if sign == "C" else -1)
            if desc.startswith("SALDO"):
                balances.append((day, cents))
                continue
            dates = []
            for year in range(start.year, end.year + 1):
                try:
                    candidate = parse_date(day + f"/{year}")
                    if start <= candidate <= end:
                        dates.append(candidate)
                except InputError:
                    pass
            if len(dates) != 1:
                raise InputError("O período torna a data de um movimento ambígua.")
            docs = [s[5:].strip() for s in rest if s.startswith("DOC.:")]
            if len(docs) != 1:
                raise ValueError()
            details = [s for s in rest if not s.startswith("DOC.:")]
            description = normalize(" ".join([desc, *details]) + " - " + docs[0])
            movements.append(Movement(dates[0], description, cents, docs[0]))
        except (ValueError, IndexError) as exc:
            raise InputError(f"Não foi possível interpretar um movimento Sicoob em {day}; importação interrompida para evitar perda de linhas.") from exc
    warnings = []
    if balances:
        running = balances[0][1]
        for day, balance in balances[1:]:
            running += sum(m.cents for m in movements if m.date.strftime("%d/%m") == day)
            if running != balance:
                raise InputError(f"Os movimentos não fecham com o saldo do extrato em {day}. Revise o layout.")
        warnings.append(f"{len(balances) - 1} saldos diários conferidos com o PDF.")
    return Statement("Sicoob SISBR", movements, account[1] if account else "", warnings)


def read_c6(text):
    period = re.search(r"Período\s*•\s*\d+ de \w+ de (\d{4}) até \d+ de \w+ de (\d{4})", text)
    if not period or period[1] != period[2]:
        raise InputError("Este leitor C6 exige um período contido no mesmo ano.")
    year = period[1]
    account = re.search(r"Agência:\s*\d+\s*•\s*Conta:\s*(\d+)", text)
    pattern = re.compile(r"^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(Outros gastos|Entrada PIX|Saída PIX|Pagamento|Entradas|Devolução PIX)\s+(.+?)\s+(-?)R\$\s*([\d.]+,\d{2})\s*$", re.M)
    movements = []
    for match in pattern.finditer(text):
        launch, book, kind, desc, sign, amount = match.groups()
        movements.append(Movement(parse_date(launch + "/" + year), desc, money(amount) * (-1 if sign else 1), book_date=parse_date(book + "/" + year)))
    candidates = re.findall(r"^\d{2}/\d{2}\s+\d{2}/\d{2}.*$", text, re.M)
    if len(candidates) != len(movements):
        raise InputError("Há movimentos C6 fora do layout reconhecido; nenhuma linha foi importada.")
    warnings = ["Data de lançamento usada na exportação; data contábil preservada para consulta."]
    monthly = re.findall(r"\w+\s+\d{4}\s*\(\s*(\d{2}/\d{2}/\d{4})\s*-\s*\d{2}/\d{2}/\d{4}\s*\)\s*Entradas:\s*R\$\s*([\d.]+,\d{2})\s*•\s*Saídas:\s*R\$\s*([\d.]+,\d{2})", text)
    for begin, incoming, outgoing in monthly:
        month = parse_date(begin).month
        items = [m for m in movements if m.date.month == month]
        if sum(m.cents for m in items if m.cents > 0) != money(incoming) or -sum(m.cents for m in items if m.cents < 0) != money(outgoing):
            raise InputError(f"Os totais de {month:02d}/{year} não fecham com o PDF C6.")
    if monthly:
        warnings.append(f"Totais de entradas e saídas conferidos em {len(monthly)} meses.")
    return Statement("C6 — duas datas", movements, account[1] if account else "", warnings)


def read_ofx(content):
    text = decode(content)
    movements = []
    def tag(block, name):
        found = re.search(r"<" + name + r">\s*([^<\r\n]+)", block, re.I)
        return found[1].strip() if found else ""
    blocks = re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>|</BANKTRANLIST>))", text, re.S | re.I)
    if len(blocks) != len(re.findall(r"<STMTTRN>", text, re.I)):
        raise InputError("OFX incompleto: um movimento não tem fechamento reconhecido.")
    for block in blocks:
        try:
            day = datetime.strptime(tag(block, "DTPOSTED")[:8], "%Y%m%d").date()
            movements.append(Movement(day, tag(block, "MEMO") or tag(block, "NAME") or "Movimento OFX", money(tag(block, "TRNAMT")), tag(block, "FITID")))
        except (ValueError, InputError) as exc:
            raise InputError("OFX contém um movimento inválido; importação interrompida.") from exc
    if not movements:
        raise InputError("Nenhum STMTTRN foi encontrado no OFX.")
    return Statement("OFX", movements, tag(text, "ACCTID"), ["Valores lidos do OFX; confira o saldo com o extrato."])


def decode(content):
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252")


def read_table(content, suffix, mapping):
    if suffix == ".xlsx":
        book = load_workbook(BytesIO(content), read_only=True, data_only=False)
        try:
            sheet = book.active
            rows = []
            for row in sheet:
                if any(c.data_type == "f" for c in row):
                    raise InputError("A planilha contém fórmulas. Exporte os valores antes de importar.")
                rows.append([c.value for c in row])
                if len(rows) > 20001:
                    raise InputError("Importe no máximo 20.000 movimentos por arquivo.")
        finally:
            book.close()
    else:
        source = decode(content)
        try:
            dialect = csv.Sniffer().sniff(source[:8192], delimiters=";,\t")
        except csv.Error:
            raise InputError("CSV sem delimitador reconhecido. Use ponto e vírgula, vírgula ou tabulação.")
        rows = list(csv.reader(StringIO(source), dialect))
    if not rows:
        raise InputError("Tabela vazia.")
    if len(rows) > 20001:
        raise InputError("Importe no máximo 20.000 movimentos por arquivo.")
    headers = [normalize(x) for x in rows[0]]
    if {"DATA", "CONTA", "VALOR", "DEBITO", "CREDITO", "HISTORICO"}.issubset(headers):
        raise InputError("Esta é uma planilha Makro já conciliada. Use-a em Gerenciar regras para ensinar as classificações. Para criar a conciliação, envie o extrato do banco.")
    aliases = {"date": ["DATA", "DATE", "DATA LANÇAMENTO"], "description": ["DESCRICAO", "DESCRIÇÃO", "HISTORICO", "HISTÓRICO", "CONTA"], "value": ["VALOR", "VALUE", "AMOUNT"]}
    indices = {}
    for field, names in aliases.items():
        label = normalize(mapping.get(field, ""))
        matches = [i for i, h in enumerate(headers) if h == label] if label else [i for i, h in enumerate(headers) if h in names]
        if len(matches) != 1:
            label = {"date": "data", "description": "descrição", "value": "valor"}[field]
            raise InputError(f"Informe o nome exato da coluna de {label} em Mapear colunas: {', '.join(str(x) for x in rows[0])}")
        indices[field] = matches[0]
    movements = []
    for n, row in enumerate(rows[1:], 2):
        if not any(x is not None and str(x).strip() for x in row):
            continue
        try:
            day, desc, value = (row[indices[k]] for k in ("date", "description", "value"))
            if not desc:
                raise InputError("Descrição vazia.")
            movements.append(Movement(parse_date(day), str(desc), money(value)))
        except (ValueError, IndexError) as exc:
            raise InputError(f"Linha {n} inválida: {exc}") from exc
    if not movements:
        raise InputError("Tabela sem movimentos.")
    return Statement("Tabela mapeada", movements, warnings=["Tabela: valores positivos são entradas, negativos são saídas. Não use aqui a planilha Makro com valores absolutos; use-a no aprendizado de regras."])


def read_statement(content, filename, password="", mapping=None):
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    if suffix == ".pdf":
        return read_pdf(content, password)
    if suffix == ".ofx":
        return read_ofx(content)
    if suffix in (".csv", ".xlsx"):
        return read_table(content, suffix, mapping or {})
    raise InputError("Formato não suportado. Use PDF, OFX, CSV ou XLSX.")
