import re

TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("a an the and or of to in for on with is are be this that it as at by from your you we our".split())


def tokenize(t: str) -> list[str]:
    return [w for w in TOKEN.findall(t.lower()) if w not in STOP and len(w) > 1]
