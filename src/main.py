from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from structlog import get_logger

from src.channels.instagram import InstagramChannel
from src.db.sessions import (
    get_requests_by_client,
    get_session,
    save_session,
    update_request_status,
)
from src.services.google_sheets import GoogleSheetsService

logger = get_logger()

instagram = InstagramChannel()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.db.faq_db import load_faq_to_chroma

    try:
        count = load_faq_to_chroma()
        logger.info("faq.ready", entries=count)
    except Exception:
        logger.exception("faq.load_failed")
    yield


app = FastAPI(
    title="Travel Agent Bot",
    description="ИИ-помощник турагентства",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- API управления заявками ---


class StatusUpdateRequest(BaseModel):
    status: str


REQUEST_STATUSES = {"Новая", "В обработке", "Подтверждена", "Оплачена"}


@app.get("/api/requests/{client_id}")
async def get_client_requests(client_id: str):
    requests = await get_requests_by_client(client_id)
    if not requests:
        raise HTTPException(status_code=404, detail="Заявки не найдены")
    return {"client_id": client_id, "requests": requests}


@app.patch("/api/requests/{client_id}/status")
async def update_request_status_endpoint(client_id: str, body: StatusUpdateRequest):
    if body.status not in REQUEST_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Неверный статус. Допустимые: {', '.join(sorted(REQUEST_STATUSES))}",
        )

    # Обновить в SQLite
    updated = await update_request_status(client_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # Попробовать обновить в Google Sheets (best-effort)
    try:
        requests_data = await get_requests_by_client(client_id)
        if requests_data:
            req = requests_data[0]
            sheets = GoogleSheetsService()
            await sheets.update_request_status(
                name=req.get("name", ""),
                phone=req.get("phone", ""),
                new_status=body.status,
            )
    except Exception:
        logger.exception("google_sheets.status_update_failed", client_id=client_id)

    return {"client_id": client_id, "status": body.status, "updated": True}


@app.get("/webhook/instagram")
async def verify_instagram_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
):
    return await instagram.verify_webhook(hub_mode, hub_challenge, hub_verify_token)


async def process_with_ai(sender_id: str, text: str) -> None:
    from src.ai.engine import build_graph

    session = await get_session(sender_id)
    session["messages"].append(HumanMessage(content=text))

    graph = build_graph()
    result = await graph.ainvoke(session)

    for msg in result.get("messages", []):
        if (
            hasattr(msg, "content")
            and msg.content
            and not isinstance(msg, HumanMessage)
        ):
            try:
                await instagram.send_message(sender_id, msg.content)
            except Exception:
                logger.exception("instagram.message.send_failed", sender_id=sender_id)

    await save_session(sender_id, result)


@app.post("/webhook/instagram")
async def receive_instagram_message(request: Request):
    raw_body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not instagram.verify_signature(raw_body, sig):
        logger.warning("instagram.webhook.invalid_signature")
        return Response(status_code=403, content="Invalid signature")

    payload = await request.json()
    logger.info("instagram.webhook.received")

    messages = await instagram.receive_message(payload)

    for sender_id, text in messages:
        logger.info("instagram.message.processing", sender_id=sender_id)
        try:
            await process_with_ai(sender_id, text)
        except Exception:
            logger.exception("ai.processing.failed", sender_id=sender_id)
            try:
                await instagram.send_message(
                    sender_id,
                    "Произошла техническая ошибка. Наши специалисты уже работают над этим. Попробуйте позже! 🛠️",
                )
            except Exception:
                logger.exception("instagram.message.send_failed", sender_id=sender_id)

    return {"status": "ok"}
