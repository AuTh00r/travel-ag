import os
import re
from difflib import SequenceMatcher

from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import settings
from src.exceptions import GoogleSheetsError
from src.models.request import BookingRequest

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_TOURS_RANGE = "Туры!A:I"
_REQUESTS_RANGE = "Заявки!A:K"


class GoogleSheetsService:
    def __init__(self) -> None:
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service

        creds_file = settings.google_sheets_credentials_file
        if not os.path.isfile(creds_file):
            raise GoogleSheetsError(
                f"Файл учетных данных Google Sheets не найден: {creds_file}"
            )

        try:
            creds = ServiceAccountCredentials.from_service_account_file(
                creds_file, scopes=_SCOPES
            )
            self._service = build("sheets", "v4", credentials=creds)
            return self._service
        except Exception as e:
            raise GoogleSheetsError(f"Ошибка аутентификации Google Sheets: {e}") from e

    async def search_tours(
        self,
        destination: str | None = None,
        tour_type: str | None = None,
        budget: str | None = None,
        dates: str | None = None,
        travelers: int | None = None,
    ) -> list[dict]:
        service = self._get_service()
        sheet_id = settings.google_tours_sheet_id

        if not sheet_id:
            raise GoogleSheetsError("GOOGLE_TOURS_SHEET_ID не задан")

        try:
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=_TOURS_RANGE)
                .execute()
            )
        except HttpError as e:
            raise GoogleSheetsError(f"Ошибка чтения Google Sheets: {e}") from e

        rows = result.get("values", [])
        if not rows or len(rows) < 2:
            return []

        header = rows[0]
        raw_tours = rows[1:]

        tours = []
        for raw in raw_tours:
            tour_dict = dict(zip(header, raw + [""] * (len(header) - len(raw))))
            tours.append(tour_dict)

        available = [t for t in tours if t.get("Доступно", "").strip().lower() == "да"]

        filters = _build_filters(destination, tour_type, budget, dates)
        scored: list[tuple[dict, float]] = []
        for tour in available:
            score = _match_score(tour, filters)
            if score > 0:
                scored.append((tour, score))

        scored.sort(key=lambda x: -x[1])

        return [t for t, _ in scored]

    async def create_request(
        self,
        name: str,
        phone: str,
        email: str,
        tour: str = "",
        destination: str = "",
        budget: str = "",
        travelers: int = 1,
    ) -> None:
        service = self._get_service()
        sheet_id = settings.google_requests_sheet_id

        if not sheet_id:
            raise GoogleSheetsError("GOOGLE_REQUESTS_SHEET_ID не задан")

        req = BookingRequest(
            name=name,
            phone=phone,
            email=email,
            selected_tour=tour,
            destination=destination,
            budget=budget,
            travelers=travelers,
        )

        row = [
            req.created_at.strftime("%d.%m.%Y %H:%M"),
            req.name,
            req.phone,
            req.email,
            req.destination,
            req.budget,
            str(req.travelers),
            req.selected_tour,
            req.status,
            req.source,
            req.tag,
        ]

        try:
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=_REQUESTS_RANGE,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            ).execute()
        except HttpError as e:
            raise GoogleSheetsError(f"Ошибка записи в Google Sheets: {e}") from e

    async def update_request_status(
        self,
        name: str,
        phone: str,
        new_status: str,
    ) -> bool:
        valid_statuses = {"Новая", "В обработке", "Подтверждена", "Оплачена"}
        if new_status not in valid_statuses:
            raise GoogleSheetsError(
                f"Неверный статус: {new_status}. Допустимые: {', '.join(sorted(valid_statuses))}"
            )

        service = self._get_service()
        sheet_id = settings.google_requests_sheet_id

        if not sheet_id:
            raise GoogleSheetsError("GOOGLE_REQUESTS_SHEET_ID не задан")

        try:
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=_REQUESTS_RANGE)
                .execute()
            )
        except HttpError as e:
            raise GoogleSheetsError(f"Ошибка чтения Google Sheets: {e}") from e

        rows = result.get("values", [])
        if not rows:
            return False

        header = rows[0]
        name_col = header.index("Имя") if "Имя" in header else 1
        phone_col = header.index("Телефон") if "Телефон" in header else 2
        status_col = header.index("Статус") if "Статус" in header else 8

        for i, row in enumerate(rows[1:], start=2):
            row_name = row[name_col] if len(row) > name_col else ""
            row_phone = row[phone_col] if len(row) > phone_col else ""
            if row_name == name and row_phone == phone:
                range_to_update = f"Заявки!{chr(65 + status_col)}{i}"
                try:
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=range_to_update,
                        valueInputOption="USER_ENTERED",
                        body={"values": [[new_status]]},
                    ).execute()
                    return True
                except HttpError as e:
                    raise GoogleSheetsError(f"Ошибка обновления статуса: {e}") from e

        return False


def _build_filters(
    destination: str | None,
    tour_type: str | None,
    budget: str | None,
    dates: str | None,
) -> dict:
    filters: dict = {}

    if destination:
        filters["destination"] = _normalize(destination)

    if tour_type:
        filters["tour_type"] = _normalize(tour_type)

    if budget:
        budget_str = str(budget)
        nums = re.findall(r"\d+", budget_str.replace(",", "").replace(" ", ""))
        budget_values = [int(n) for n in nums] if nums else None
        filters["budget_values"] = budget_values
        filters["budget_direction"] = _detect_budget_direction(budget)

    if dates:
        filters["dates"] = _normalize(dates)
        filters["date_months"] = _extract_months(dates)

    return filters


def _detect_budget_direction(budget_str: str) -> str:
    budget_lower = str(budget_str).lower()
    if any(w in budget_lower for w in ["до", "не больше", "макс"]):
        return "max"
    if any(w in budget_lower for w in ["от", "не меньше", "мин"]):
        return "min"
    return "exact"


def _extract_months(text: str) -> list[str]:
    months = [
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
        "янв",
        "фев",
        "мар",
        "апр",
        "май",
        "июн",
        "июл",
        "авг",
        "сен",
        "окт",
        "ноя",
        "дек",
    ]
    found = []
    text_lower = text.lower()
    for m in months:
        if m in text_lower:
            found.append(m)
    return found


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _fuzzy_match(a: str, b: str, threshold: float = 0.35) -> bool:
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    similarity = SequenceMatcher(None, a, b).ratio()
    return similarity >= threshold


def _parse_price(price_str: str) -> list[int]:
    nums = re.findall(r"\d+", price_str.replace(" ", "").replace(",", ""))
    return [int(n) for n in nums] if nums else []


def _match_score(tour: dict, filters: dict) -> float:
    score = 1.0

    tour_dest = _normalize(tour.get("Направление", ""))
    tour_type_val = _normalize(tour.get("Тип", ""))
    tour_keywords = _normalize(tour.get("Ключевые слова", ""))
    tour_dates = _normalize(tour.get("Даты", ""))
    tour_price_str = tour.get("Цена", "")

    if "destination" in filters:
        dest_filter = filters["destination"]
        if not _fuzzy_match(dest_filter, tour_dest):
            if not _fuzzy_match(dest_filter, tour_keywords):
                return 0.0
            else:
                score += 0.5
        else:
            score += 1.0

    if "tour_type" in filters:
        type_filter = filters["tour_type"]
        if not _fuzzy_match(type_filter, tour_type_val):
            if not _fuzzy_match(type_filter, tour_keywords):
                return 0.0
            else:
                score += 0.3
        else:
            score += 1.0

    if "budget_values" in filters and filters["budget_values"]:
        budget_vals = filters["budget_values"]
        direction = filters.get("budget_direction", "exact")
        price_nums = _parse_price(tour_price_str)

        if price_nums:
            tour_price = max(price_nums)
            client_budget = min(budget_vals) if direction == "max" else max(budget_vals)

            if direction == "max":
                if tour_price <= client_budget:
                    score += 1.0
                else:
                    score -= 0.5
            elif direction == "min":
                if tour_price >= client_budget:
                    score += 1.0
                else:
                    return 0.0
            else:
                if abs(tour_price - client_budget) <= client_budget * 0.3:
                    score += 1.0 - abs(tour_price - client_budget) / (client_budget * 2)
                else:
                    score -= 0.5

    if "dates" in filters:
        date_filter = filters["dates"]
        if _fuzzy_match(date_filter, tour_dates):
            score += 1.0
        elif filters.get("date_months"):
            for month in filters["date_months"]:
                if month in tour_dates:
                    score += 0.7
                    break

    return score
