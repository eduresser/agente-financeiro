import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

InputVerdict = Literal["ok", "suspect", "block"]

_FLAGS = re.IGNORECASE
_FILLER = r"(?:\w+\W+){0,3}"

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))
_HOMOGLYPHS = str.maketrans("аеорсхіуѕАЕОРСХ", "aeopcxiysAEOPCX")
_LEET = str.maketrans("013457@$", "oieastas")
_SPACED_LETTERS = re.compile(r"(?<!\w)(?:\w[\s.\-_*]){3,}\w(?!\w)")


def _unmask(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).translate(_HOMOGLYPHS)
    return _SPACED_LETTERS.sub(lambda m: re.sub(r"[\s.\-_*]", "", m.group()), folded)


def _variants(text: str) -> list[str]:
    unmasked = _unmask(text)
    return [text, unmasked, unmasked.translate(_LEET)]


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
        r"</?\s*(system|assistant|instructions?)\s*>|^\s*(system|assistant)\s*:", _FLAGS | re.M
    ),
    re.compile(
        r"\b(execute|executar|chame|chamar|invoque|invocar|call|invoke|run)\W+(?:\w+\W+){0,3}"
        r"(ferramenta|fun[cç][ãa]o|tool|function|comando|command)\b",
        _FLAGS,
    ),
    re.compile(
        r"\bdo anything now\b|\bunrestricted\b"
        r"|\b(responda|aja|fale|answer|act|behave|reply)\W+(?:\w+\W+){0,3}"
        r"(sem|without)\s+(nenhum[ao]?s?\s+|qualquer\s+|any\s+)?"
        r"(restri[cç](?:[õo]es|[ãa]o)|filtros?|regras?|restrictions?|filters?|rules?)\b",
        _FLAGS,
    ),
    re.compile(r"\bDAN\b"),
    re.compile(
        r"\bvoc[eê]\s+agora\s+[eé]\b|\ba partir de agora\s+voc[eê]\b|\byou are now\b"
        r"|\bfrom now on you\b|\bact as\b|\bfinja\s+(que|ser)\b|\bpretend\s+(to be|you)\b"
        r"|\bdeveloper mode\b|\bmodo desenvolvedor\b|\bjailbreak\b",
        _FLAGS,
    ),
]

_SUSPECT = [
    re.compile(
        rf"\b(desconsidere|ignore|ignora|esque[cç]a|forget|disregard)\W+{_FILLER}"
        r"(tudo|all|everything)\b",
        _FLAGS,
    ),
    re.compile(
        r"\bo que\s+(te|lhe|voc[eê])\s+(disseram|falaram|programaram|foi dito)\b"
        r"|\bwhat\s+(were|was)\s+you\s+(told|instructed)\b"
        r"|\b(repita|repeat)\W+(?:\w+\W+){0,3}(acima|above)\b",
        _FLAGS,
    ),
    re.compile(
        r"\b(sou|eu sou|i am|i'm)\W+(?:\w+\W+){0,2}(gerente|administrador|admin|desenvolvedor"
        r"|developer|dono do banco|funcion[aá]rio do banco|suporte t[eé]cnico)\b",
        _FLAGS,
    ),
    re.compile(
        r"\b(cliente anterior|outro cliente|outros clientes|another customer|other customers"
        r"|de outra pessoa)\b",
        _FLAGS,
    ),
    re.compile(r"\b(decodifique|decode|base64)\b|[A-Za-z0-9+/]{24,}={0,2}", _FLAGS),
    re.compile(
        r"\b(mude|altere|troque|change|switch)\W+(?:\w+\W+){0,2}"
        r"(comportamento|behaviou?r|personalidade|persona)\b"
        r"|\bmensagem\s+d[oa]\s+(desenvolvedor|sistema|administrador)\b"
        r"|\b(modo|mode)\s+(debug|admin|root|deus|god)\b",
        _FLAGS,
    ),
    re.compile(
        r"\b(roteiro|roleplay|role-play|hipot[eé]tic[oa]|imagine|fic[cç][ãa]o|story)\b"
        r"(?:\W+\w+){0,12}\W+(prompt|instru[cç][õo]es|regras|instructions|rules)\b",
        _FLAGS,
    ),
    re.compile(
        r"\b(suas|seu|sua|your)\s+(instru[cç][õo]es|regras|prompt|configura[cç][õo]es"
        r"|programa[cç][ãa]o|instructions|rules)\b",
        _FLAGS,
    ),
    re.compile(r"\b(ferramentas|tools|api key|chave de api)\b", _FLAGS),
]

_CPF = re.compile(r"(?<!\d)(?:\d[\s.\-/]{0,2}){10}\d(?!\d)")
_LINK = re.compile(r"https?://|www\.|!\[[^\]]*\]\(", _FLAGS)
_CEILING_CONTEXT = re.compile(r"m[aá]xim[oa]|teto|permitid[oa]|faixa", _FLAGS)
_CEILING_WINDOW = 120

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
    re.compile(
        r"\b(vale a pena|melhor op[cç][ãa]o|melhor escolha|compensa)\W+(?:\w+\W+){0,4}"
        r"(invest|aplic|cdb|tesouro|a[cç][õo]es|bitcoin|cripto|fundos?)",
        _FLAGS,
    ),
    re.compile(
        r"\b(cdb|tesouro direto|a[cç][õo]es|bitcoin|cripto\w*"
        r"|fundos? (imobili[aá]rios?|de investimento))"
        r"\W+(?:\w+\W+){0,6}(rende|rendem|rentabilidade|melhor|recomend)",
        _FLAGS,
    ),
    re.compile(
        r"\b(eu\s+)?(investiria|compraria|aplicaria|sugeriria|recomendaria)\b"
        r"|\bi would (invest|buy)\b",
        _FLAGS,
    ),
    re.compile(
        r"\b(praticamente|quase)\s+aprovad|\bpode\s+contar\s+com\s+a\s+aprova"
        r"|\b(ser[aá]|vai\s+ser|vamos)\s+(com certeza\s+)?aprovad"
        r"|\baprova[cç][ãa]o\s+(certa|assegurada)\b",
        _FLAGS,
    ),
]

_AGENT_MENTION = [
    re.compile(
        r"\b(agente|setor|departamento|especialista|assistente)\s+de\s+"
        r"(cr[eé]dito|c[aâ]mbio|triagem|entrevista)\b",
        _FLAGS,
    ),
    re.compile(
        r"\b(time|equipe|n[oó]|m[oó]dulo)\s+de\s+(cr[eé]dito|c[aâ]mbio|triagem|entrevista)\b",
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
    "You help a digital bank",
    "You are a",
    "Answer only with the topic",
]

_LEAK = re.compile(
    r"\b(minhas|my)\s+(instru[cç][õo]es|instructions)\b|\bfui\s+instru[ií]d[oa]\b"
    r"|\b(meu|my)\s+(prompt|system prompt)\b|\bprompt\s+(do\s+)?sistema\b"
    r"|\binstru[cç][õo]es\s+internas\b",
    _FLAGS,
)


def classify_input(text: str) -> InputVerdict:
    variants = _variants(text)
    if any(pattern.search(v) for pattern in _INJECTION for v in variants):
        return "block"
    if any(pattern.search(v) for pattern in _SUSPECT for v in variants[:2]):
        return "suspect"
    return "ok"


def foreign_cpf_present(text: str, own_cpf: str | None) -> bool:
    for match in _CPF.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if len(digits) == 11 and digits != own_cpf:
            return True
    return False


@dataclass(frozen=True)
class Protected:
    pattern: re.Pattern[str]
    user_may_supply: bool = True
    user_pattern: re.Pattern[str] | None = None


def protected_pattern_present(
    text: str, patterns: Iterable[Protected | re.Pattern[str]], user_text: str = ""
) -> bool:
    for item in patterns:
        protected = item if isinstance(item, Protected) else Protected(item)
        for match in protected.pattern.finditer(text):
            if protected.user_may_supply and (protected.user_pattern or protected.pattern).search(
                user_text
            ):
                continue
            if protected.user_may_supply and _CEILING_CONTEXT.search(
                text[max(0, match.start() - _CEILING_WINDOW) : match.start()]
            ):
                continue
            return True
    return False


def external_link_present(text: str) -> bool:
    return bool(_LINK.search(text))


def advice_or_promise_present(text: str) -> bool:
    return any(pattern.search(text) for pattern in _ADVICE)


def internal_leak_present(text: str, markers: Iterable[str] = INTERNAL_MARKERS) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers) or bool(_LEAK.search(text))


def agent_mention_present(text: str) -> bool:
    return any(pattern.search(text) for pattern in _AGENT_MENTION)
