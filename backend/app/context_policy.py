"""Local privacy gate for context events, applied before anything reaches a reasoning model.

Calendar titles and place names can be private. This is a deliberately simple word list, not a classifier: it errs on the side of dropping an
event. The Critic's own rule (sensitive Evidence never surfaces) is separate. Extend the list; do not remove the gate.
"""
from __future__ import annotations

import re

SENSITIVE = re.compile(
    r'\b(doctor|dr\.?|clinic|hospital|therap\w*|psychiat\w*|psycholog\w*|counsel\w*|medical|medication|prescription|pregnan\w*|oncolog\w*|'
    r'surgery|dentist|bank|loan|debt|tax|password|passcode|otp|visa|immigration|divorce|lawyer|court|funeral|'
    r'dokter|rumah sakit|terapi|psikolog|psikiater|konseling|obat|pinjaman|pajak|sandi|pengacara|pengadilan|pemakaman)\b',
    re.IGNORECASE)


def sensitive_reason(*texts: str | None) -> str | None:
    for text in texts:
        if text and SENSITIVE.search(text):
            return 'Looks private (health, money, legal or similar); not sent to reasoning.'
    return None
