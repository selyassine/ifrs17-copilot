"""Préparation de la requête avant la recherche.

``expand_glossary`` : les utilisateurs écrivent « CSM », « PAA », « onéreux » ou « bilan » alors
que le texte officiel dit « marge sur services contractuels », « méthode d'affectation des primes »,
« déficitaire », « état de la situation financière ». Le glossaire ajoute les termes officiels à
la requête : c'est la version déterministe et gratuite de la réécriture de requête par LLM (S3).

Le glossaire est un savoir du domaine IFRS 17, écrit avant d'analyser les échecs du jeu de
test, et ne doit pas être ajusté question par question (sinon l'évaluation est biaisée).
"""

from __future__ import annotations

import re

from rag.retrieve import fold

# terme utilisateur (sans accents, minuscules) → termes du texte officiel
GLOSSARY: dict[str, str] = {
    r"\bcsm\b": "marge sur services contractuels",
    r"\bcontractual service margin\b": "marge sur services contractuels",
    r"\bpaa\b": "méthode d'affectation des primes",
    r"\bpremium allocation\b": "méthode d'affectation des primes",
    r"\bvfa\b": "contrats d'assurance avec éléments de participation directe",
    r"\bvariable fee\b": "contrats d'assurance avec éléments de participation directe",
    r"\b(bba|gmm)\b": "modèle général évaluation flux de trésorerie d'exécution",
    r"\bra\b": "ajustement au titre du risque non financier",
    r"\brisk adjustment\b": "ajustement au titre du risque non financier",
    r"\blrc\b": "passif au titre de la couverture restante",
    r"\blic\b": "passif au titre des sinistres survenus",
    r"\bfcf\b": "flux de trésorerie d'exécution",
    r"\bbel\b|\bbest estimate\b|\bmeilleure estimation\b": "estimations des flux de trésorerie futurs actualisées",
    r"\bonereu(x|se|ses)\b": "déficitaire",
    r"\bonerous\b": "déficitaire",
    r"\bchiffre d.affaires\b": "produits des activités d'assurance",
    r"\bbilan\b": "état de la situation financière",
    r"\boci\b": "autres éléments du résultat global",
    r"\bcohortes? annuelles?\b": "contrats émis à plus d'un an d'intervalle groupe",
    r"\btraites? de reassurance\b": "contrats de réassurance détenus",
    r"\bsinistres?\b": "demandes d'indemnisation",
    r"\bunites? de couverture\b": "unités de couverture services prévus",
}


# Question sur la norme dans son ensemble (« définition d'IFRS 17 », « c'est quoi IFRS 17 ? ») :
# « IFRS 17 » figure dans presque tous les paragraphes, la recherche ne trouve donc rien de précis.
# Le paragraphe 1 (objet de la norme) y répond ; on ajoute ses termes officiels (D-039).
_GENERIC_WORDS = """
a au aux avec bref c ce cela ces cest d de des definir definis definissez definition donne donner donnez
du elle en est est-ce explique expliquer expliquez general generale globale il ifrs ifrs17 introduction
j je l la le les m me moi mots norme objectif objet presentation presente presenter presentez
pourquoi pouvez peux plait principe principes qu quoi que quel quelle qui resume resumer resumez s
sert servir simple simplement sont svp t te toi tu un une votre vous 17
"""
_GENERIC = set(_GENERIC_WORDS.split())
STANDARD_EXPANSION = ("objectif de la norme : principes de comptabilisation, d'évaluation et de "
                      "présentation des contrats d'assurance et informations à fournir")


def about_the_standard(query: str) -> bool:
    """Vrai si la question porte sur IFRS 17 en général, sans sujet précis."""
    q = fold(query)
    if not re.search(r"\bifrs ?17\b", q):
        return False
    words = re.findall(r"[a-z0-9]+", q)
    return bool(words) and all(w in _GENERIC for w in words)


def expand_glossary(query: str) -> str:
    q = fold(query)
    extra = [target for pattern, target in GLOSSARY.items() if re.search(pattern, q)]
    if about_the_standard(query):
        extra.append(STANDARD_EXPANSION)
    return query if not extra else f"{query} ({'; '.join(dict.fromkeys(extra))})"


# --------------------------------------------------------------------------- #
# Questions de définition (D-092) : « c quoi le LRC », « qu'est-ce que la CSM », « définir le LIC »
# --------------------------------------------------------------------------- #
_DEFINITION = re.compile(r"\b(?:c ?quoi|c'?est quoi|qu'?est[- ]ce (?:que|qu)|que (?:signifie|veut dire)|"
                         r"defini(?:r|tion|s|t)?|definissez|signification|sens de|kesako|ca veut dire)\b")
# notions sans définition à l'annexe A : paragraphes qui les présentent (savoir du domaine, pas réglé sur un jeu de test)
CONCEPT_ANCHORS: dict[str, list[str]] = {
    r"\bpaa\b|affectation des primes|premium allocation": ["53"],
    r"\bbel\b|best estimate|meilleure estimation": ["33"],
}


_ASK = {"comment", "calculer", "calcule", "calcul", "evaluer", "evalue", "mesurer", "mesure", "et", "ou", "on", "selon",
        "utilise", "utiliser", "signifie", "veut", "dire", "c", "cest", "quoi", "qu", "est", "ce", "un", "une", "le", "la"}
_DEF_STOP = {"de", "d", "des", "du", "au", "aux", "la", "le", "les", "l", "a", "en", "sur", "titre", "assurance", "avec"}


def _stem_words(text: str) -> set[str]:
    return {w[:-1] if len(w) > 3 and w.endswith(("s", "x")) else w for w in re.findall(r"[a-z0-9]+", fold(text))}


def definition_targets(query: str, definitions: list[str]) -> tuple[list[str], list[str]]:
    """Question de définition → (définitions de l'annexe A visées, paragraphes d'ancrage). Vide sinon.

    Une définition est visée quand tous ses mots (pluriels ramenés au singulier) figurent dans la question ou dans les
    termes officiels ajoutés par le glossaire (« LRC » → « passif au titre de la couverture restante »)."""
    q = fold(query)
    if not _DEFINITION.search(q):
        return [], []
    # sujet de la question : ses mots, sans les mots de la demande (« c quoi », « comment le calculer ») ; une
    # abréviation du glossaire est remplacée par les mots du terme officiel (« LRC » → « passif … restante »)
    subject = q
    official: list[str] = []
    for pattern, target in GLOSSARY.items():
        if re.search(pattern, subject):
            subject = re.sub(pattern, " ", subject)
            official.append(target)
    subject_words = (_stem_words(_DEFINITION.sub(" ", subject)) | _stem_words(" ".join(official))) - _GENERIC - _ASK - _DEF_STOP
    def same_subject(d: str) -> bool:      # mêmes mots significatifs des deux côtés (« contrat onéreux » ≠ « contrat »)
        w = _stem_words(d.removeprefix("def:")) - _DEF_STOP
        return bool(subject_words) and w <= subject_words and subject_words <= w
    defs = [d for d in definitions if same_subject(d)]
    anchors = [pid for pattern, ids in CONCEPT_ANCHORS.items() if re.search(pattern, q) for pid in ids]
    return defs, anchors
