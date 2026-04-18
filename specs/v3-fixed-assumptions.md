# Fixed Assumptions

- Backend stack: FastAPI + Pydantic + SQLAlchemy + PostgreSQL
- Frontend stack: Next.js + React + TypeScript + Tailwind
- Async jobs: Celery or equivalent queue abstraction
- Durable storage: Postgres for source of truth, vector store later or adapter-based now
- Artifacts: markdown first, export adapters later
- Auth: stubbed in MVP, interface-ready for expansion
- Memory model: semantic + episodic + importance weighting
- Deployment target: containerized local/dev first, cloud later
- Primary objective: implementation velocity with replaceable modules
