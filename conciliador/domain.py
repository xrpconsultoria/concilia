from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata


class InputError(ValueError):
    def __init__(self, message, *, account_mismatch=False):
        super().__init__(message)
        self.account_mismatch = account_mismatch


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
    description_variants: tuple[str, ...] = ()

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


class RuleClassifier:
    """Normalize account-scoped rules once, retaining conflicts and exact priority."""

    def __init__(self, rules):
        self.exact = {}
        self.contains = []
        for rule in rules:
            direction, pattern, code = rule["direction"], normalize(rule["pattern"]), int(rule["code"])
            if rule["kind"] == "exact":
                self.exact.setdefault((direction, pattern), set()).add(code)
            elif rule["kind"] == "contains":
                self.contains.append((direction, pattern, code))

    def classify(self, movement, default_in=106, default_out=106):
        text = normalize(movement.description)
        codes = set()
        for variant in (text, *movement.description_variants):
            codes.update(self.exact.get((movement.direction, normalize(variant)), ()))
        if not codes:
            codes = {code for direction, pattern, code in self.contains if direction == movement.direction and pattern in text}
        if len(codes) > 1:
            return 106, "Regras conflitantes; revisar"
        if codes:
            code = codes.pop()
            return code, "Regra do cliente" if code != 106 else "Pendência intencional"
        code = default_in if movement.cents >= 0 else default_out
        return code, "Padrão configurado para a conta" if code != 106 else "Sem regra; revisar"


def classify(movement, rules, default_in=106, default_out=106):
    classifier = rules if isinstance(rules, RuleClassifier) else RuleClassifier(rules)
    return classifier.classify(movement, default_in, default_out)
