from loom.repositories.analysis_repository import AnalysisRepository


class HistoryController:
    """Handles GET /history and GET /history/{analysis_id}."""

    def __init__(self, analysis_repository: AnalysisRepository):
        self.analysis_repository = analysis_repository

    async def history(self) -> list[dict]:
        return self.analysis_repository.list_analyses()

    async def history_detail(self, record: dict) -> dict:
        for item in record["items"]:
            item["actionable"] = bool(item["actionable"])
        return record
