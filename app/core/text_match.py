"""
Shared lexical matching helpers.

Both the figure matcher and the structured-fact lookup need the same thing:
decide whether a user's question genuinely overlaps a short piece of stored
text (a caption, a table label). Naive `token in text` substring matching
fails badly here in two specific ways, and both were observed in practice:

  - stopwords match everything ("the" is a substring of "thermal", so any
    question containing "the" matched every thermal spec row)
  - substrings cross word boundaries ("art" matches "part")

So: whole-word tokens, stopwords removed.
"""
import re

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "onto", "its",
    "was", "are", "has", "have", "had", "can", "will", "would", "should", "does",
    "what", "whats", "which", "who", "why", "how", "when", "where", "any", "all",
    "show", "shows", "give", "please", "want", "need", "tell", "about", "over",
    "under", "between", "than", "then", "there", "here", "our", "your", "their",
    "get", "got", "use", "used", "using", "much", "many", "does", "did",
}


def content_tokens(text: str, extra_stopwords: frozenset = frozenset()) -> set:
    """Whole-word, lowercased, stopword-free tokens. Keeps part numbers ("pc-42")."""
    words = re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS and w not in extra_stopwords}
