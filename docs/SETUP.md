# Локальное окружение и первый запуск

Для переноса существующей работы сначала прочитай [гайд Windows → Mac](CODEX-WINDOWS-TO-MAC.md). В GitHub может отсутствовать часть локальной работы и прямых серверных выкладок. Клонирование восстанавливает сохранённую Git-версию.

## Требования

- На исходном ноутбуке Python 3.12.13; это начальная точка воспроизведения, не доказательство совместимости всех функций с Mac.
- Git; Node.js нужен инструментам агента и скриптам `.mjs`.
- Настройки и доступ к интеграциям — под выбранный разрешённый сценарий.
- Production — Windows с Cloudflare Tunnel. Dockerfile и Compose-файла в текущем дереве нет.

## Получить исходники

Если нужная версия уже сохранена на GitHub:

```bash
git clone https://github.com/AuTh00r/travel-ag.git travel-agent-bot
cd travel-agent-bot
```

Для незакоммиченной работы восстанови полную файловую копию в новый каталог, включая `.git`, `.kiro` и новые файлы. Не сливай её вслепую с прежней копией.

## Создать окружение

На Mac, после сохранения Windows `.venv` отдельно:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

На Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
```

Большинство зависимостей заданы через `>=`; новая установка может отличаться от старой. Сверяй инвентарь версий. GigaAM из `requirements-gigaam.txt` устанавливается **в отдельное окружение**.

## Настройки и данные

[ENV-SETUP](ENV-SETUP.md), [Settings](../src/config.py), [шаблон](../.env.example). Для новой тестовой среды создай `.env` из шаблона, только если его ещё нет. При миграции сохрани рабочий `.env` защищённо и адаптируй пути в копии. Не заменяй настройки шаблоном.

Сохрани `data/`, `credentials/`, `tours/` и внешние модели отдельно. FAQ TXT намеренно отсутствуют: [пояснение](../data/faq/README.md).

## Offline-проверки

```bash
python -m pytest tests/ -q
python -m ruff check src tests
```

`conftest.py` содержит Playwright fixtures и изоляцию SQLite/httpx. Если проверкам нужен Chromium:

```bash
python -m playwright install chromium
```

Число тестов определяй по текущему запуску или `python -m pytest tests/ --collect-only -q`, а не по старой цифре в документе.

## Локальный сервер

Сначала настрой тестовые интеграции и копию данных. Старт с production `.env` может включить фоновые воркеры, синхронизацию и доставку очереди. Не запускай случайно второй рабочий экземпляр.

```bash
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

В другом терминале:

```bash
curl --fail http://127.0.0.1:8000/health
```

Остановка — `Ctrl+C`. Windows media-декодер требует запуска без reload и нескольких workers. На Mac story/video требует отдельной адаптации Windows-пути.

Далее: [архитектура](ARCHITECTURE.md), [разработка](DEVELOPMENT.md), [отдельный процесс деплоя](DEPLOY.md), [SSH](SSH-REMOTE-ACCESS-SETUP.md).
