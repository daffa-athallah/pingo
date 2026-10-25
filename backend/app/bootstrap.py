"""Composition boundary: select storage and inject it into the unchanged agents."""
from contextlib import contextmanager, nullcontext
import os

from backend.app.repositories.memory import InMemoryLoopRepository


def sample_mode() -> bool:
    value = os.environ.get('SAMPLE_MODE', 'false').strip().lower()
    if value not in ('true', 'false'):
        raise ValueError('SAMPLE_MODE must be true or false.')
    return value == 'true'


@contextmanager
def open_repository():
    if sample_mode():
        # No Zetaris module import, JVM startup, credential check or network access.
        yield InMemoryLoopRepository()
        return
    from backend.app.adapters.zetaris import JdbcSettings, ZetarisJdbc
    from backend.app.repositories.zetaris import ZetarisRepository
    with ZetarisJdbc(JdbcSettings.from_env()) as connection:
        yield ZetarisRepository(connection)


def build_orchestrator(gateway, repository, verifier=None, **kwargs):
    from backend.app.agents.context import ContextAgent
    from backend.app.agents.critic import CriticAgent
    from backend.app.agents.evidence import EvidenceAgent
    from backend.app.agents.open_loop import OpenLoopAgent
    from backend.app.orchestration.recall import RecallOrchestrator

    class PersistenceBoundOpenLoopAgent(OpenLoopAgent):
        def apply(self, decision):
            scope = getattr(self.repository, 'unit_of_work', nullcontext)
            # Only persistence is scoped. The existing reasoning and branching stay intact.
            with scope():
                return super().apply(decision)

    new_loop_id = kwargs.pop('new_loop_id', None)
    now = kwargs.get('now')
    return RecallOrchestrator(EvidenceAgent(gateway), PersistenceBoundOpenLoopAgent(gateway, repository, now=now, new_id=new_loop_id),
                              ContextAgent(gateway, repository, now=now), CriticAgent(gateway, repository), repository,
                              verifier, **kwargs)
