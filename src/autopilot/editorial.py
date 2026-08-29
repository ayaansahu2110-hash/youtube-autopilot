from __future__ import annotations

import re
from dataclasses import dataclass

from autopilot.models import ResearchPack, TopicCandidate


@dataclass(frozen=True)
class EditorialBrief:
    series: str
    promise: str
    required_beats: tuple[str, ...]

    def as_text(self) -> str:
        beats = "\n".join(f"- {item}" for item in self.required_beats)
        return (
            "BYTEVEXA EDITORIAL BRIEF\n"
            f"SERIES: {self.series}\n"
            f"VIEWER PROMISE: {self.promise}\n"
            "REQUIRED STORY BEATS:\n"
            f"{beats}\n"
            "Use the research below for factual claims. The brief itself is not evidence."
        )


class ByteVexaEditorialSystem:
    def enrich(self, candidate: TopicCandidate, research: ResearchPack) -> ResearchPack:
        brief = self.brief_for(candidate, research)
        notes = research.research_notes.strip()
        combined = brief.as_text() + ("\n\nRESEARCH EVIDENCE\n" + notes if notes else "")
        return research.model_copy(update={"research_notes": combined})

    def brief_for(self, candidate: TopicCandidate, research: ResearchPack) -> EditorialBrief:
        text = f"{candidate.title} {candidate.angle} {research.research_notes}".lower()
        series = self._series_for(text)
        practical = self._practical_hint(text)
        return EditorialBrief(
            series=series,
            promise=(
                "Explain one new AI development through a real task or everyday consequence. "
                f"When evidence allows, ground it in {practical}."
            ),
            required_beats=(
                "Open with the most useful or surprising consequence, not the announcement.",
                "Explain what changed in one plain-English sentence.",
                "Connect it to one realistic user and task.",
                "Show or illustrate an input -> action -> output flow.",
                "Include at least one concrete feature, workflow step, limitation, comparison, or availability condition supported by evidence.",
                "State the catch or who should care when relevant.",
                "End with a clear practical takeaway instead of generic filler.",
                "Avoid a sequence made mostly of landing pages or plain text cards.",
            ),
        )

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        score = 0.0
        high_value = {
            "launch": 5, "released": 5, "release": 5, "new": 3, "update": 4,
            "agent": 4, "browser": 5, "video": 4, "image": 4, "voice": 4,
            "search": 4, "code": 4, "coding": 4, "presentation": 5, "slides": 5,
            "study": 5, "research": 4, "document": 4, "pdf": 5, "meeting": 5,
            "email": 5, "phone": 4, "app": 4, "tool": 4,
        }
        for term, weight in high_value.items():
            if re.search(rf"\b{re.escape(term)}\b", text):
                score += weight
        score -= sum(4 for term in ("funding", "valuation", "lawsuit", "executive", "rumor") if term in text)
        return max(-12.0, min(18.0, score))

    @staticmethod
    def _series_for(text: str) -> str:
        if any(term in text for term in ("launch", "released", "release", "update", "announced", "new model")):
            return "What Changed?"
        if any(term in text for term in ("benchmark", "versus", " vs ", "compare", "comparison")):
            return "AI vs Real Task"
        if any(term in text for term in ("how to", "workflow", "feature", "tool", "app", "browser", "presentation", "slides")):
            return "30-Second Demo"
        if any(term in text for term in ("free", "pricing", "subscription")):
            return "Worth Trying?"
        return "AI News You Can Use"

    @staticmethod
    def _practical_hint(text: str) -> str:
        mappings = (
            (("student", "study", "research", "pdf", "notes"), "a student or research workflow"),
            (("slides", "presentation", "deck"), "making a presentation from a short prompt"),
            (("code", "coding", "developer"), "a small coding task with a visible result"),
            (("video", "image", "design"), "creating one piece of media from a concrete prompt"),
            (("email", "meeting", "office", "work"), "a normal work task someone repeats every week"),
            (("search", "browser", "web"), "finding and using information on the web"),
        )
        for keywords, description in mappings:
            if any(word in text for word in keywords):
                return description
        return "a normal task a student, creator, or knowledge worker already does"
