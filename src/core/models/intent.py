from typing import Literal

from pydantic import BaseModel


class IntentResult(BaseModel):
    intent: Literal[
        "knowledge",
        "analytics",
        "dashboard",
        "hybrid",
        "report",
    ]

    needs_knowledge: bool
    needs_sql: bool
    reason: str = ""

    output_mode: Literal[
        "answer",
        "dashboard",
    ]

    confidence: float
    fallback: bool = False
