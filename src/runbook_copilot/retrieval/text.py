"""Tokenizer shared by indexing and querying. Kubernetes-aware: splits CamelCase terms
(CrashLoopBackOff -> crashloopbackoff + crash loop back off) so 'crash loop' queries still match."""
import re

STOPWORDS = frozenset("""
a an the and or but if then else of to in on at by for with from as is are was were be been being it its this that
these those i me my we our you your they their there here do does did doing done can could should would will just not
no yes so than too very how what why when where which who whom also into about over under again am have has had get
got any some all each every more most such only own same up down out off
""".split())

_WORD = re.compile(r"[A-Za-z0-9]+")
_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


_PROTECTED = {"kubernetes", "k8s", "aws", "status", "address", "access", "dns", "kubectl"}


def _norm(tok: str) -> str:
    """Very light plural stemming (pods -> pod). Protected words and -ss/-us/-is endings are left alone."""
    if tok in _PROTECTED or tok.endswith(("ss", "us", "is")):
        return tok
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    out: list[str] = []
    for w in _WORD.findall(text):
        parts = _CAMEL.findall(w)
        cands = [w] + (parts if len(parts) > 1 else [])
        for c in cands:
            t = _norm(c.lower())
            if len(t) < 2 and not t.isdigit():
                continue
            if not keep_stopwords and t in STOPWORDS:
                continue
            out.append(t)
    return out
