"""Тесты синхронизации туров из Google Drive. Сети нет — все ответы Drive поддельные."""

from datetime import date

import httpx
import pytest

from src.services import tour_sync as ts

TODAY = date(2026, 10, 3)
FUTURE = "12.12.2027 - 21.12.2027"
FOLDER = "folder_abc"
KEY = "test-key"

DOC_TEXT = """Тур Тестовый
Куда: Минск - Париж
Когда: 12.12.2027 - 21.12.2027
Сколько стоит: 100 €
Виза - не обязательно
Что включено: проезд
Туристическая компания оставляет за собой право
ЧУП «Сандита», телефоны
"""

BOOKING = "https://sundita.by/tur/test/"


class FakeResp:
    def __init__(self, json_data=None, text="", status=200):
        self._json = json_data
        self.text = text
        self._status = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self._status >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self._status}",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(self._status),
            )


def make_http(files=(), exports=None, fail_list=False, list_status=200):
    calls = {"exports": []}

    def http_get(url, params=None, timeout=None):
        if url == ts.DRIVE_FILES_URL:
            if fail_list:
                raise httpx.ConnectError("down")
            return FakeResp({"files": list(files)}, status=list_status)
        doc_id = url.rsplit("/", 2)[-2]
        calls["exports"].append(doc_id)
        return FakeResp(text=(exports or {}).get(doc_id, ""))

    http_get.calls = calls
    return http_get


def doc_entry(doc_id="doc1", name="Тур Тестовый", modified="2026-10-01T00:00:00Z"):
    return {"id": doc_id, "name": name, "mimeType": ts.GOOGLE_DOC_MIME, "modifiedTime": modified}


# --- Нормализация ------------------------------------------------------------


class TestNormalize:
    def test_bom_and_spaces(self):
        lines = ts.normalize_lines("﻿Заголовок  \n\n  Куда: Минск\t- Париж  \n")
        assert lines == ["Заголовок", "Куда: Минск - Париж"]

    def test_cut_footer(self):
        lines = ts.cut_footer(
            ["Куда: Минск", "Туристическая компания оставляет", "ЧУП «Сандита»"]
        )
        assert lines == ["Куда: Минск"]

    def test_cut_footer_chup_first(self):
        lines = ts.cut_footer(["Куда: Минск", "ЧУП «Сандита», адрес"])
        assert lines == ["Куда: Минск"]


class TestSeedBookings:
    def test_parses_base_text(self):
        base = "=== ТУР: Тур Тестовый ===\nСсылка на бронирование: https://sundita.by/tur/test/\n"
        assert ts.seed_bookings_from_text(base) == {"Тур Тестовый": "https://sundita.by/tur/test/"}

    def test_empty_base(self):
        assert ts.seed_bookings_from_text("") == {}


# --- Drive API ---------------------------------------------------------------


class TestListDriveDocs:
    def test_filters_only_docs(self):
        http = make_http(files=[
            doc_entry(),
            {"id": "img1", "name": "pic.png", "mimeType": "image/png", "modifiedTime": ""},
            {"id": "", "name": "noname", "mimeType": ts.GOOGLE_DOC_MIME, "modifiedTime": ""},
        ])
        docs = ts.list_drive_docs(http, FOLDER, KEY)
        assert docs == [{"id": "doc1", "name": "Тур Тестовый", "modified": "2026-10-01T00:00:00Z"}]

    def test_http_error_propagates(self):
        http = make_http(fail_list=True)
        with pytest.raises(httpx.HTTPError):
            ts.list_drive_docs(http, FOLDER, KEY)

    def test_key_never_logged(self, caplog):
        import logging

        http = make_http(files=[doc_entry()])
        with caplog.at_level(logging.DEBUG):
            ts.list_drive_docs(http, FOLDER, "SUPER-SECRET-KEY")
        assert "SUPER-SECRET-KEY" not in caplog.text


# --- Сборка ------------------------------------------------------------------


def build_two_docs(**over):
    raws = {
        "doc1": {"name": "Тур Тестовый", "modified": "m1", "text": DOC_TEXT},
        "doc2": {
            "name": "Тур Второй",
            "modified": "m1",
            "text": DOC_TEXT.replace("Тур Тестовый", "Тур Второй").replace("100 €", "200 €"),
        },
    }
    carried = {"doc1": BOOKING, "doc2": "https://sundita.by/tur/second/"}
    return ts.build_snapshot(raws, carried, today=TODAY, **over)


class TestBuildSnapshot:
    def test_happy_path(self):
        snap, skipped = build_two_docs()
        assert skipped == []
        assert len(snap["tours"]) == 2
        assert "Тур Тестовый" in snap["text"]
        assert "Виза: НУЖНА, но мы оказываем визовую поддержку" in snap["text"]
        assert "Туристическая компания" not in snap["text"]
        assert "ЧУП" not in snap["text"]
        assert len(snap["hash"]) == 64

    def test_tour_url_injected(self):
        snap, _ = build_two_docs()
        assert "https://docs.google.com/document/d/doc1" in snap["text"]
        assert "https://docs.google.com/document/d/doc2" in snap["text"]

    def test_booking_from_doc_text_wins(self):
        text = DOC_TEXT.replace(
            "Что включено: проезд",
            "Что включено: проезд\nСсылка на бронирование - https://sundita.by/tur/from-doc/",
        )
        raws = {"doc1": {"name": "Тур Тестовый", "modified": "m1", "text": text}}
        snap, skipped = ts.build_snapshot(raws, {"doc1": BOOKING}, today=TODAY)
        assert skipped == []
        assert snap["tours"][0]["booking_url"] == "https://sundita.by/tur/from-doc/"

    def test_skipped_without_booking(self):
        raws = {"doc9": {"name": "Тур Новый", "modified": "m1", "text": DOC_TEXT}}
        snap, skipped = ts.build_snapshot(raws, {}, today=TODAY)
        assert len(snap["tours"]) == 0
        assert skipped == ["Тур Новый (нет ссылки на бронирование)"]

    def test_duplicate_names_rejected(self):
        raws = {
            "doc1": {"name": "Одинаковый", "modified": "m1", "text": DOC_TEXT},
            "doc2": {"name": "Одинаковый", "modified": "m1", "text": DOC_TEXT},
        }
        carried = {"doc1": BOOKING, "doc2": BOOKING}
        with pytest.raises(ValueError, match="дублирующиеся"):
            ts.build_snapshot(raws, carried, today=TODAY)

    def test_sold_out_filtered(self):
        text = DOC_TEXT.replace(FUTURE, "12.12.2027 - 21.12.2027 (мест нет)")
        raws = {"doc1": {"name": "Тур Тестовый", "modified": "m1", "text": text}}
        snap, _ = ts.build_snapshot(raws, {"doc1": BOOKING}, today=TODAY)
        assert "мест нет" not in snap["text"]
        assert "Свободных дат нет" in snap["text"]


# --- Валидация и diff --------------------------------------------------------


class TestValidate:
    def test_empty_rejected(self):
        assert ts.validate_snapshot(0, 8, 1, 0.5) == (False, "пустой результат (0 туров)")

    def test_below_min_rejected(self):
        ok, reason = ts.validate_snapshot(2, 8, 3, 0.5)
        assert ok is False and "порога" in reason

    def test_drop_rejected(self):
        ok, reason = ts.validate_snapshot(3, 8, 1, 0.5)
        assert ok is False and "просадка" in reason

    def test_ok(self):
        assert ts.validate_snapshot(8, 8, 1, 0.5)[0] is True

    def test_first_run_no_drop_guard(self):
        assert ts.validate_snapshot(2, None, 1, 0.5)[0] is True


def snap_with(names):
    tours = [
        {"doc_id": f"doc{i}", "name": n, "booking_url": BOOKING, "modified": "m",
         "raw": "x", "section": f"=== ТУР: {n} ===\nСколько стоит: 100 €"}
        for i, n in enumerate(names)
    ]
    text = "\n\n".join(t["section"] for t in tours)
    import hashlib

    return {"tours": tours, "text": text,
            "hash": hashlib.sha256(text.encode()).hexdigest(), "built_at": "t"}


class TestDiff:
    def _snap(self, pairs):
        import hashlib

        tours = [
            {"doc_id": did, "name": n, "booking_url": BOOKING, "modified": "m",
             "raw": "x", "section": f"=== ТУР: {n} ===\nСколько стоит: 100 €"}
            for did, n in pairs
        ]
        text = "\n\n".join(t["section"] for t in tours)
        return {"tours": tours, "text": text,
                "hash": hashlib.sha256(text.encode()).hexdigest(), "built_at": "t"}

    def test_added_removed(self):
        old = self._snap([("old1", "A"), ("old2", "B")])
        new = self._snap([("old2", "B"), ("new1", "C")])
        diff = ts.diff_snapshots(old, new)
        assert diff["added"] == ["C"]
        assert diff["removed"] == ["A"]
        assert diff["changed"] == []

    def test_renamed(self):
        old = self._snap([("d1", "Старое")])
        new = self._snap([("d1", "Новое")])
        diff = ts.diff_snapshots(old, new)
        assert len(diff["changed"]) == 1 and "переименован" in diff["changed"][0]

    def test_price_change_noted(self):
        old = snap_with(["A"])
        new = snap_with(["A"])
        new["tours"][0]["section"] = "=== ТУР: A ===\nСколько стоит: 200 €"
        new["text"] = new["tours"][0]["section"]
        diff = ts.diff_snapshots(old, new)
        assert len(diff["changed"]) == 1 and "цена" in diff["changed"][0]

    def test_no_changes(self):
        # Две секции: между ними разделитель "\n\n", который при разборе
        # прилипает к хвосту — без rstrip каждая сборка выглядела бы изменённой.
        old = snap_with(["A", "B"])
        diff = ts.diff_snapshots(old, snap_with(["A", "B"]))
        assert diff == {"added": [], "removed": [], "changed": []}


class TestFormatMessage:
    def test_contains_markers(self):
        msg = ts.format_diff_message(
            {"added": ["X"], "removed": ["Y"], "changed": ["Z (цена)"]},
            ["W (нет ссылки на бронирование)"],
        )
        for marker in ("➕", "➖", "✏️", "⚠️", "X", "Y", "Z", "W"):
            assert marker in msg


# --- sync_now ----------------------------------------------------------------


class TestSyncNow:
    def test_disabled(self):
        snap, info = ts.sync_now(make_http(), "", "", None)
        assert (snap, info["status"]) == (None, "disabled")

    def test_unchanged(self):
        http = make_http(files=[doc_entry()], exports={"doc1": DOC_TEXT})
        prev, _ = ts.build_snapshot(
            {"doc1": {"name": "Тур Тестовый", "modified": "m1", "text": DOC_TEXT}},
            {"doc1": BOOKING}, today=TODAY,
        )
        prev["tours"][0]["modified"] = "2026-10-01T00:00:00Z"
        snap, info = ts.sync_now(http, FOLDER, KEY, prev, today=TODAY)
        assert info["status"] == "unchanged"
        assert snap["hash"] == prev["hash"]
        assert http.calls["exports"] == [], "неизменившееся не качаем заново"

    def test_empty_without_bookings_invalid(self):
        http = make_http(files=[doc_entry()], exports={"doc1": DOC_TEXT})
        snap, info = ts.sync_now(http, FOLDER, KEY, None, today=TODAY,
                                 carried_seed_text="",
                                 )
        # без брони в carried и seed — пропуск, результат пуст -> invalid
        assert info["status"] == "invalid"

    def test_ok_with_seed(self):
        base = "=== ТУР: Тур Тестовый ===\nСсылка на бронирование: " + BOOKING + "\n"
        http = make_http(files=[doc_entry()], exports={"doc1": DOC_TEXT})
        snap, info = ts.sync_now(http, FOLDER, KEY, None, base, today=TODAY)
        assert info["status"] == "ok"
        assert BOOKING in snap["text"]

    def test_error_on_list_failure(self):
        snap, info = ts.sync_now(make_http(fail_list=True), FOLDER, KEY, None)
        assert (snap, info["status"]) == (None, "error")

    def test_auth_error(self):
        http = make_http(list_status=403)
        snap, info = ts.sync_now(http, FOLDER, KEY, None)
        assert (snap, info["status"]) == (None, "auth_error")

    def test_partial_export_failure_reuses_old(self):
        prev, _ = ts.build_snapshot(
            {"doc1": {"name": "Тур Тестовый", "modified": "m1", "text": DOC_TEXT}},
            {"doc1": BOOKING}, today=TODAY,
        )
        prev["tours"][0]["modified"] = "2026-10-01T00:00:00Z"

        def http_get(url, params=None, timeout=None):
            if url == ts.DRIVE_FILES_URL:
                return FakeResp({"files": [doc_entry(modified="2026-10-02T00:00:00Z")]})
            raise httpx.ConnectError("down")

        snap, info = ts.sync_now(http_get, FOLDER, KEY, prev, today=TODAY)
        assert info["status"] in ("ok", "unchanged")
        assert "Тур Тестовый" in snap["text"]


# --- tour_loader: publish + snapshot -----------------------------------------


class TestLoaderPublishSnapshot:
    def test_publish_and_get(self):
        from src.services import tour_loader as tl

        old = tl.get_tours_text()
        try:
            tl.publish_tours_text("hello-sync")
            assert tl.get_tours_text() == "hello-sync"
        finally:
            tl.publish_tours_text(old)

    def test_snapshot_roundtrip(self, tmp_path):
        from src.services.tour_loader import load_snapshot, save_snapshot

        path = str(tmp_path / "snap.json")
        snap = {"tours": [], "text": "abc", "hash": "h", "built_at": "t"}
        save_snapshot(path, snap)
        assert load_snapshot(path) == snap

    def test_snapshot_missing_and_broken(self, tmp_path):
        from src.services.tour_loader import load_snapshot

        assert load_snapshot(str(tmp_path / "nope.json")) is None
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert load_snapshot(str(bad)) is None
        empty = tmp_path / "empty.json"
        empty.write_text('{"tours": []}', encoding="utf-8")
        assert load_snapshot(str(empty)) is None
