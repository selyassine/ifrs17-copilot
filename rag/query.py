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


def expand_glossary(query: str) -> str:
    q = fold(query)
    extra = [target for pattern, target in GLOSSARY.items() if re.search(pattern, q)]
    return query if not extra else f"{query} ({'; '.join(dict.fromkeys(extra))})"
