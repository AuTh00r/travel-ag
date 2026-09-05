from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


SOURCE = Path(r"D:\projects\travel-agent-bot\tours\programma_tura_измененный.docx")
EXPECTED = Path(
    r"D:\projects\travel-agent-bot\tours\programma_tura_измененный_актуальный.docx"
)
OUTPUT = Path(r"D:\projects\travel-agent-bot\.tmp_docx_qa\updated_minimal_compact_dates.docx")

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


def replace_once(paragraph, old: str, new: str) -> None:
    nodes = paragraph.xpath(".//w:t", namespaces=NS)
    full_text = "".join(node.text or "" for node in nodes)
    if full_text.count(old) != 1:
        raise RuntimeError(
            f"Expected one replacement in paragraph, found {full_text.count(old)}: {old!r}"
        )

    start = full_text.index(old)
    end = start + len(old)
    offsets = []
    cursor = 0
    for node in nodes:
        node_text = node.text or ""
        offsets.append((cursor, cursor + len(node_text)))
        cursor += len(node_text)

    first = next(i for i, (_, node_end) in enumerate(offsets) if node_end > start)
    last = next(
        i
        for i, (node_start, node_end) in enumerate(offsets)
        if node_start < end <= node_end
    )
    first_start, _ = offsets[first]
    last_start, _ = offsets[last]
    prefix = (nodes[first].text or "")[: start - first_start]
    suffix = (nodes[last].text or "")[end - last_start :]

    if first == last:
        set_text_node(nodes[first], prefix + new + suffix)
        return

    set_text_node(nodes[first], prefix + new)
    for index in range(first + 1, last):
        set_text_node(nodes[index], "")
    set_text_node(nodes[last], suffix)


def remove_paragraph(paragraph) -> None:
    paragraph.getparent().remove(paragraph)


def insert_date_before(reference, template, text: str) -> None:
    new_paragraph = deepcopy(template)
    set_paragraph_text(new_paragraph, text)
    reference.addprevious(new_paragraph)


def update_document_xml(xml_bytes: bytes) -> bytes:
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_bytes, parser)

    first_vdp_date = find_exact(
        root, "Когда: 01.07.2026 - 05.07.2026 (12 мест)"
    )
    set_paragraph_text(first_vdp_date, "Когда: 05.08.2026 - 09.08.2026")
    remove_paragraph(find_exact(root, "05.08.2026 - 09.08.2026"))

    vdp_warsaw = find_exact(
        root,
        "2 день (первый день программы, четверг): Прибытие в Варшаву. "
        "обзорная экскурсия. Рыночную площадь с символом города – русалочкой, "
        "кафедральный собор св. Иоанна, королевский замок (без посещения "
        "интерьеров), Краковское предместье с дворцами польской аристократии "
        "и другие значимые достопримечательности Старого города. Переезд в "
        "транзитный отель у границы с Германией на ночлег.",
    )
    replace_once(
        vdp_warsaw,
        "Переезд в транзитный отель у границы с Германией на ночлег.",
        "Переезд в транзитный отель у границы с Германией на ночлег. "
        "Внимание! В случае существенной задержки при прохождении границы "
        "возможен перенос экскурсии по Варшаве на воскресенье.",
    )

    france_route = find_exact(
        root,
        "Куда: Минск - Бамберг - Ротенбург на Таубере - Страсбург - "
        "Баден-Баден - Люцерн - Лаутербруннен - Мюррен - Дижон- "
        "Кольмар-Риквир - Нюрнберг - Минск",
    )
    for city in ("Баден-Баден", "Люцерн", "Лаутербруннен", "Мюррен", "Дижон"):
        replace_once(france_route, city, city + "*")

    france_first_date = find_exact(root, "Когда: 12.12.2026 - 21.12.2026")
    france_cost = find_exact(
        root,
        "Сколько стоит: 630 € на человека при проживании в 2 или 3 местном номере",
    )
    for date in (
        "20.03.2027 - 28.03.2027",
        "08.05.2027 - 16.05.2027",
        "25.09.2027 - 03.10.2027",
        "11.12.2027 - 19.12.2027",
    ):
        insert_date_before(france_cost, france_first_date, date)

    france_murren = find_exact(
        root,
        "5 день, среда: Завтрак в отеле. Свободный день в Мюлузе либо "
        "выездная экскурсия по желанию за доплату в Люцерн- "
        "Лаутербруннен+Мюррен*. Возвращение в Мюлуз (или его пригород). "
        "Ночлег в отеле.",
    )
    replace_once(
        france_murren,
        "Возвращение в Мюлуз (или его пригород).",
        "В случае ревизионных работ или оползней канатная дорога в Мюррен "
        "может не работать; тогда проводится альтернативная экскурсионная "
        "программа с гидом по маршруту Лаутербруннен - Гриндельвальд - "
        "Интерлакен. Возвращение в Мюлуз (или его пригород).",
    )

    france_dijon = find_exact(
        root,
        "6 день, четверг: Завтрак в отеле. Свободный день в Мюлузе. Для "
        "желающих выезд в столицу Бургундии - Дижон. Возвращение в Мюлуз "
        "( Или его пригород). Ночлег в отеле.",
    )
    replace_once(
        france_dijon,
        "Для желающих выезд в столицу Бургундии - Дижон.",
        "Для желающих выезд в столицу Бургундии - Дижон* для "
        "самостоятельной прогулки-квеста.",
    )

    berlin_cost = find_exact(
        root,
        "Сколько стоит: 220 € (на человека при проживании в 2-местном номере)",
    )
    replace_once(berlin_cost, "220 € (", "220 € без скрытых доплат! (")

    berlin_transfer = find_nth(
        root,
        "Внимание! в случае перегруженности границы и возникновении "
        "необходимости довоза в ожидающий автобус, стоимость тура "
        "увеличивается на 20 €",
        1,
    )
    replace_once(
        berlin_transfer,
        "довоза в ожидающий автобус",
        "довоза в ожидающий в очереди автобус",
    )

    berlin_headphones = find_nth(root, "наушники по программе", 1)
    set_paragraph_text(
        berlin_headphones, "использование наушников во все экскурсионные дни"
    )

    berlin_return = find_exact(
        root,
        "5 день (день приезда, воскресенье): Прибытие домой в первой половине дня.",
    )
    replace_once(
        berlin_return,
        "Прибытие домой в первой половине дня.",
        "Прибытие домой рано утром.",
    )

    french_first_date = find_exact(
        root, "Когда: 20.06.2026 - 28.06.2026 (мест нет)"
    )
    set_paragraph_text(
        french_first_date,
        "Когда: 18.07.2026 - 26.07.2026 (2 места для туристов с визами)",
    )
    remove_paragraph(
        find_exact(
            root, "18.07.2026 - 26.07.2026 (2 места для туристов с визами)"
        )
    )

    set_paragraph_text(
        find_exact(root, "12.09.2026 - 20.09.2026 (мест нет)"),
        "12.09.2026 - 20.09.2026 (2 места для туристов с визами)",
    )
    set_paragraph_text(
        find_exact(root, "24.10.2026 - 01.11.2026 (осталось 2 места)"),
        "24.10.2026 - 01.11.2026 (мест нет)",
    )

    french_template = find_exact(root, "19.12.2026 - 27.12.2026")
    french_cost = find_exact(
        root,
        "Сколько стоит: 630 € (на человека при проживании в 2 или 3 местном номере)",
    )
    for date in (
        "13.02.2027 - 21.02.2027; 06.03.2027 - 14.03.2027",
        "08.05.2027 - 16.05.2027; 12.06.2027 - 20.06.2027",
        "10.07.2027 - 18.07.2027; 07.08.2027 - 15.08.2027",
        "18.09.2027 - 26.09.2027; 16.10.2027 - 24.10.2027",
        "06.11.2027 - 14.11.2027; 04.12.2027 - 12.12.2027",
    ):
        insert_date_before(french_cost, french_template, date)

    paragraphs = root.xpath(".//w:body/w:p", namespaces=NS)
    if len(paragraphs) != 214:
        raise RuntimeError(f"Unexpected paragraph count: {len(paragraphs)}")

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )


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

    from docx import Document

    actual_text = [paragraph.text for paragraph in Document(OUTPUT).paragraphs]
    required_dates = (
        "13.02.2027 - 21.02.2027",
        "06.03.2027 - 14.03.2027",
        "08.05.2027 - 16.05.2027",
        "12.06.2027 - 20.06.2027",
        "10.07.2027 - 18.07.2027",
        "07.08.2027 - 15.08.2027",
        "18.09.2027 - 26.09.2027",
        "16.10.2027 - 24.10.2027",
        "06.11.2027 - 14.11.2027",
        "04.12.2027 - 12.12.2027",
    )
    all_text = "\n".join(actual_text)
    if any(date not in all_text for date in required_dates):
        raise RuntimeError("A 2027 French Kiss date is missing")

    print(f"Created: {OUTPUT}")
    print("Changed package parts: word/document.xml only")
    print(f"Paragraphs: {len(actual_text)}")


if __name__ == "__main__":
    main()
