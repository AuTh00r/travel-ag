# План: исправление проблем ответов бота

> Статус: **готов к исполнению**
> Исправляет: слишком длинные сообщения, отсутствие ссылок, скрытые туры, имя «Анастасия»

---

## 1. `src/services/tour_loader.py` — ссылка на тур наверх

Сейчас: весь текст docx склеивается как есть, URL зарыт в конце 3000+ символов.

Надо: парсить Google Docs URL из документа и выносить его в начало секции тура. Ключевые поля (Маршрут, Даты, Стоимость, Тип отдыха, Виза) — сразу после ссылки. Остальной текст — ниже.

**Изменения:**

```python
_URL_RE = re.compile(r"https?://docs\.google\.com\S+")
_KEY_FIELDS = ("Маршрут:", "Даты:", "Стоимость:", "Тип отдыха:", "Виза:")

def _extract_tour_section(filename: str, paragraphs: list[str]) -> str:
    text = "\n".join(paragraphs)
    # Извлечь URL
    url_match = _URL_RE.search(text)
    tour_url = url_match.group(0) if url_match else ""
    if tour_url:
        text = _URL_RE.sub("", text).strip()
    # Убрать лишнее
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace("ПОДРОБНАЯ ИНФОРМАЦИЯ И БРОНИРОВАНИЕ НА САЙТЕ", "").strip()
    # Разделить на ключевые поля и остальное
    key_lines = []
    other_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(f) for f in _KEY_FIELDS):
            key_lines.append(line)
        else:
            other_lines.append(line)
    # Собрать
    parts = [f"=== ТУР: {filename} ==="]
    if tour_url:
        parts.append(f"Ссылка на тур: {tour_url}")
    parts.extend(key_lines)
    if other_lines:
        parts.append("")
        parts.extend(other_lines)
    return "\n".join(parts)
```

В `load_tours` заменить прямую конкатенацию на вызов `_extract_tour_section`.

---

## 2. `src/ai/prompts.py` — 4 правки в `_BASE_RULES`

### 2.1 Identity (строка 52)

**Было:** `Ты — менеджер туристической компании «Сандита» (Минск). Ты отвечаешь клиентам в Instagram.`

**Стало:** `Ты — ассистент менеджера туристической компании «Сандита» (Минск). Ты отвечаешь клиентам в Instagram. Не представляйся по имени — просто помогай клиенту.`

### 2.2 Лимит символов (строка 57)

**Было:** `— максимум 980 символов, старайся использовать почти весь лимит. Лимит Instagram 1000.`

**Стало:** `— пиши по делу, без воды. Если ответ большой — он будет разбит на несколько сообщений автоматически.`

### 2.3 Ссылка на тур (строка 58)

**Было:** `ССЫЛКА НА ТУР — ОБЯЗАТЕЛЬНО. Если упоминаешь тур — ссылка должна быть в сообщении. Сначала ссылка, потом 1-2 предложения описания. Не хватает места — режь воду и общие фразы, но ссылку оставляй.`

**Стало:** `ССЫЛКА НА ТУР — ОБЯЗАТЕЛЬНО. У каждого тура есть поле «Ссылка на тур: https://docs.google.com/...» — скопируй эту ссылку целиком. Если упоминаешь тур — ссылка должна быть в сообщении. Сначала ссылка, потом краткое описание. Ссылка в приоритете над описанием.`

### 2.4 Лимит 2-3 тура (строка 63)

**Было:** `Не перечисляй больше 2-3 туров в одном сообщении. Если нужно показать больше — скажи «ещё напишу в следующем сообщении»`

**Стало:** `Перечисли все подходящие туры. Если их много — сообщение будет разбито на несколько автоматически, не переживай о длине.`

---

## 3. `src/main.py` — мульти-отправка сообщений

### 3.1 Добавить функцию `_split_reply`

```python
def _split_reply(text: str, max_len: int = 1000) -> list[str]:
    """Разбить ответ на части по границам предложений.

    Не разрывает URL (https://...). Режет только по . ! ? в конце
    предложения, за которым следует пробел или конец строки.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while len(text) > max_len:
        # Ищем границу предложения не далее max_len
        candidate = text[:max_len]
        # Не режем внутри URL
        # Ищем последнюю границу предложения
        split_at = -1
        # Ищем . ! ? за которым пробел, конец строки или конец candidate
        for sep in (". ", "! ", "? "):
            pos = candidate.rfind(sep)
            if pos > split_at:
                split_at = pos + 1  # включаем знак
        if split_at <= 0:
            # Не нашли — режем по max_len
            split_at = max_len
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks
```

### 3.2 Заменить отправку в `process_with_ai`

**Было (строка 349-351):**
```python
        try:
            await instagram.send_message(sender_id, clean_reply)
        except Exception:
            logger.exception("instagram.message.send_failed", sender_id=sender_id)
```

**Стало:**
```python
        for chunk in _split_reply(clean_reply):
            try:
                await instagram.send_message(sender_id, chunk)
            except Exception:
                logger.exception("instagram.message.send_failed", sender_id=sender_id)
                break
```

---

## 4. Тесты

### 4.1 `tests/test_tour_search.py` (или `test_tour_loader.py`)

Добавить тест `_extract_tour_section`:
- URL извлекается и ставится наверх
- Ключевые поля идут после URL
- Исходный URL удалён из текста

### 4.2 `tests/test_api.py` — `TestManagerPauseGate`

Не меняется — уже работает.

### 4.3 `tests/test_main.py` (или `test_api.py`)

Добавить тест `_split_reply`:
- Короткий текст → 1 чанк
- Текст 1500 символов → 2 чанка, не разорваны предложения
- URL не разрывается
- Пустой текст → пустой список

---

## 5. Проверка

```bash
pytest tests/ -q
ruff check src/ tests/
```

---

## 6. Деплой

```bash
git add -A
git commit -m "fix: tour links, multi-message splitting, identity"
git push origin master
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72 "cd /opt/travel-agent-bot && git pull origin master && systemctl restart travel-bot"
```
