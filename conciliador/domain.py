from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata


class InputError(ValueError):
    pass


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).upper().split())


def money(value):
    raw = str(value).strip().replace("\xa0", "").replace("R$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise InputError(f"Valor inválido: {value}") from exc
    if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
        raise InputError("Valores devem ter no máximo duas casas decimais.")
    return int(amount * 100)


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            pass
    raise InputError(f"Data inválida: {value}. Use dia/mês/ano.")


@dataclass
class Movement:
    date: date
    description: str
    cents: int
    document: str = ""
    book_date: date | None = None

    @property
    def direction(self):
        return "entrada" if self.cents >= 0 else "saida"


@dataclass
class Statement:
    layout: str
    movements: list[Movement]
    bank_account: str = ""
    warnings: list[str] = field(default_factory=list)


def account_digits(value):
    return re.sub(r"\D", "", str(value)).lstrip("0")


def classify(movement, rules, default_in=106, default_out=106):
    text = normalize(movement.description)
    candidates = [r for r in rules if r["direction"] == movement.direction]
    exact = [r for r in candidates if r["kind"] == "exact" and normalize(r["pattern"]) == text]
    matches = exact or [r for r in candidates if r["kind"] == "contains" and normalize(r["pattern"]) in text]
    codes = {int(r["code"]) for r in matches}
    if len(codes) > 1:
        return 106, "Regras conflitantes; revisar"
    if codes:
        code = codes.pop()
        return code, "Regra do cliente" if code != 106 else "Pendência intencional"
    code = default_in if movement.cents >= 0 else default_out
    return code, "Padrão configurado para a conta" if code != 106 else "Sem regra; revisar"
