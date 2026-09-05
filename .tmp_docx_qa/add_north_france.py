from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


SOURCE = Path(r"D:\projects\travel-agent-bot\tours\programma_tura_измененный_актуальный.docx")
OUTPUT = Path(r"D:\projects\travel-agent-bot\.tmp_docx_qa\catalogue_with_north_france_v6.docx")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def paragraph_text(paragraph) -> str:
    return "".join(text.text or "" for text in paragraph.xpath(".//w:t", namespaces=NS))


def find_exact(root, text: str):
    matches = [
        paragraph
        for paragraph in root.xpath(".//w:body/w:p", namespaces=NS)
        if paragraph_text(paragraph) == text
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one exact paragraph, found {len(matches)}: {text!r}")
    return matches[0]


def find_nth(root, text: str, occurrence: int):
    matches = [
        paragraph
        for paragraph in root.xpath(".//w:body/w:p", namespaces=NS)
        if paragraph_text(paragraph) == text
    ]
    if len(matches) <= occurrence:
        raise RuntimeError(
            f"Expected occurrence {occurrence + 1}, found {len(matches)}: {text!r}"
        )
    return matches[occurrence]


def set_text_node(node, text: str) -> None:
    node.text = text
    if text.startswith(" ") or text.endswith(" "):
        node.set(XML_SPACE, "preserve")
    else:
        node.attrib.pop(XML_SPACE, None)


def set_paragraph_text(paragraph, text: str) -> None:
    nodes = paragraph.xpath(".//w:t", namespaces=NS)
    if not nodes:
        raise RuntimeError("Paragraph has no text node")
    set_text_node(nodes[0], text)
    for node in nodes[1:]:
        set_text_node(node, "")


def clear_clone_ids(paragraph) -> None:
    paragraph.attrib.pop("{http://schemas.microsoft.com/office/word/2010/wordml}paraId", None)
    paragraph.attrib.pop("{http://schemas.microsoft.com/office/word/2010/wordml}textId", None)


def append_before_section(body, paragraph) -> None:
    section_properties = body.find(f"{{{W_NS}}}sectPr")
    if section_properties is None:
        body.append(paragraph)
    else:
        body.insert(body.index(section_properties), paragraph)


def clone_with_text(template, text: str):
    paragraph = deepcopy(template)
    clear_clone_ids(paragraph)
    set_paragraph_text(paragraph, text)
    return paragraph


def clone_plain_paragraph(template, text: str):
    paragraph = deepcopy(template)
    clear_clone_ids(paragraph)
    paragraph_properties = paragraph.find(f"{{{W_NS}}}pPr")
    for child in list(paragraph):
        if child is not paragraph_properties:
            paragraph.remove(child)
    run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
    text_node = etree.SubElement(run, f"{{{W_NS}}}t")
    set_text_node(text_node, text)
    return paragraph


def update_document_xml(xml_bytes: bytes) -> bytes:
    root = etree.fromstring(xml_bytes, etree.XMLParser(remove_blank_text=False))
    if root.find(f".//{{{W_NS}}}body") is None:
        raise RuntimeError("Document body is missing")
    additions = []

    title_template = find_exact(root, "Французский поцелуй")
    page_break_template = title_template.getprevious()
    if page_break_template is None or not page_break_template.xpath(
        ".//w:br[@w:type='page']", namespaces=NS
    ):
        raise RuntimeError("Could not find the catalogue page-break template")
    blank_template = page_break_template.getprevious()
    if blank_template is None or paragraph_text(blank_template):
        raise RuntimeError("Could not find the catalogue blank-paragraph template")
    normal_template = find_exact(
        root,
        "Куда: Минск - Потсдам - Амстердам - Париж 3 дня - Люксембург - Трир - Минск",
    )
    programme_template = find_nth(
        root,
        "1 день , суббота: Выезд из Минска ориентировочно в 15.00. "
        "Выезд из Бреста ориентировочно 20.30. Прохождение границы.",
        1,
    )
    link_template = find_exact(
        root,
        "Ссылка на тур - https://docs.google.com/document/d/"
        "1dLsh0_1n4VVbLRaf1y2S06CJYMdoBn3u",
    )

    # Start the new tour on a fresh page, matching the catalogue's existing layout.
    page_break = deepcopy(page_break_template)
    clear_clone_ids(page_break)
    for text_node in page_break.xpath(".//w:t", namespaces=NS):
        set_text_node(text_node, "")
    page_breaks = page_break.xpath(".//w:br", namespaces=NS)
    if not page_breaks:
        run = etree.SubElement(page_break, f"{{{W_NS}}}r")
        page_breaks = [etree.SubElement(run, f"{{{W_NS}}}br")]
    page_breaks[0].set(f"{{{W_NS}}}type", "page")
    additions.append(page_break)

    lines = [
        (title_template, "Магия Нормандии"),
        (normal_template, "Виза - НУЖНА"),
        (
            normal_template,
            "Куда: Минск - Берлин - Гент - Брюссель* - Этрета* + Онфлёр* + "
            "Довиль/Трувиль* - Мон-Сен-Мишель* + Сен-Мало* - Руан - Брюгге - Кёльн - Минск",
        ),
        (normal_template, "Когда: 22.08.2026 - 30.08.2026 (2 места для туристов с визами)"),
        (normal_template, "22.05.2027 - 30.05.2027"),
        (normal_template, "19.06.2027 - 27.06.2027"),
        (normal_template, "24.07.2027 - 01.08.2027"),
        (normal_template, "14.08.2027 - 22.08.2027"),
        (normal_template, "Сколько стоит: 630 € на человека при проживании в 2 или 3 местном номере"),
        (normal_template, "Что включено в стоимость тура:"),
        (normal_template, "туруслуга"),
        (normal_template, "проезд автобусом"),
        (normal_template, "7 ночлегов в отелях"),
        (normal_template, "7 завтраков в отелях"),
        (normal_template, "услуги сопровождающего"),
        (normal_template, "обзорные экскурсии в Берлине, Генте, Руане, Брюгге, Кёльне"),
        (normal_template, "городские налоги"),
        (normal_template, "Что оплачивается дополнительно:"),
        (normal_template, "Обязательно:"),
        (normal_template, "медицинская страховка (оформляется самостоятельно)"),
        (normal_template, "При необходимости:"),
        (normal_template, "консульский сбор за открытие визы - 35 €"),
        (normal_template, "оплата ускоренного продвижения ко въезду на КПП при скоплении большого количества автобусов накануне выезда - 20 €"),
        (normal_template, "По желанию (*):"),
        (normal_template, "обзорная экскурсия по Познани (при благоприятном прохождении границы) - 10 €/ 5 € (несовершеннолетние)"),
        (normal_template, "экскурсия в Брюссель - 25 €"),
        (normal_template, "экскурсия Этрета + Онфлёр + Довиль/Трувиль - 50 € (билет в сады Этрета приобретается самостоятельно)"),
        (normal_template, "экскурсия Мон-Сен-Мишель + Сен-Мало - 50 €"),
        (normal_template, "аренда наушников для экскурсий - 10 €"),
        (normal_template, "Выездные экскурсии состоятся при минимальной группе 25 чел."),
        (normal_template, "Программа тура:"),
        (programme_template, "1 день, суббота: Выезд из Минска ориентировочно в 15.00. Прохождение границы."),
        (programme_template, "2 день, воскресенье: Переезд по территории Польши. При благоприятном прохождении границы - факультативная экскурсия по Познани*. Ночлег в транзитном отеле."),
        (programme_template, "3 день, понедельник: Переезд в Берлин. Обзорная экскурсия. Свободное время. Ночлег в Германии."),
        (programme_template, "4 день, вторник: Переезд в Гент. Обзорная экскурсия. По желанию - Брюссель*. Ночлег во Франции, в районе Руана."),
        (programme_template, "5 день, среда: Свободный день в Руане или факультативная поездка в Этрета*, Онфлёр*, Довиль/Трувиль*. Ночлег."),
        (programme_template, "6 день, четверг: Свободный день в Руане или факультативная поездка в Мон-Сен-Мишель* и Сен-Мало*. Ночлег."),
        (programme_template, "7 день, пятница: Обзорная экскурсия по Руану. Переезд в Брюгге, обзорная экскурсия. Ночлег в Германии."),
        (programme_template, "8 день, суббота: Переезд в Кёльн, обзорная экскурсия. Ночлег в Польше."),
        (programme_template, "9 день, воскресенье / утро понедельника: Выезд в Минск через Брест."),
    ]
    for template, text in lines:
        if text == "Виза - НУЖНА":
            additions.append(clone_plain_paragraph(template, text))
        else:
            additions.append(clone_with_text(template, text))

    blank_paragraph = deepcopy(blank_template)
    clear_clone_ids(blank_paragraph)
    additions.append(blank_paragraph)
    additions.append(
        clone_with_text(
            link_template,
            "Ссылка на тур - https://docs.google.com/document/d/1d1hNBDdRZME-yckgo47PDmDAXgKhVQm-w9xIARfpr6w/",
        )
    )
    additions.append(
        clone_with_text(
            link_template,
            "Ссылка на бронирование - https://sundita.by/tur/magiya-normandii/",
        )
    )

    insert_at = xml_bytes.rfind(b"<w:sectPr")
    if insert_at == -1:
        raise RuntimeError("Document section properties are missing")
    fragment = b"\n".join(etree.tostring(paragraph, encoding="UTF-8") for paragraph in additions)
    return xml_bytes[:insert_at] + b"\n" + fragment + b"\n" + xml_bytes[insert_at:]


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {OUTPUT}")

    with ZipFile(SOURCE, "r") as source_zip:
        new_document_xml = update_document_xml(source_zip.read("word/document.xml"))
        with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as output_zip:
            for item in source_zip.infolist():
                data = (
                    new_document_xml
                    if item.filename == "word/document.xml"
                    else source_zip.read(item.filename)
                )
                output_zip.writestr(item, data)

    from docx import Document

    with ZipFile(SOURCE, "r") as source_zip, ZipFile(OUTPUT, "r") as output_zip:
        if output_zip.testzip() is not None:
            raise RuntimeError("The generated DOCX ZIP is corrupt")
        changed_parts = [
            name
            for name in source_zip.namelist()
            if source_zip.getinfo(name).CRC != output_zip.getinfo(name).CRC
        ]
        if changed_parts != ["word/document.xml"]:
            raise RuntimeError(f"Unexpected changed package parts: {changed_parts}")

    document = Document(OUTPUT)
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    required = (
        "Магия Нормандии",
        "22.08.2026 - 30.08.2026 (2 места для туристов с визами)",
        "14.08.2027 - 22.08.2027",
        "https://docs.google.com/document/d/1d1hNBDdRZME-yckgo47PDmDAXgKhVQm-w9xIARfpr6w/",
        "https://sundita.by/tur/magiya-normandii/",
    )
    all_text = "\n".join(paragraphs)
    if any(value not in all_text for value in required):
        raise RuntimeError("New tour validation failed")
    if sum("Ссылка на бронирование" in paragraph for paragraph in paragraphs) != 6:
        raise RuntimeError("Expected six tour blocks after insertion")

    print(f"Created: {OUTPUT}")
    print("Changed package parts: word/document.xml only")
    print("Tours: 6")


if __name__ == "__main__":
    main()
