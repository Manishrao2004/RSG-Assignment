"""Optional live Groq smoke test. Uses a separate temporary checkpoint database."""

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def main():
    settings = Settings()
    if not settings.groq_api_key:
        print("SKIPPED: GROQ_API_KEY is not configured.")
        return
    with TemporaryDirectory(prefix="rsg-live-", dir=settings.db_path.parent) as temp:
        config = settings.model_copy(update={"db_path": Path(temp) / "sales.sqlite3"})
        with TestClient(create_app(config)) as client:
            thread = None
            for question, expected_product, expected_revenue in [
                ("Which product generated the highest revenue?", "Monitor", 473000),
                ("And the least?", "Laptop Stand", 96000),
                ("Only in North?", "USB-C Hub", 18000),
            ]:
                response = client.post("/api/chat", json={"question": question, "thread_id": thread})
                for _ in range(2):
                    if response.status_code != 429:
                        break
                    print("Groq rate limit: waiting 30 seconds.", flush=True)
                    time.sleep(30)
                    response = client.post("/api/chat", json={"question": question, "thread_id": thread})
                response.raise_for_status()
                reply = response.json()
                assert reply["type"] == "answer", reply["message"]
                values = [
                    value for item in reply["evidence"] for row in item["rows"] for value in row.values()
                ]
                assert expected_product in values and expected_revenue in values, reply
                thread = reply["thread_id"]
                print(
                    json.dumps(
                        {
                            "question": question,
                            "type": reply["type"],
                            "answer": reply["message"],
                            "rows": [item["rows"] for item in reply["evidence"]],
                        },
                        ensure_ascii=True,
                    ),
                    flush=True,
                )
                time.sleep(15)
            ambiguous = client.post("/api/chat", json={"question": "which is the least revenue"})
            ambiguous.raise_for_status()
            assert ambiguous.json()["type"] == "clarification", ambiguous.json()
            history = client.get(f"/api/conversations/{thread}").json()["messages"]
            assert len([message for message in history if message["role"] == "assistant"]) == 3
            print(
                json.dumps({"ambiguous": ambiguous.json()["message"], "type": ambiguous.json()["type"]}),
                flush=True,
            )


if __name__ == "__main__":
    main()
