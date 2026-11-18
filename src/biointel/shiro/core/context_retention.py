"""
Shiro AI — Multi-Turn Conversation Context Engine
Maintains conversation state and resolves contextual follow-up queries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass
class ConversationTurn:
    user_query: str
    assistant_response: str
    key_entities: tuple[str, ...]


class ShiroContextEngine:
    """Manages multi-turn conversation memory and context resolution."""

    def __init__(self, max_history: int = 6) -> None:
        self.max_history = max_history
        self.history: list[ConversationTurn] = []

    def add_turn(self, query: str, response: str, entities: Sequence[str] = ()) -> None:
        self.history.append(ConversationTurn(query, response, tuple(entities)))
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def resolve_contextual_query(self, query: str) -> str:
        """Resolves pronouns like 'it', 'this gene', 'that result' using conversation history."""
        clean = query.strip()
        pronouns = {"it", "its", "this", "that", "this gene", "that report", "the variant", "the sample"}
        
        words = clean.casefold().split()
        needs_context = any(p in words or clean.casefold().startswith(p) for p in pronouns) or len(words) <= 3

        if needs_context and self.history:
            last_turn = self.history[-1]
            if last_turn.key_entities:
                main_entity = last_turn.key_entities[0]
                return f"{clean} (Context: {main_entity})"
            else:
                last_words = [w for w in last_turn.user_query.split() if w.isupper() or len(w) > 4]
                if last_words:
                    return f"{clean} (Context: {last_words[0]})"

        return clean

    def get_summary(self) -> str:
        """Generates a brief multi-turn history summary for LLM context injection."""
        if not self.history:
            return ""
        turns = [f"User: {t.user_query}\nShiro: {t.assistant_response[:150]}..." for t in self.history[-3:]]
        return "\n---\n".join(turns)
