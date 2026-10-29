# AI use and development notes

I started with an existing agent model and architecture that I had built. For this assignment, I chose FastAPI, SQLite, uv, and Groq, and directed the implementation toward a simple chat interface with LangGraph conversation history. I also chose to add LangSmith tracing for debugging.

I used Codex as a coding assistant to help adapt that existing architecture to the sales dataset, draft implementation changes and test cases, and investigate errors. The architectural reference and requirements came from my existing work and the assignment. AI-generated changes were checked through automated tests and live Groq queries.

The application follows my existing approach to model and tool separation, SQL query execution, query validation, conversation history, and checkpointing. It uses sqlglot for SQL validation and LangGraph's AsyncSqliteSaver for persistence. Features unrelated to this dataset were left out to keep the application focused.

## Problems and debugging

- During testing, a “least revenue” question returned a highest-product answer. I identified this issue and asked for the implementation to follow my existing agent architecture. The fix replaced fixed analysis plans with a conversational model–tool loop and added checks for highest and lowest rankings.
- Ambiguous least/highest questions need a grouping. The system prompt asks for clarification without context and uses saved history for follow-ups. The SQL tools support both ascending and descending analysis rather than a fixed winner report.
- Financial data contains a return, zero quantity and a missing price. Explicit ingestion rules preserve auditability and avoid imputing unknown prices.
- SQL safety cannot rely on a model prompt. The guard validates the AST and scopes every source reference; SQLite adds read-only execution, table/function restrictions and query work limits.
- Interrupted turns may leave unanswered tool calls in saved state. The graph repairs these before starting another user turn, following the recovery approach in my existing agent model.
- Automated tests use a scripted model so graph/tool behavior is deterministic, including invalid tool calls and SQL retries. These tests verify orchestration, not live Groq comprehension.
- Live testing with Groq gpt-oss-20b exposed provider errors when forced to emit a final-answer tool. The fix lets the model use SQL/data-quality tools and return ordinary chat replies, with the backend attaching validated response structure and actual evidence. Live checks covered the highest-product question, lowest-product follow-up, and North-region follow-up.
- LangSmith tracing is configured per request, including thread metadata, graph/model/tool runs and shutdown flushing. It is enabled only with an explicit tracing flag and key. Traces contain prompts and query results; keys are never added to trace metadata.

## Another day of work

Evaluate a labeled live-model question set, especially ambiguous requests and carried filters; add context compaction, better provider-error diagnostics, and browser interaction tests. Add authentication and conversation ownership checks before any shared deployment. Confirm discount/status semantics with a real stakeholder and derive dimension/date metadata dynamically for other CSVs.

