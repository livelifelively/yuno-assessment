"""Central registry of SQLModel table classes.

Imported by Alembic env.py and tests/conftest.py to ensure SQLModel.metadata
is populated before metadata.create_all or migration autogenerate.

Add a noqa-imported reference here whenever a new SQLModel `table=True` class
is defined in a module.
"""

from app.agents.persistence.row import AgentRow  # noqa: F401
from app.runs.persistence.row import RunEventRow, RunRow  # noqa: F401
