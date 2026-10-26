"""Story (P8.4): scenario -> TA-style test story (inputs only, never expected results)."""

from __future__ import annotations

import json

from pydantic import BaseModel

from engine.model import TestCase
from llm.client import LLMClient

SYSTEM = """Write the test story for a DTA EEL test case in the style of the ITSG Pool-Testaufgaben
(German, month by month). Give only the facts an HR clerk enters: employee, sick notes with dates (electronic
or paper), employment end. Never state the expected messages or results. Write every date as DD.MM.YYYY."""


class Story(BaseModel):
    text: str


def story(client: LLMClient, tc: TestCase) -> str:
    f = lambda d: d.strftime("%d.%m.%Y")
    i = tc.inputs
    dates = [f(a.start) for a in i.priors] + [f(i.current.start)]
    user = json.dumps({"id": tc.id, "person": "Peter Mustermann", "inputs": i.model_dump(mode="json")})

    def validate(o: Story) -> str | None:
        missing = [d for d in dates if d not in o.text]
        return f"dates missing: {missing}" if missing else None

    return client.structured(SYSTEM, user, Story, validate=validate).text
