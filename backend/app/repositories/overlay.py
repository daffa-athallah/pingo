"""Read-only view of a repository for evaluations that must never change stored data.

Reads go to the wrapped repository. Loop writes the agents make during a run (for example a Critic-requested revision) stay in memory for
the rest of that run, so the trace is faithful, and are discarded afterwards. Evidence, entity, Check-in and context writes are refused.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace


class ReadOnlyOverlayRepository:
    def __init__(self, base):
        self._base = base
        self._loops: dict = {}
        self._links: list = []

    def __getattr__(self, name):  # reads and helpers
        return getattr(self._base, name)

    def unit_of_work(self):
        return nullcontext(self)

    def _overlay(self, loops):
        return [self._loops.get(loop.loop_id, loop) for loop in loops]

    def get_open_loop(self, loop_id):
        return self._loops.get(loop_id) or self._base.get_open_loop(loop_id)

    def get_active_open_loops(self, **kw):
        return self._overlay(self._base.get_active_open_loops(**kw))

    def get_candidate_open_loops(self, *a, **kw):
        return self._overlay(self._base.get_candidate_open_loops(*a, **kw))

    def get_loop_entities(self, loop_ids):
        return [*self._base.get_loop_entities(loop_ids), *[k for k in self._links if k.loop_id in set(loop_ids)]]

    def save_open_loop(self, loop):
        self._loops[loop.loop_id] = loop
        return loop

    def update_open_loop(self, loop_id, **changes):
        current = self.get_open_loop(loop_id)
        if current is None:
            raise KeyError(loop_id)
        self._loops[loop_id] = replace(current, **{k: v for k, v in changes.items() if v is not None})
        return self._loops[loop_id]

    def link_loop_entity(self, link):
        self._links.append(link)

    def _refuse(self, *a, **kw):
        raise PermissionError('This evaluation is read-only.')

    save_evidence = save_entity = save_check_in = save_context_event = _refuse
