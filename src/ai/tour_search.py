from structlog import get_logger

from src.ai.states import DialogState
from src.exceptions import GoogleSheetsError
from src.services.google_sheets import GoogleSheetsService

logger = get_logger()


async def search_tours(state: DialogState) -> dict:
    params = state.get("tour_params", {})
    sheets = GoogleSheetsService()

    try:
        tours = await sheets.search_tours(
            destination=params.get("destination"),
            tour_type=params.get("tour_type"),
            budget=params.get("budget"),
            dates=params.get("dates"),
            travelers=params.get("travelers"),
        )
    except GoogleSheetsError as e:
        logger.error("tour_search.failed", error=str(e))
        return {
            "found_tours": [],
            "needs_escalation": True,
            "escalation_reason": f"Ошибка поиска туров: {e}",
        }

    if not tours:
        logger.info("tour_search.no_results", params=params)

    logger.info("tour_search.found", count=len(tours))
    return {"found_tours": tours}
