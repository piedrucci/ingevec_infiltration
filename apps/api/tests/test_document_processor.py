import pytest

from app.services import document_processor


OCR_TEXT = """
N° obra (691)-n° filtración (897)
Proyecto en que se detecta
EUCLIDES
Tipo de filtración: LOSA, INSTALACIONES CCDD, Y BOW WINDOWS DPTOS
Lugar de la filtración: (dpto 2207)
3. ANALISIS DE CAUSA DE LA FALLA
Falla de sellos y barda de alfeizar sin pendiente
4. DESCRIPCIÓN DE LA REPARACIÓN Y MATERIALES UTILIZADOS
Se genera pendiente y se repasan sellos
"""


def test_parse_ocr_text_extracts_template_fields():
    details = document_processor._parse_pdf_text(OCR_TEXT)

    assert details == {
        "project_number": "691",
        "project_name": "EUCLIDES",
        "infiltration_location": "(dpto 2207)",
        "failure_cause": "Falla de sellos y barda de alfeizar sin pendiente",
    }


def test_parse_sparse_ocr_text_handles_split_labels_and_misread_degree_symbol():
    text = """
N*
obra (691)-n" filtración
Proyecto
en
que
se
Tipo de filtración: LOSA
detecta
EUCLIDES
Lugar de la filtración:
(dpto 2207)
3
ANALISIS DE CAUSA DE LA FALLA
Falla de sellos y barda de alfeizar sin pendiente
4
DESCRIPCIÓN DE LA REPARACIÓN
"""

    details = document_processor._parse_pdf_text(text)

    assert details["project_number"] == "691"
    assert details["project_name"] == "EUCLIDES"
    assert details["infiltration_location"] == "(dpto 2207)"
    assert details["failure_cause"] == "Falla de sellos y barda de alfeizar sin pendiente"


def test_complete_native_text_skips_ocr(monkeypatch):
    monkeypatch.setattr(document_processor, "_extract_native_text", lambda _: OCR_TEXT)

    def unexpected_ocr(_: bytes) -> str:
        raise AssertionError("OCR must not run for complete native text")

    monkeypatch.setattr(document_processor, "_ocr_pdf_text", unexpected_ocr)

    details = document_processor.extract_pdf_details(b"pdf")

    assert details["extraction_method"] == "native"
    assert details["failure_cause"] == "Falla de sellos y barda de alfeizar sin pendiente"


def test_image_only_pdf_uses_ocr(monkeypatch):
    monkeypatch.setattr(document_processor, "_extract_native_text", lambda _: "")
    monkeypatch.setattr(document_processor, "_ocr_pdf_text", lambda _: OCR_TEXT)

    details = document_processor.extract_pdf_details(b"pdf")

    assert details["extraction_method"] == "ocr"
    assert details["project_number"] == "691"
    assert details["project_name"] == "EUCLIDES"
    assert details["infiltration_location"] == "(dpto 2207)"
    assert details["failure_cause"] == "Falla de sellos y barda de alfeizar sin pendiente"


def test_partial_native_text_is_completed_by_ocr(monkeypatch):
    native_text = "N° obra: 691\nNombre proyecto: EUCLIDES"
    monkeypatch.setattr(document_processor, "_extract_native_text", lambda _: native_text)
    monkeypatch.setattr(document_processor, "_ocr_pdf_text", lambda _: OCR_TEXT)

    details = document_processor.extract_pdf_details(b"pdf")

    assert details["extraction_method"] == "hybrid"
    assert details["project_number"] == "691"
    assert details["project_name"] == "EUCLIDES"
    assert details["infiltration_location"] == "(dpto 2207)"
    assert details["failure_cause"] == "Falla de sellos y barda de alfeizar sin pendiente"


def test_unreadable_pdf_fails_after_ocr(monkeypatch):
    monkeypatch.setattr(document_processor, "_extract_native_text", lambda _: "")
    monkeypatch.setattr(document_processor, "_ocr_pdf_text", lambda _: "")

    with pytest.raises(ValueError, match="no extractable or OCR-readable text"):
        document_processor.extract_pdf_details(b"pdf")
