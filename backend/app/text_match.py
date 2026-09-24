"""
Shared lexical matching for short stored text (table labels, figure captions).

Naive substring matching fails in two ways that were both seen in practice:
stopwords match everything ("the" is inside "thermal", so every thermal spec
row matched any question containing "the"), and substrings cross word
boundaries ("art" matches "part"). So: whole-word tokens, stopwords removed.
"""
import re

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "onto", "its",
    "was", "are", "has", "have", "had", "can", "will", "would", "should", "does",
    "what", "whats", "which", "who", "why", "how", "when", "where", "any", "all",
    "show", "shows", "give", "please", "want", "need", "tell", "about", "over",
    "under", "between", "than", "then", "there", "here", "our", "your", "their",
    "get", "got", "use", "used", "using", "much", "many", "did", "value", "values",
})


def content_tokens(text: str, extra_stopwords: frozenset = frozenset()) -> set[str]:
    """Whole-word, lowercased, stopword-free tokens. Keeps part numbers ("pc-42")."""
    words = re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS and w not in extra_stopwords}
