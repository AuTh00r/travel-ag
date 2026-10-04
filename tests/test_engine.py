from unittest.mock import AsyncMock, patch

import pytest

from src.main import _extract_escalation, _strip_markers


# --- Marker parsing ---


class TestExtractEscalation:
    def test_extract_escalation_with_context(self):
        text = "ответ\n\n===МЕНЕДЖЕР===\nПричина: просит менеджера\nКонтекст: ищет тур в Турцию\n===МЕНЕДЖЕР==="
        result = _extract_escalation(text)
        assert result == {
            "reason": "просит менеджера",
            "context": "ищет тур в Турцию",
            "type": "Нужен звонок",
        }

    def test_extract_escalation_without_context(self):
        text = "ответ\n\n===МЕНЕДЖЕР===\nПричина: просит менеджера\n===МЕНЕДЖЕР==="
        result = _extract_escalation(text)
        assert result == {
            "reason": "просит менеджера",
            "context": "просит менеджера",
            "type": "Нужен звонок",
        }

    def test_extract_escalation_with_name_and_phone(self):
        text = "ответ\n\n===МЕНЕДЖЕР===\nТип: консультация\nПричина: просит менеджера\nКонтекст: ищет тур\nИмя: Иван\nТелефон: +375291234567\n===МЕНЕДЖЕР==="
        result = _extract_escalation(text)
        assert result == {
            "reason": "просит менеджера",
            "context": "ищет тур",
            "name": "Иван",
            "phone": "+375291234567",
            "type": "консультация",
        }

    def test_extract_escalation_with_review_type(self):
        text = "ответ\n\n===МЕНЕДЖЕР===\nТип: отзыв\nПричина: клиент оставил отзыв о туре\nКонтекст: благодарит за организацию\n===МЕНЕДЖЕР==="
        result = _extract_escalation(text)
        assert result == {
            "reason": "клиент оставил отзыв о туре",
            "context": "благодарит за организацию",
            "type": "отзыв",
        }

    def test_extract_escalation_no_marker(self):
        assert _extract_escalation("обычный ответ") is None


class TestStripMarkers:
    def test_strips_escalation_marker(self):
        text = "Привет!\n\n===МЕНЕДЖЕР===\nПричина: тест\n===МЕНЕДЖЕР==="
        result = _strip_markers(text)
        assert "===МЕНЕДЖЕР===" not in result
        assert "Привет!" in result


# --- Prompt building ---


def test_build_full_prompt_includes_tours():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="=== ТУР: Турция ===\nПляж",
        faq_context="",
        history=[],
        message="Хочу тур",
    )
    assert len(messages) == 2  # system + user
    assert "Турция" in messages[0].content
    assert messages[1].content == "Хочу тур"


def test_build_full_prompt_includes_history():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="",
        history=[
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте!"},
        ],
        message="Хочу тур",
    )
    assert len(messages) == 4  # system + user + assistant + user
    assert messages[1].content == "Привет"
    assert messages[2].content == "Здравствуйте!"


def test_build_full_prompt_includes_faq():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="Виза в Турцию делается за 5 дней",
        history=[],
        message="Нужна виза?",
    )
    assert "Виза в Турцию" in messages[0].content


def test_build_full_prompt_distinguishes_ambiguous_query_from_attachment():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="",
        history=[],
        message="Сколько стоит?",
    )
    system_prompt = messages[0].content
    assert "ОДИН конкретный уточняющий вопрос" in system_prompt
    assert "одновременно сообщи, что передаёшь запрос менеджеру" in system_prompt
    assert "Только если ТЕКУЩЕЕ сообщение содержит служебную пометку" in system_prompt


# --- DeepSeek prefix cache ---
#
# DeepSeek матчит кэш только по полному совпадению префикса с нулевого токена
# (api-docs.deepseek.com/guides/kv_cache), поэтому всё меняющееся между
# вызовами обязано быть в хвосте промпта. Раньше `Сейчас: ЧЧ:ММ` стоял в
# первых строках и обнулял кэш каждую минуту — ~30 тыс. знаков входа шли по
# цене cache miss вместо cache hit (в 50 раз дороже).


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def test_system_prompt_prefix_stable_across_minutes():
    """Смена минуты не должна менять ничего, кроме хвоста промпта."""
    from src.ai.prompts import _build_system

    tours = "=== ТУР: Турция ===\nПляж"
    at_1015 = _build_system(tours, "", current_time="10:15")
    at_1016 = _build_system(tours, "", current_time="10:16")

    assert at_1015 != at_1016, "время обязано попадать в промпт"
    shared = _common_prefix_len(at_1015, at_1016)
    assert shared / len(at_1015) > 0.95, (
        f"общий префикс всего {shared} из {len(at_1015)} знаков — "
        "что-то переменное уехало в начало промпта и ломает кэш DeepSeek"
    )


def test_tours_base_precedes_variable_blocks():
    """База туров — самая крупная статика, она обязана идти до FAQ и времени."""
    from src.ai.prompts import _build_system

    prompt = _build_system(
        "=== ТУР: Турция ===\nПляж",
        "Вопрос: нужна ли виза?",
        current_time="10:15",
    )
    assert prompt.index("=== ТУР: Турция ===") < prompt.index("нужна ли виза?")
    assert prompt.index("нужна ли виза?") < prompt.index("Сейчас: 10:15")


def test_current_time_is_last_block():
    from src.ai.prompts import _build_system

    prompt = _build_system("", "", current_time="10:15")
    assert prompt.rstrip().endswith(
        "Это поле «Сейчас» из правила [ЧАСЫ] в разделе КОНЦОВКА."
    )


class TestPromptRules:
    """Правила, которые уже ломались в проде — держим тестами."""

    def _system(self, tours_text: str = "") -> str:
        from src.ai.prompts import _build_system

        return _build_system(tours_text, "", current_time="10:15")

    def test_russian_only(self):
        """Разрешение английского было временным, на Meta App Review."""
        prompt = self._system()
        assert "Отвечай только по-русски" in prompt
        assert "английском" not in prompt

    def test_visa_support_never_called_visa_free(self):
        """Клиенты читали «не обязательно» как «поездка без визы»."""
        prompt = self._system()
        assert "визовую поддержку" in prompt
        assert "«виза не нужна», «без визы», «виза не требуется» для таких туров ЗАПРЕЩЕНЫ" in prompt

    def test_visa_has_three_states(self):
        from src.services.tour_loader import (
            VISA_NOT_NEEDED,
            VISA_REQUIRED,
            VISA_SUPPORTED,
        )

        prompt = self._system()
        # Промпт обязан описывать ровно те значения, которые кладёт загрузчик.
        for state in (VISA_REQUIRED, VISA_SUPPORTED, VISA_NOT_NEEDED):
            head = state.split("—")[0].split(",")[0].strip()
            assert head in prompt, head

    def test_dates_hidden_by_default_shown_on_request(self):
        prompt = self._system()
        assert "ДАТЫ УЖЕ ОТФИЛЬТРОВАНЫ" in prompt
        assert "Свободных дат нет" in prompt
        # Даты не называем по умолчанию, только по явной просьбе клиента.
        assert "по умолчанию НЕ называй" in prompt
        assert "актуальные даты смотрите по ссылке на тур" in prompt
        assert "Только если клиент явно попросил даты" in prompt
        # Старое правило требовало от модели самой сравнивать даты и
        # перечислять ВСЕ заезды — теперь это делает загрузчик.
        assert "ФИЛЬТР ДАТ" not in prompt
        assert "ВСЕ будущие даты" not in prompt
        # Старого поведения «даты всегда» быть не должно.
        assert "указывай даты из поля" not in prompt

    def test_male_gender_consistent(self):
        """«Пол — мужской» противоречил примеру «я передала… она свяжется»."""
        prompt = self._system()
        assert "Пол — мужской" in prompt
        assert "передала" not in prompt
        assert "она свяжется" not in prompt

    def test_no_stale_promos_in_prompt(self):
        """Протухшие акции не должны жить в промпте: дедлайн посольства
        02.10.2026 прошёл, повышение цен с 01.10 — тоже, актуальные данные
        только в турах по ссылкам."""
        prompt = self._system()
        assert "02.10.2026" not in prompt
        assert "посольство" not in prompt.lower()
        assert "на следующей неделе" not in prompt


def test_escalation_limit_block_does_not_shift_prefix():
    """Переключение лимита эскалаций не должно двигать базу туров."""
    from src.ai.prompts import _build_system

    tours = "=== ТУР: Турция ===\nПляж"
    under = _build_system(tours, "", escalation_count=0, current_time="10:15")
    over = _build_system(tours, "", escalation_count=3, current_time="10:15")

    assert "ЛИМИТ ИСЧЕРПАН" in over and "ЛИМИТ ИСЧЕРПАН" not in under
    shared = _common_prefix_len(under, over)
    assert shared > under.index("=== ТУР: Турция ===") + len(tours)


# --- Integration smoke test ---


@pytest.mark.asyncio
async def test_process_with_ai_smoke():
    """Проверяет, что process_with_ai не падает при вызове с замоканным LLM."""
    fake_response = AsyncMock()
    fake_response.content = "Здравствуйте! Чем могу помочь?"

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=fake_response)

    patches = [
        patch("src.services.llm.get_llm", return_value=fake_llm),
        patch("src.services.tour_loader.get_tours_text", return_value=""),
        patch("src.db.faq_db.search_faq", return_value=[]),
        patch("src.main.save_session"),
        patch("src.main.instagram.send_message"),
        patch("src.main.instagram.get_username", return_value=None),
    ]
    for p in patches:
        p.start()

    try:
        await process_with("test_user", "Привет")
    except Exception as e:
        pytest.fail(f"process_with_ai raised: {e}")
    finally:
        for p in patches:
            p.stop()


async def process_with(sender_id: str, text: str) -> None:
    """Helper — вызывает process_with_ai."""
    from src.main import process_with_ai

    await process_with_ai(sender_id, text)
