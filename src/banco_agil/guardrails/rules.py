import re
from collections.abc import Iterable
from typing import Literal

InputVerdict = Literal["ok", "suspect", "block"]

_FLAGS = re.IGNORECASE
_FILLER = r"(?:\w+\W+){0,3}"

_INJECTION = [
    re.compile(
        rf"\b(ignore|ignora|desconsidere|esque[cç]a|disregard|forget)\W+{_FILLER}"
        r"(instru[cç][õo]es|regras|diretrizes|instructions|rules|guidelines|prompt)",
        _FLAGS,
    ),
    re.compile(
        r"\b(system|developer|hidden|initial)\s+prompt\b|\bprompt\s+(do\s+)?(sistema|inicial|interno)",
        _FLAGS,
    ),
    re.compile(
        rf"\b(mostre|revele|repita|exiba|diga|show|reveal|print|repeat)\W+{_FILLER}"
        r"(instru[cç][õo]es|prompt|instructions)",
        _FLAGS,
    ),
    re.compile(
        r"\b(estou|sou|fui|j[aá] fui|consider(e|ar)( que)?( eu)?( estou| sou| fui)?|consider me"
        r"|i am|i'm|i have been)\W+(?:\w+\W+){0,2}(autenticad[oa]|authenticated|verificad[oa])",
        _FLAGS,
    ),
    re.compile(
        r"\bvoc[eê]\s+agora\s+[eé]\b|\ba partir de agora\s+voc[eê]\b|\byou are now\b"
        r"|\bfrom now on you\b|\bact as\b|\bfinja\s+(que|ser)\b|\bpretend\s+(to be|you)\b"
        r"|\bdeveloper mode\b|\bmodo desenvolvedor\b|\bjailbreak\b",
        _FLAGS,
    ),
]

_SUSPECT = [
    re.compile(
        r"\b(suas|seu|sua|your)\s+(instru[cç][õo]es|regras|prompt|configura[cç][õo]es"
        r"|programa[cç][ãa]o|instructions|rules)\b",
        _FLAGS,
    ),
    re.compile(r"\b(ferramentas|tools|api key|chave de api)\b", _FLAGS),
]

_CPF = re.compile(r"(?<!\d)(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d)")

_ADVICE = [
    re.compile(
        r"\b(recomendo|sugiro|aconselho|i recommend|i suggest)\W+(?:\w+\W+){0,4}"
        r"(invest|compr(ar|e)\s+(a[cç][õo]es|bitcoin|cripto)|stocks|crypto)",
        _FLAGS,
    ),
    re.compile(r"\b(invista em|voc[eê] deveria investir|you should invest)\b", _FLAGS),
    re.compile(
        r"\b(garanto|garantimos|prometo|prometemos|com certeza|certamente|i guarantee"
        r"|guaranteed)\W+(?:\w+\W+){0,6}aprov",
        _FLAGS,
    ),
    re.compile(r"\baprova[cç][ãa]o garantida\b|\bguaranteed approval\b", _FLAGS),
]

_AGENT_MENTION = [
    re.compile(
        r"\b(agente|setor|departamento|especialista|assistente)\s+de\s+"
        r"(cr[eé]dito|c[aâ]mbio|triagem|entrevista)\b",
        _FLAGS,
    ),
    re.compile(
        r"\b(transferindo|transfiro|vou transferir|vou te transferir|encaminhando"
        r"|vou encaminhar)\W+(?:\w+\W+){0,3}(voc[eê]|voce|vc)\b",
        _FLAGS,
    ),
]

INTERNAL_MARKERS = [
    "get_credit_limit",
    "request_limit_increase",
    "accept_interview",
    "decline_interview",
    "next_pending_field",
    "record_answer",
    "finish_interview",
    "abandon_interview",
    "get_exchange_rate",
    "Never reveal internal names",
    "Always answer in Brazilian Portuguese",
    "You classify the latest customer message",
]


def classify_input(text: str) -> InputVerdict:
    if any(pattern.search(text) for pattern in _INJECTION):
        return "block"
    if any(pattern.search(text) for pattern in _SUSPECT):
        return "suspect"
    return "ok"


def foreign_cpf_present(text: str, own_cpf: str | None) -> bool:
    return any("".join(match.groups()) != own_cpf for match in _CPF.finditer(text))


def protected_pattern_present(text: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def advice_or_promise_present(text: str) -> bool:
    return any(pattern.search(text) for pattern in _ADVICE)


def internal_leak_present(text: str, markers: Iterable[str] = INTERNAL_MARKERS) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def agent_mention_present(text: str) -> bool:
    return any(pattern.search(text) for pattern in _AGENT_MENTION)
