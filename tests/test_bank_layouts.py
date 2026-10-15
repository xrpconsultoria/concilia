from datetime import date
import unittest
from unittest.mock import Mock, patch

from conciliador.bank_layouts import read_cresol, read_sicredi
from conciliador.domain import InputError
from conciliador.readers import read_pdf


def sicredi_row(day, document, history, debit="", credit="", balance=""):
    return f" {day:<10}  {document:<9}  {history:<52}{debit:>16}{credit:>20}{balance:>20}"


def sicredi_header():
    return "\n".join([
        "SICREDI — EXTRATO DE CONTA CORRENTE",
        "           EMPRESA FICTICIA                    000000001-1",
        "PERIODO: DE 08/2026 A 09/2026",
        sicredi_row("DATA", "DOCUMENTO", "HISTORICO", "DEBITO", "CREDITO", "SALDO"),
        "=" * 132,
    ])


def sicredi_sample():
    return "\n".join([
        sicredi_header(),
        sicredi_row("**/**/****", "*********", "S A L D O  A N T E R I O R", balance="100,00"),
        sicredi_row("01/08/2026", "DOC1", "TRANSFERENCIA RECEBIDA", credit="200,00", balance="300,00"),
        sicredi_row("01/08/2026", "DOC2", "COMPRA EXEMPLO        CIDADE", debit="50,00", balance="250,00"),
        sicredi_row("02/08/2026", "DOC3", "CAPITAL DE DEMONSTRACAO", debit="10,00"),
        sicredi_row("02/08/2026", "DOC3", "CAPITAL DE DEMONSTRACAO", debit="10,00"),
        sicredi_row("02/08/2026", "DOC3", "CAPITAL DE DEMONSTRACAO", debit="10,00", balance="220,00"),
        "  SALDO ATUAL......: 220,00 | LANCAMENTOS FUTUROS",
        "  DEBITOS.............: 80,00 |",
        "  CREDITOS............: 200,00 |",
        "03/08/2026 FUTURO EXEMPLO 999,00",
    ])


def cresol_sample():
    return """EMPRESA FICTICIA
Agência 1   Conta 000000-1
Saldo em Conta             Limite de Crédito          Saldo Disponível
R$ 100,00                  R$ 500,00                 R$ 600,00
01 de Agosto de 2026 a 31 de Agosto de 2026
Lançamentos
02/08/2026                               Saldo do Dia: + R$ 100,00
  02/08/2026 PIX CREDITO DE: EMPRESA DE             + R$ 70,00
              DEMONSTRACAO
01/08/2026                               Saldo do Dia: + R$ 30,00
  01/08/2026 JUROS EXEMPLO                           - R$ 2,00
              11111111111111111
  01/08/2026 ESTORNO JUROS EXEMPLO                   + R$ 2,00
              11111111111111111
  01/08/2026 PAGAMENTO EXEMPLO                       - R$ 70,00
              22222222222222222-1
Saldo Anterior:                                    + R$ 100,00
Consulta Posição consolidada em 01/09/2026 às 10:00:00
Periodo de 01/08/2026 a 31/08/2026
Página 1 de 1
"""


class SicrediTests(unittest.TestCase):
    def test_distinguishes_debit_credit_balance_and_preserves_repeated_entries(self):
        result = read_sicredi(sicredi_sample())
        self.assertEqual(result.bank_account, "000000001-1")
        self.assertEqual([m.cents for m in result.movements], [20000, -5000, -1000, -1000, -1000])
        self.assertEqual(result.movements[1].description, "COMPRA EXEMPLO — CIDADE — Documento DOC2 — Sicredi, conta 000000001-1")
        self.assertEqual(result.movements[2].description, result.movements[3].description)
        self.assertEqual(len(result.movements), 5)

    def test_negative_opening_balance_and_transport_between_pages(self):
        text = "\n".join([
            sicredi_header(),
            sicredi_row("**/**/****", "*********", "S A L D O  A N T E R I O R", balance="-100,00"),
            sicredi_row("31/08/2026", "D1", "EXEMPLO", debit="10,00", balance="-110,00"),
            "  SALDO ATUAL......: -110,00 |",
            "\f", sicredi_header(),
            sicredi_row("**/**/****", "*********", "D E  T R A N S P O R T E", balance="-110,00"),
            sicredi_row("01/09/2026", "D2", "EXEMPLO", credit="20,00", balance="-90,00"),
            "  SALDO ATUAL......: -90,00 |",
        ])
        result = read_sicredi(text)
        self.assertEqual([m.date for m in result.movements], [date(2026, 8, 31), date(2026, 9, 1)])
        self.assertEqual([m.cents for m in result.movements], [-1000, 2000])

    def test_balance_mismatch_aborts(self):
        with self.assertRaisesRegex(InputError, "saldo"):
            read_sicredi(sicredi_sample().replace("300,00", "300,01"))

    def test_total_mismatch_aborts(self):
        with self.assertRaisesRegex(InputError, "total de débitos"):
            read_sicredi(sicredi_sample().replace("80,00 |", "80,01 |"))

    def test_two_sides_in_same_movement_are_rejected(self):
        old = sicredi_row("01/08/2026", "DOC1", "TRANSFERENCIA RECEBIDA", credit="200,00", balance="300,00")
        new = sicredi_row("01/08/2026", "DOC1", "TRANSFERENCIA RECEBIDA", debit="1,00", credit="200,00", balance="300,00")
        with self.assertRaisesRegex(InputError, "débito ou crédito"):
            read_sicredi(sicredi_sample().replace(old, new))

    def test_out_of_position_values_are_rejected(self):
        old = sicredi_row("01/08/2026", "DOC1", "TRANSFERENCIA RECEBIDA", credit="200,00", balance="300,00")
        with self.assertRaises(InputError):
            read_sicredi(sicredi_sample().replace(old, old.replace("200,00", "  200,00")))

    def test_account_or_period_changes_between_pages_are_rejected(self):
        for altered in [sicredi_sample().replace("000000001-1", "000000002-2"), sicredi_sample().replace("08/2026 A 09/2026", "07/2026 A 09/2026")]:
            with self.assertRaises(InputError):
                read_sicredi(sicredi_sample() + "\n\f\n" + altered)

    def test_unusual_characters_are_preserved_and_reported(self):
        old = sicredi_row("01/08/2026", "DOC1", "TRANSFERENCIA RECEBIDA", credit="200,00", balance="300,00")
        new = sicredi_row("01/08/2026", "DOC1", "EXEMPLO COM ¶ NO HISTORICO", credit="200,00", balance="300,00")
        result = read_sicredi(sicredi_sample().replace(old, new))
        self.assertIn("¶", result.movements[0].description)
        self.assertTrue(any("grafia foi preservada" in warning for warning in result.warnings))


class CresolTests(unittest.TestCase):
    def test_sorts_days_joins_wrapped_description_and_keeps_reversal(self):
        result = read_cresol(cresol_sample())
        self.assertEqual(result.bank_account, "000000-1")
        self.assertEqual([m.cents for m in result.movements], [-200, 200, -7000, 7000])
        self.assertEqual(result.movements[0].document, result.movements[1].document)
        self.assertEqual(result.movements[-1].description, "PIX CREDITO DE: EMPRESA DE DEMONSTRACAO — Documento não informado — Cresol, conta 000000-1")
        self.assertEqual(result.movements[0].date, date(2026, 8, 1))

    def test_balance_mismatch_aborts(self):
        with self.assertRaisesRegex(InputError, "saldo de"):
            read_cresol(cresol_sample().replace("Saldo do Dia: + R$ 30,00", "Saldo do Dia: + R$ 30,01"))

    def test_opening_balance_is_required(self):
        text = cresol_sample().replace("Saldo Anterior:                                    + R$ 100,00", "")
        with self.assertRaisesRegex(InputError, "saldo anterior"):
            read_cresol(text)

    def test_sign_is_required_in_each_movement(self):
        with self.assertRaisesRegex(InputError, "sinal ou valor"):
            read_cresol(cresol_sample().replace("- R$ 2,00", "R$ 2,00"))

    def test_unrecognized_money_line_cannot_be_treated_as_description(self):
        with self.assertRaises(InputError):
            read_cresol(cresol_sample().replace("11111111111111111", "R$ 2,00", 1))

    def test_multiple_documents_in_one_movement_are_rejected(self):
        with self.assertRaisesRegex(InputError, "mais de um documento"):
            read_cresol(cresol_sample().replace("11111111111111111", "11111111111111111\n22222222222222222", 1))

    def test_date_must_belong_to_period_and_daily_balance(self):
        with self.assertRaisesRegex(InputError, "fora do período"):
            read_cresol(cresol_sample().replace("  02/08/2026 PIX", "  02/09/2026 PIX"))

    def test_account_summary_must_match_last_daily_balance(self):
        with self.assertRaisesRegex(InputError, "saldo final"):
            read_cresol(cresol_sample().replace("R$ 100,00                  R$ 500,00", "R$ 100,01                  R$ 500,00"))


class AdditionalDispatchTests(unittest.TestCase):
    def check_dispatch(self, plain, positioned, expected):
        page = Mock()
        page.extract_text.side_effect = lambda **kwargs: positioned if kwargs.get("extraction_mode") == "layout" else plain
        with patch("conciliador.readers.PdfReader") as reader:
            reader.return_value.is_encrypted = False
            reader.return_value.pages = [page]
            result = read_pdf(b"pdf-ficticio")
        self.assertIn(expected, result.layout)

    def test_sicredi_dispatch_uses_positioned_text(self):
        self.check_dispatch("SICREDI EXTRATO DE CONTA CORRENTE", sicredi_sample(), "Sicredi")

    def test_cresol_dispatch_requires_layout_markers(self):
        self.check_dispatch(cresol_sample(), cresol_sample(), "Cresol")


if __name__ == "__main__":
    unittest.main()
