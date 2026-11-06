from pydantic import BaseModel


class ExportRequest(BaseModel):
    report_type: str
    format: str
