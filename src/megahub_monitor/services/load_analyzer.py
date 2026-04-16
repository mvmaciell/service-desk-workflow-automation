from __future__ import annotations

from collections import Counter

from ..domain.models import LoadEntry, Ticket


class LoadAnalyzer:
    def calculate(self, tickets: list[Ticket]) -> list[LoadEntry]:
        counts: Counter[str] = Counter()

        for ticket in tickets:
            consultant = ticket.consultant.strip()
            if not consultant or consultant == "-":
                continue
            counts[consultant] += 1

        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
        return [LoadEntry(consultant=name, open_tickets=count) for name, count in ordered]

