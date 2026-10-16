"""OCR em memória, com modelos incluídos no pacote e sem serviços externos."""

from functools import lru_cache
from contextlib import closing
from statistics import median
from threading import Lock
import re

from .domain import InputError

_LOCK = Lock()


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)


def positioned_rows(results):
    """Group OCR cells by baseline, retaining separate table columns."""
    if not results:
        raise InputError("OCR local: não foi possível reconhecer texto na imagem.")
    heights = [max(p[1] for p in box) - min(p[1] for p in box) for box, _, _ in results]
    tolerance = median(heights) * 0.6
    rows = []
    for box, text, confidence in sorted(results, key=lambda item: sum(p[1] for p in item[0]) / 4):
        # Never correct ambiguous digits or C/D automatically.
        if confidence < 0.80 and re.search(r"\d[\d.]*,\d{2}|\d{2}/\d{2}/\d{4}|^\d{6}$", text):
            raise InputError("OCR local: data, documento ou valor com baixa confiança. Envie um PDF mais legível ou OFX.")
        y = sum(p[1] for p in box) / 4
        if not rows or abs(rows[-1][0] - y) > tolerance:
            rows.append((y, []))
        rows[-1][1].append((min(p[0] for p in box), text))
    return "\n".join("  ".join(text for _, text in sorted(cells)) for _, cells in rows)


def read_image_pdf(content, password=""):
    try:
        import pypdfium2 as pdfium
        with _LOCK, pdfium.PdfDocument(content, password=password or None) as document:
            if len(document) > 20:
                raise InputError("OCR local: importe até 20 páginas digitalizadas por vez.")
            pages = []
            for index in range(len(document)):
                with closing(document[index]) as page:
                    width, height = page.get_size()
                    scale = min(3.5, 3300 / max(width, height))
                    with closing(page.render(scale=scale)) as bitmap:
                        result, _ = _engine()(bitmap.to_numpy())
                        pages.append(positioned_rows(result))
            return "\n\f\n".join(pages)
    except InputError:
        raise
    except ImportError as exc:
        raise InputError("OCR local indisponível. Encerre e abra o inicializador para instalar as dependências da versão atual.") from exc
    except Exception as exc:
        raise InputError("Não foi possível ler a imagem por OCR local. Confira a legibilidade ou envie OFX.") from exc
