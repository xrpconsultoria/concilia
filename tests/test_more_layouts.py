"""Somente dados fictícios; nenhum documento real é necessário para a suíte."""

from datetime import date
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from openpyxl import load_workbook

from conciliador.domain import InputError, classify
from conciliador.local_ocr import positioned_rows, read_image_pdf
from conciliador.makro import HEADERS, export_workbook
from conciliador.more_layouts import read_bb, read_caixa, read_cora, read_inter, read_nubank
from conciliador.readers import read_pdf


def bb_header():
    return "\n".join(["Extrato de Conta Corrente", "Cliente EMPRESA FICTICIA", "Agência: 0001-0 Conta: 000001-1", "Lançamentos",
                         f"{'Dia':<14}{'Lote':<12}{'Documento':<20}{'Histórico':<55}Valor"])


def bb_row(day, history, value="", lot="", document=""):
    return f"{day:<14}{lot:<12}{document:<20}{history:<55}{value}"


def bb_sample():
    return "\n".join([bb_header(), bb_row("31/07/2026", "Saldo Anterior", "100,00 (+)"),
        bb_row("01/08/2026", "Pix - Recebido"), bb_row("", "01/08 10:00 EMPRESA FICTICIA", "200,00 (+)", "10000", "12345"),
        bb_row("00/00/0000", "Saldo do dia", "300,00 (+)"),
        bb_row("02/08/202", "Pix - Enviado", "50,00 (-)", "10000", "12346"),
        "\f", bb_header(), bb_row("6", "02/08 09:30 PESSOA EXEMPLO"),
        bb_row("00/00/0000", "Saldo do dia", "250,00 (+)"), bb_row("02/08/2026", "S A L D O", "250,00 (+)"),
        "Total Aplicações Financeiras 0,00"])


def inter_sample():
    return """EMPRESA FICTICIA
CPF/CNPJ: 00.000.000/0001-00, Instituição: Banco Inter, Agência: 0001-0, Conta: 000002-2
Período: 01/08/2026 a 31/08/2026
Saldo total R$ 999,00
1 de Agosto de 2026 Saldo do dia: R$ 250,00       Valor Saldo por transação
 Pix recebido: "Cp :00000000-EMPRESA EXEMPLO"    R$ 200,00     R$ 300,00
Fale com a gente
SAC: 0000 000 0000
\f
 Pix enviado: "Cp :11111111-Pessoa Ficticia"    -R$ 50,00     R$ 250,00
2 de Agosto de 2026 Saldo do dia: R$ -50,00
 Pix enviado: "Cp :11111111-Outro Exemplo"    -R$ 300,00     -R$ 50,00
"""


def cora_sample():
    return """EMPRESA FICTICIA
CNPJ 00.000.000/0001-00
Agência: 0001 - Conta: 000003-3
Extrato do período 01/08/2026 a 01/09/2026
Saldo inicial disponível R$ 100,00
Total de entradas + R$ 200,00
Total de saídas - R$ 50,00
Saldo final disponível R$ 250,00
Transações
02/08/2026      Saldo do dia R$ 250,00
 Compra no débito     Loja fictícia…       - R$ 50,00
01/08/2026      Saldo do dia R$ 300,00
 Transf Pix recebida     EMPRESA EXEMPLO…     00.000.000/0001-00    + R$ 100,00
Cora SCFI - CNPJ 00.000.000/0001-00
Ouvidoria: 0000
Extrato gerado no dia 01/09/2026 pág 1 de 2
\f
EMPRESA FICTICIA
CNPJ 00.000.000/0001-00
Agência: 0001 - Conta: 000003-3
 Transf Pix recebida     EMPRESA EXEMPLO…     00.000.000/0001-00    + R$ 100,00
Cora SCFI - CNPJ 00.000.000/0001-00
"""


def nubank_sample():
    return """EMPRESA FICTICIA
CNPJ 00.000.000/0001-00 Agência 0001 Conta
000004-4
01 DE SETEMBRO DE 2026 a 30 DE SETEMBRO DE 2026 VALORES EM R$
Saldo inicial 100,00
Rendimento líquido +0,02
Total de entradas +200,00
Total de saídas -50,00
Saldo final do período 250,02
Movimentações
15 SET 2026   Total de entradas     + 200,00
    Transferência recebida pelo Pix    EMPRESA EXEMPLO LTDA -    200,00
        00.000.000/0001-00 - BANCO EXEMPLO
        Agência: 0001 Conta: 000001-1
    Saldo do dia    300,01
16 SET 2026   Total de saídas       - 50,00
    Transferência enviada pelo Pix    PESSOA FICTICIA -    50,00
        BANCO DEMONSTRATIVO Agência: 0002 Conta: 000002-2
    Saldo do dia    250,02
O saldo líquido corresponde ao total de depósitos e rendimentos em conta.
Nu Pagamentos S.A.
"""


def caixa_sample():
    return """CAIXA
Extrato por periodo
Cliente  EMPRESA FICTICIA
Conta  0001 / 0000.000000005-5
Periodo dos lancamentos  01/08/2026ate30/08/2026
SALDO ANTERIOR  RS 100,00 C
Lancamentos  Nr. Doc  Historico/Complemento  Favorecido  CPF/CNPJ  Valor  Saldo
31/08/2026-00:00:00  000000  SALDO DIA  0,00 C  250,00 C
31/08/2026-10:00:00  000002  TARIFA EXEMPLO  5,00 D  250,00 C
31/08/2026-10:00:00  000002  SAQUE EXEMPLO  45,00 D  255,00 C
01/08/2026-12:30:00  000001  CRED PIX CHAVE  Pessoa Exemplo  ***.000.000***  200,00 C  300,00 C
Alo CAIXA: 0000 000 0000
Ouvidoria: 0000
"""


class BancoBrasilTests(unittest.TestCase):
    def test_multiline_document_split_date_and_balances(self):
        result = read_bb(bb_sample())
        self.assertEqual([m.cents for m in result.movements], [20000, -5000])
        self.assertEqual(result.movements[-1].date, date(2026, 8, 2))
        self.assertEqual(result.movements[-1].document, "12346")
        self.assertIn("PESSOA EXEMPLO", result.movements[-1].description)
        self.assertTrue(any("recomposta" in w for w in result.warnings))

    def test_bad_balance_or_unfinished_date_aborts(self):
        for text in [bb_sample().replace("300,00 (+)", "300,01 (+)"), bb_sample().replace(bb_row("6", "02/08 09:30 PESSOA EXEMPLO"), "")]:
            with self.subTest(text=text), self.assertRaises(InputError):
                read_bb(text)

    def test_last_transaction_needs_closing_balance(self):
        text = bb_sample().replace(bb_row("00/00/0000", "Saldo do dia", "250,00 (+)"), "").replace(bb_row("02/08/2026", "S A L D O", "250,00 (+)"), "")
        with self.assertRaises(InputError):
            read_bb(text)

    def test_multiple_accounts_are_rejected(self):
        with self.assertRaises(InputError):
            read_bb(bb_sample().replace("\f", "\fAgência: 0001-0 Conta: 000009-9\n"))


class InterTests(unittest.TestCase):
    def test_cross_page_continuation_negative_balance_and_original_names(self):
        result = read_inter(inter_sample())
        self.assertEqual([m.cents for m in result.movements], [20000, -5000, -30000])
        self.assertEqual(result.movements[1].description, "PIX ENVIADO — Cp :11111111-PESSOA FICTICIA — Banco Inter, conta 000002-2")

    def test_transaction_or_daily_balance_mismatch_aborts(self):
        for text in [inter_sample().replace("R$ 300,00", "R$ 300,01", 1), inter_sample().replace("Saldo do dia: R$ 250,00", "Saldo do dia: R$ 250,01")]:
            with self.subTest(text=text), self.assertRaises(InputError):
                read_inter(text)

    def test_malformed_financial_line_or_out_of_period_date_aborts(self):
        for text in [inter_sample().replace('-R$ 50,00     R$ 250,00', '-R$ 50,00'), inter_sample().replace("2 de Agosto", "2 de Setembro")]:
            with self.subTest(text=text), self.assertRaises(InputError):
                read_inter(text)

    def test_first_transaction_sign_must_match_its_direction_without_opening_balance(self):
        with self.assertRaisesRegex(InputError, "sentido"):
            read_inter(inter_sample().replace('R$ 200,00', '-R$ 200,00'))


class CoraTests(unittest.TestCase):
    def test_reverse_order_and_identical_transfers_across_pages_preserved(self):
        result = read_cora(cora_sample())
        self.assertEqual([m.cents for m in result.movements], [-5000, 10000, 10000])
        self.assertEqual(result.movements[1].description, "EMPRESA EXEMPLO… 00.000.000/0001-00")
        self.assertEqual(result.movements[1], result.movements[2])
        self.assertEqual(result.movements[0].date, date(2026, 8, 2))

    def test_total_daily_balance_or_final_mismatch_aborts(self):
        for text in [cora_sample().replace("entradas + R$ 200,00", "entradas + R$ 200,01"), cora_sample().replace("dia R$ 300,00", "dia R$ 300,01"), cora_sample().replace("final disponível R$ 250,00", "final disponível R$ 250,01")]:
            with self.subTest(text=text), self.assertRaises(InputError):
                read_cora(text)

    def test_signless_or_unrecognized_row_is_rejected(self):
        for text in [cora_sample().replace("- R$ 50,00", "R$ 50,00"), cora_sample().replace("- R$ 50,00", "- 50,00"), cora_sample().replace("- R$ 50,00", "- R$ 50,00\nOPERACAO ILEGIVEL")]:
            with self.subTest(text=text), self.assertRaises(InputError):
                read_cora(text)


class NubankTests(unittest.TestCase):
    def test_true_counterparties_and_yield_not_fabricated_as_dated_transaction(self):
        result = read_nubank(nubank_sample())
        self.assertEqual([m.cents for m in result.movements], [20000, -5000])
        self.assertIn("EMPRESA EXEMPLO", result.movements[0].description)
        self.assertIn("PESSOA FICTICIA", result.movements[1].description)
        self.assertNotIn("EMPRESA EXEMPLO", result.movements[1].description)
        self.assertTrue(any(w.startswith("ATENÇÃO:") and "0,02" in w for w in result.warnings))
        self.assertEqual(classify(result.movements[1], [dict(kind="exact", pattern="Transferência enviada pelo Pix — EMPRESA EXEMPLO", direction="saida", code=150)])[0], 106)

    def test_totals_yield_daily_balance_and_side_must_reconcile(self):
        variants = [("Total de entradas +200,00", "Total de entradas +200,01"), ("Total de entradas     + 200,00", "Total de entradas     + 199,99"), ("líquido +0,02", "líquido +0,03"), ("Saldo do dia    300,01", "Saldo do dia    300,03"), ("enviada pelo Pix", "recebida pelo Pix")]
        for old, new in variants:
            with self.subTest(old=old), self.assertRaises(InputError):
                read_nubank(nubank_sample().replace(old, new))

    def test_no_yield_needs_no_manual_yield_warning(self):
        text = nubank_sample().replace("+0,02", "+0,00").replace("250,02", "250,00").replace("300,01", "300,00")
        result = read_nubank(text)
        self.assertFalse(any(w.startswith("ATENÇÃO:") for w in result.warnings))

    def test_unknown_financial_line_cannot_be_appended_to_description(self):
        with self.assertRaises(InputError):
            read_nubank(nubank_sample().replace("00.000.000/0001-00 - BANCO EXEMPLO", "Valor não reconhecido 10,00"))

    def test_each_new_day_requires_its_own_direction_total(self):
        with self.assertRaises(InputError):
            read_nubank(nubank_sample().replace("16 SET 2026   Total de saídas       - 50,00", "16 SET 2026   "))


class CaixaTests(unittest.TestCase):
    def test_same_time_fees_daily_balances_and_header_end_date(self):
        result = read_caixa(caixa_sample(), ocr=True)
        self.assertEqual([m.cents for m in result.movements], [20000, -4500, -500])
        self.assertEqual(result.movements[-1].date, date(2026, 8, 31))
        self.assertEqual(result.bank_account, "0000.000000005-5")
        self.assertEqual(result.movements[0].document, "000001")
        self.assertTrue(any("posteriores" in w for w in result.warnings))
        self.assertTrue(any("OCR local" in w for w in result.warnings))

    def test_bad_balance_missing_sign_or_missing_row_aborts(self):
        for text in [caixa_sample().replace("255,00 C", "255,01 C"), caixa_sample().replace("45,00 D", "45,00"), "\n".join(line for line in caixa_sample().splitlines() if "SAQUE EXEMPLO" not in line)]:
            with self.subTest(text=text), self.assertRaises(InputError):
                read_caixa(text)

    def test_balance_markers_cannot_have_a_nonzero_value(self):
        with self.assertRaises(InputError):
            read_caixa(caixa_sample().replace("SALDO DIA  0,00", "SALDO DIA  1,00"))

    def test_other_month_cannot_silently_pass_as_header_anomaly(self):
        with self.assertRaises(InputError):
            read_caixa(caixa_sample().replace("31/08/2026", "01/09/2026"))


class DispatchAndExportTests(unittest.TestCase):
    def test_new_pdf_dispatch_and_makro_export(self):
        samples = [(bb_sample(), "Banco do Brasil"), (inter_sample(), "Inter"), (cora_sample(), "Cora"), (nubank_sample(), "Nubank"), (caixa_sample(), "Caixa")]
        for source, name in samples:
            with self.subTest(bank=name):
                page = Mock()
                page.extract_text.return_value = source
                with patch("conciliador.readers.PdfReader") as pdf:
                    pdf.return_value.is_encrypted = False
                    pdf.return_value.pages = [page]
                    statement = read_pdf(b"pdf-ficticio")
                self.assertIn(name, statement.layout)
                rows = [dict(date=m.date.isoformat(), description=m.description, cents=m.cents, code=106) for m in statement.movements]
                sheet = load_workbook(export_workbook(rows, 12), data_only=True).active
                self.assertEqual(list(next(sheet.values)), HEADERS)
                for exported, m in zip(list(sheet.values)[1:], statement.movements, strict=True):
                    self.assertEqual(exported[0].date(), m.date)
                    self.assertEqual(round(exported[2] * 100), abs(m.cents))
                    self.assertEqual(exported[3:6], (12, 106, 52) if m.cents > 0 else (106, 12, 52))
                    self.assertEqual(exported[6:], (None, None, None, None))

    def test_scanned_pdf_uses_local_ocr_and_rejects_unrecognized_bank(self):
        with patch("conciliador.readers.PdfReader") as pdf, patch("conciliador.readers.read_image_pdf") as ocr:
            pdf.return_value.is_encrypted = False
            pdf.return_value.pages = [Mock(extract_text=Mock(return_value=""))]
            ocr.return_value = caixa_sample()
            self.assertIn("OCR local", read_pdf(b"imagem").layout)
            ocr.assert_called_once_with(b"imagem", "")
            ocr.return_value = "BANCO SEM LEITOR"
            with self.assertRaises(InputError):
                read_pdf(b"imagem")

    def test_critical_warnings_are_visible_outside_collapsed_details(self):
        from app import create_app
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(dict(TESTING=True, SECRET_KEY="fictional-key", DATABASE=str(Path(directory) / "app.sqlite3")))
            client = app.test_client()
            client.get("/")
            with client.session_transaction() as session:
                csrf = session["csrf"]
            client.post("/clients", data=dict(csrf=csrf, name="Empresa fictícia"))
            client.post("/accounts", data=dict(csrf=csrf, client_id=1, name="Nubank", number="000004-4", bank_code=12))
            with patch("app.read_statement", return_value=read_nubank(nubank_sample())):
                response = client.post("/import", data=dict(csrf=csrf, account_id=1, file=(BytesIO(b"pdf-ficticio"), "extrato.pdf")), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('ATENÇÃO: rendimento'.encode(), response.data.split(b'<details class="verification-details">')[0])


class LocalOCRTests(unittest.TestCase):
    def test_groups_cells_in_source_columns_and_rejects_uncertain_financial_fields(self):
        def cell(x, y, text, confidence=0.99):
            return ([[x, y], [x + 50, y], [x + 50, y + 20], [x, y + 20]], text, confidence)
        cells = [cell(200, 1, "100,00 C"), cell(0, 0, "01/08/2026"), cell(0, 40, "02/08/2026")]
        self.assertEqual(positioned_rows(cells), "01/08/2026  100,00 C\n02/08/2026")
        with self.assertRaisesRegex(InputError, "baixa confiança"):
            positioned_rows([cell(0, 0, "100,00 C", .7)])
        with self.assertRaises(InputError):
            positioned_rows([])

    def test_invalid_image_pdf_has_actionable_error(self):
        with self.assertRaisesRegex(InputError, "OCR local"):
            read_image_pdf(b"invalid-pdf")


if __name__ == "__main__":
    unittest.main()
