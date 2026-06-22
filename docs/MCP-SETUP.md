# MCP‑серверы для агента — Инструкция по установке

## Что установить

Для проекта travel-agent-bot нужно установить **2 MCP‑сервера**:

1. **Google Sheets MCP** — прямой доступ к Google Sheets (база туров + заявки)
2. **Google Drive MCP** — доступ к Google Docs (описания туров + FAQ)

---

## Установка через ZCode

### Способ 1: Через npx (рекомендуется)

Добавьте в файл `~/.zcode/mcp.json` (или создайте его):

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic-ai/mcp-server-google-sheets"
      ],
      "env": {
        "GOOGLE_SHEETS_API_KEY": "ВАШ_GOOGLE_API_KEY"
      }
    },
    "google-drive": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic-ai/mcp-server-gdrive"
      ],
      "env": {
        "GOOGLE_DRIVE_API_KEY": "ВАШ_GOOGLE_API_KEY"
      }
    }
  }
}
```

### Способ 2: Как глобальный MCP (без npm)

Если у агента нет доступа к npm/npx, можно установить MCP-серверы как Python-пакеты:

```bash
# Google Sheets MCP (через Google API)
pip install google-api-python-client google-auth-httplib2

# Создать MCP-сервер как модуль проекта:
# src/mcp/google_sheets_server.py
```

---

## Получение Google API Key

1. Зайдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте проект (или выберите существующий)
3. Включите API:
   - Google Sheets API
   - Google Drive API
4. Создайте credentials:
   - **API Key** — для простого чтения (если таблицы публичные)
   - **OAuth 2.0 Service Account** — для чтения/записи приватных таблиц

### Service Account (рекомендуется)

```bash
# 1. Создать Service Account в Google Cloud Console
# 2. Скачать JSON-ключ
# 3. Поделиться Google Sheets с email Service Account
# 4. Указать путь к файлу в конфиге
```

---

## Альтернативные MCP-серверы

Если официальные MCP от Anthropic не подходят, вот альтернативы:

### Google Sheets MCP (от ModelContextProtocol)
```json
{
  "mcpServers": {
    "gsheets": {
      "command": "npx",
      "args": ["-y", "mcp-google-sheets"]
    }
  }
}
```

### Универсальный Google MCP
```json
{
  "mcpServers": {
    "google": {
      "command": "npx",
      "args": ["-y", "google-mcp-server"],
      "env": {
        "GOOGLE_API_KEY": "ВАШ_KEY"
      }
    }
  }
}
```

---

## Зачем эти MCP агенту

| MCP | Зачем | Пример использования агентом |
|---|---|---|
| **Google Sheets** | Чтение базы туров, проверка записи заявок | «Покажи все туры в Турцию до $1500» → агент читает таблицу и видит данные |
| **Google Drive/Docs** | Проверка ссылок на описания туров, загрузка FAQ | «Проверь, работает ли ссылка на описание тура "Анталья"» → агент читает документ |

Без MCP агенту придётся писать тестовые скрипты и запускать их вручную
для проверки данных. С MCP — он видит данные прямо в сессии.

---

## Важное замечание

MCP-серверы — это **инструменты отладки для агента**, а не часть
продакшен-кода. В продакшене бот использует Google Sheets API напрямую
через `src/services/google_sheets.py`. MCP нужен, чтобы агент мог
проверять данные в реальном времени при разработке.
