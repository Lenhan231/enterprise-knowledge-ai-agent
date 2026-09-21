from typing import Literal

from pydantic import BaseModel


class IntentResult(BaseModel):
    intent: Literal[
        "knowledge",
        "analytics",
        "dashboard",
        "hybrid"
    ]

    needs_knowledge: bool
    needs_sql: bool

    output_mode: Literal[
        "answer",
        "dashboard",
    ]

    confidence: float