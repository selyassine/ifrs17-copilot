"""Orchestrateur d'un dossier complet (D-036) : document → données → CSM → norme → note.

    extracteur ─► calculateur ─► chercheur RAG + vérificateur (questions fixes) ─► rédacteur
        │               │                       │                                   │
   ancrage des     moteur Python          citations vérifiées,                synthèse ancrée
    chiffres      (jamais le LLM)        juge, 1 correction max          (chiffres et paragraphes)

Chaque étape est journalisée (agent, statut, durée) : n8n affiche ce journal et décide de la
suite. Le dossier part en **validation humaine** dès qu'un contrôle n'est pas passé ; la note est
alors produite quand même, marquée « à valider », pour que l'humain ait tout sous les yeux.
"""

from __future__ import annotations

import dataclasses
import hashlib
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from agents import reference
from agents.pipeline import verified_answer
from agents.reference import BASE_QUESTIONS, ONEROUS_QUESTION  # noqa: F401 (réexportées)
from agents.schemas import CsmResult, PortfolioData, TriangleData, VerdictStatus
from agents.writer import NormPoint, Note, NoteContext, verdict_label, write_note
from core.config import Settings
from core.llm import LLMClient
from core.prompts import load_prompt
from core.version import VERSION
from engine.csm import compute_csm
from multimodal.documents import DocumentText, pdf_text
from multimodal.extract import ExtractionResult, extract_from_images, extract_from_text
from multimodal.spreadsheet import CSV_MIME, XLSX_MIME, SpreadsheetError, spreadsheet_text
from multimodal.vision import normalize_image, pdf_page_images


class UnreadableDocument(ValueError):
    """PDF ou image illisible (corrompu, chiffré, format inconnu)."""


@dataclass
class Step:
    agent: str
    status: str
    detail: str = ""
    ms: float = 0.0


@dataclass
class GroupOutcome:
    """Un groupe de contrats du dossier : données, calcul, note et points à valider (D-078)."""
    portfolio: PortfolioData
    extraction: ExtractionResult | None = None
    csm: CsmResult | None = None
    note: Note | None = None
    controls: list[str] = field(default_factory=list)


@dataclass
class CaseOutcome:
    case_id: str
    status: str                     # note_prete | validation_humaine | document_illisible
    steps: list[Step] = field(default_factory=list)
    extraction: ExtractionResult | None = None
    csm: CsmResult | None = None
    portfolio: PortfolioData | None = None      # données retenues (extraites ou validées)
    norm: list[NormPoint] = field(default_factory=list)
    note: Note | None = None
    controls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    groups: list[GroupOutcome] = field(default_factory=list)   # plusieurs groupes : un par groupe (D-078)
    kind: str = "lrc"               # lrc : état de portefeuille (CSM) ; lic : triangle de sinistres survenus (D-083)
    triangle: TriangleData | None = None
    triangle_extraction: object | None = None    # TriangleResult
    lic: object | None = None                    # engine.lic.LicResult


def extract_document(data: bytes, mime: str, settings: Settings, text_client: Callable[[], LLMClient],
                     vision_client: Callable[[], LLMClient], case_id: str = "",
                     target_group: str | None = None) -> ExtractionResult:
    """PDF à couche texte → mode texte (ou hybride selon EXTRACT_PDF_MODE) ; scan ou image → vision.
    ``target_group`` : lire ce groupe-là dans un document qui en contient plusieurs (D-078).
    Classeur Excel ou CSV : cellules converties en tableau, puis même lecture que la couche texte (D-079)."""
    if mime in (XLSX_MIME, CSV_MIME):
        try:
            sheet = spreadsheet_text(data, mime)
        except SpreadsheetError as exc:
            raise UnreadableDocument(str(exc)) from exc
        return extract_from_text(sheet, text_client(), case_id=case_id, target_group=target_group, mode="tableur")
    if mime == "application/pdf":
        try:
            doc = pdf_text(data)
        except Exception as exc:          # PDF corrompu ou chiffré
            raise UnreadableDocument(f"PDF illisible : {exc}"[:300]) from exc
        has_text = len(doc.table_numbers) + len(doc.text_numbers) >= 3
        if has_text and settings.extract_pdf_mode != "hybride":
            return extract_from_text(doc, text_client(), case_id=case_id, target_group=target_group)
        return extract_from_images(pdf_page_images(data, max_pages=2), vision_client(),
                                   doc=doc if has_text else None, case_id=case_id,
                                   double_read=settings.vision_double_read, target_group=target_group)
    try:
        image = normalize_image(data)
    except Exception as exc:
        raise UnreadableDocument(f"image illisible : {exc}"[:300]) from exc
    return extract_from_images([image], vision_client(), case_id=case_id,
                               double_read=settings.vision_double_read, target_group=target_group)


def text_document(data: bytes, mime: str) -> DocumentText | None:
    """Couche texte d'un PDF ou d'un classeur, sans appel au LLM ; None pour une image ou un scan."""
    if mime in (XLSX_MIME, CSV_MIME):
        try:
            return spreadsheet_text(data, mime)
        except SpreadsheetError as exc:
            raise UnreadableDocument(str(exc)) from exc
    if mime == "application/pdf":
        try:
            doc = pdf_text(data)
        except Exception as exc:          # PDF corrompu ou chiffré
            raise UnreadableDocument(f"PDF illisible : {exc}"[:300]) from exc
        return doc if len(doc.table_numbers) + len(doc.text_numbers) >= 3 else None
    return None


def _timed(steps: list[Step], agent: str, notify: Callable[[int, Step], None] | None = None):
    """Mesure une étape et prévient ``notify`` à son début et à sa fin (suivi en direct, SSE)."""
    class _T:
        def __enter__(self):
            self.t0 = time.perf_counter()
            self.step = Step(agent=agent, status="en cours")
            steps.append(self.step)
            self.index = len(steps) - 1
            if notify:
                notify(self.index, self.step)
            return self.step

        def __exit__(self, *exc):
            self.step.ms = round((time.perf_counter() - self.t0) * 1000, 1)
            if exc[0] is not None:
                self.step.status = "erreur"
            if notify:
                notify(self.index, self.step)
            return False
    return _T()


def _prompt_version(prompt_id: str, version: int | None = None) -> int | None:
    try:
        return load_prompt(prompt_id, version).version
    except (KeyError, ValueError):
        return None


def note_context(settings: Settings, case_id: str, data: bytes, mime: str, source_name: str,
                 extraction: ExtractionResult | None, portfolio: PortfolioData) -> NoteContext:
    """Origine de la note : document, lecture, versions des prompts et des modèles (traçabilité)."""
    prompts = {"write_note": _prompt_version("write_note"), "verify_answer": _prompt_version("verify_answer"),
               "rag_answer": _prompt_version("rag_answer", settings.rag_prompt_version)}
    if settings.rag_agentic:
        prompts |= {"agentic_plan": _prompt_version("agentic_plan"), "grade_passages": _prompt_version("grade_passages")}
    if extraction is not None:
        pid = "extract_portfolio_vision" if extraction.mode in ("vision", "hybride") else "extract_portfolio"
        prompts[pid] = _prompt_version(pid)
    from actuariat.registre import current as registry
    from actuariat.registre import ra_volatility

    cv, cv_source, _ = ra_volatility(portfolio.line_of_business, default_cv=settings.ra_cv)
    reg = registry()
    return NoteContext(
        ra_cv_source=cv_source, ra_target_level=float(reg["ajustement_risque"].get("niveau_cible") or 0) or None,
        registry_version=str(reg.get("version", "")),
        case_id=case_id, entity=settings.note_entity, app_version=VERSION,
        source_name=source_name or ("document transmis" if data else ""),
        source_sha256=hashlib.sha256(data).hexdigest() if data else "", source_mime=mime,
        extraction_mode=extraction.mode if extraction is not None else "",
        grounding=extraction.grounding if extraction is not None else "",
        validated_by_human=extraction is None and not data,
        field_confidence=dict(portfolio.field_confidence), ra_cv=cv,
        provenance=dict(extraction.provenance) if extraction is not None else {},
        reader_notes=list(extraction.warnings) if extraction is not None else [],
        prompt_versions={k: v for k, v in prompts.items() if v is not None},
        models={"grand (raisonnement)": settings.llm_model_large, "petit (évaluation)": settings.llm_model_small})


def _same_group(a: str, b: str) -> bool:
    norm = lambda s: "".join(ch for ch in str(s).upper() if ch.isalnum())     # noqa: E731
    return norm(a) == norm(b)


def _single_group_view(ext: ExtractionResult) -> ExtractionResult:
    """Lecture d'un document à plusieurs groupes, réduite au groupe qu'elle a saisi : l'alerte « plusieurs
    groupes » n'a plus lieu d'être, chaque groupe étant lu et calculé à part (D-078)."""
    issues = [i for i in ext.issues if not i.startswith("plusieurs groupes de contrats")]
    status = ext.status
    if ext.portfolio is not None and status == "a_verifier" and not issues and not ext.missing:
        status = "ok"
    return dataclasses.replace(ext, issues=issues, status=status)


def _extraction_controls(ext: ExtractionResult, prefix: str = "") -> list[str]:
    return ([f"{prefix}extraction : {i}" for i in ext.issues]
            + [f"{prefix}extraction : champ absent du document ({m})" for m in ext.missing])


def run_case(data: bytes, mime: str, settings: Settings, text_client: Callable[[], LLMClient],
             vision_client: Callable[[], LLMClient], retriever_loader: Callable | None,
             case_id: str, portfolio: PortfolioData | None = None,
             on_step: Callable[[int, Step], None] | None = None, source_name: str = "",
             human_changes: list[str] | None = None,
             other_portfolios: list[PortfolioData] | None = None,
             triangle: TriangleData | None = None, validated_by: str = "") -> CaseOutcome:
    """``portfolio`` fourni (données validées par un humain) : l'extraction est sautée ; ``other_portfolios`` :
    autres groupes du même document, repris tels quels (D-078). ``triangle`` fourni : dossier de sinistres
    survenus validé (D-083). Un document dont la couche texte est un triangle de sinistres survenus suit la
    branche LIC (lecture du triangle, Chain Ladder et Mack, note écrite par le code).
    ``on_step(index, étape)`` : appelé au début et à la fin de chaque étape (interface en direct)."""
    out = CaseOutcome(case_id=case_id, status="note_prete")

    def add(step: Step) -> None:
        out.steps.append(step)
        if on_step:
            on_step(len(out.steps) - 1, step)
    if triangle is not None:
        return run_lic_case(out, settings, text_client, case_id, data, mime, source_name, on_step, add,
                            triangle=triangle, human_changes=human_changes, validated_by=validated_by)
    if portfolio is None and data:
        from multimodal.triangle import looks_like_triangle

        doc = text_document(data, mime)
        if doc is not None and looks_like_triangle(doc):
            return run_lic_case(out, settings, text_client, case_id, data, mime, source_name, on_step, add, doc=doc)
    client = text_client()
    groups: list[GroupOutcome] = []

    # 1. Extracteur
    if portfolio is None:
        with _timed(out.steps, "extracteur", on_step) as st:
            ext = extract_document(data, mime, settings, text_client, vision_client, case_id)
            out.extraction = ext
            st.status = ext.status
            st.detail = f"mode {ext.mode}, ancrage {ext.grounding}" + (f", {len(ext.issues)} problème(s)" if ext.issues else "")
        if ext.portfolio is None:
            out.status = "document_illisible"
            out.controls = ext.issues or ["aucune donnée exploitable"]
            return out
        if settings.multi_group and len(ext.groups) > 1:
            # un document, plusieurs groupes : une lecture ciblée par groupe, puis une note par groupe (D-078)
            first = _single_group_view(ext)
            for g in ext.groups:
                if _same_group(g, ext.portfolio.group_id):
                    eg = first
                    add(Step(agent="extracteur", status=eg.status, detail=f"groupe {g} : lecture déjà faite"))
                else:
                    with _timed(out.steps, "extracteur", on_step) as st:
                        eg = extract_document(data, mime, settings, text_client, vision_client, case_id, target_group=g)
                        st.status = eg.status
                        st.detail = f"groupe {g} : mode {eg.mode}" + (f", {len(eg.issues)} problème(s)" if eg.issues else "")
                if eg.portfolio is None:
                    out.controls.append(f"groupe {g} : lecture impossible ({'; '.join(eg.issues)[:160]})")
                    continue
                if any(_same_group(x.portfolio.group_id, eg.portfolio.group_id) for x in groups):
                    out.controls.append(f"groupe {g} : même identifiant qu'un groupe déjà lu ({eg.portfolio.group_id})")
                    continue
                groups.append(GroupOutcome(portfolio=eg.portfolio, extraction=eg,
                                           controls=_extraction_controls(eg, f"groupe {eg.portfolio.group_id} : ")))
            missing = [g for g in ext.groups if not any(_same_group(g, x.portfolio.group_id) for x in groups)]
            if missing:
                out.controls.append(f"groupes annoncés mais non calculés : {', '.join(missing)}")
            if not groups:
                out.status = "document_illisible"
                out.controls = out.controls or ["aucune donnée exploitable"]
                return out
        else:
            groups.append(GroupOutcome(portfolio=ext.portfolio, extraction=ext, controls=_extraction_controls(ext)))
    else:
        add(Step(agent="extracteur", status="saute", detail="données fournies (validées)"))
        groups.append(GroupOutcome(portfolio=portfolio, extraction=None))
        for op in other_portfolios or []:
            groups.append(GroupOutcome(portfolio=op, extraction=None))

    # 2. Calculateur (Python, jamais le LLM)
    with _timed(out.steps, "calculateur", on_step) as st:
        for g in groups:
            g.csm = compute_csm(g.portfolio)
        st.status = "ok"
        st.detail = " ; ".join(f"{g.portfolio.group_id} {'déficitaire' if g.csm.onerous else 'bénéficiaire'}"
                               for g in groups) if len(groups) > 1 else (
            "groupe déficitaire" if groups[0].csm.onerous else "groupe bénéficiaire")

    # 3. Chercheur RAG + vérificateur, sur des questions fixes adaptées au cas (une fois pour le dossier)
    any_onerous = any(g.csm.onerous for g in groups)
    questions = BASE_QUESTIONS + ([ONEROUS_QUESTION] if any_onerous else [])
    norm_controls: list[str] = []
    if retriever_loader is None:
        out.warnings.append("norme non indexée : note sans fondements cités")
    else:
        refs = reference.load(settings.norm_reference_path) if settings.use_norm_reference else {}
        todo: list[tuple[int, str, Step]] = []
        points: dict[int, NormPoint] = {}
        for i, q in enumerate(questions):
            ref = reference.usable(refs.get(q))
            if ref is not None:          # réponse de référence déjà vérifiée : aucun appel LLM
                points[i] = NormPoint(question=q, answer=ref, verdict="ok")
                add(Step(agent="chercheur_rag", status="reference", detail=q[:80]))
            else:                        # étape ouverte tout de suite : l'interface voit les questions en cours
                st = Step(agent="chercheur_rag+verificateur", status="en cours", detail=q[:80])
                add(st)
                todo.append((len(out.steps) - 1, q, st))
        if todo:
            # Questions indépendantes (D-063) : traitées en parallèle (NORM_PARALLEL, 1 = l'une après
            # l'autre) ; résultats remis dans l'ordre des questions, la note est identique.
            retriever = retriever_loader()

            def answer(item: tuple[int, str, Step]):
                index, q, st = item
                t0 = time.perf_counter()
                try:
                    return verified_answer(q, settings, client, retriever, case_id=case_id)
                finally:
                    st.ms = round((time.perf_counter() - t0) * 1000, 1)

            workers = max(1, min(settings.norm_parallel, len(todo)))
            if workers == 1:
                results = [answer(item) for item in todo]
            else:
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="norme") as pool:
                    results = list(pool.map(answer, todo))
            for (index, q, st), res in zip(todo, results, strict=True):
                label = verdict_label(res.verdict)
                points[questions.index(q)] = NormPoint(question=q, answer=res.answer, verdict=label)
                st.status = "refus" if res.answer.refused else label
                if on_step:
                    on_step(index, st)
            for (_, q, _), res in zip(todo, results, strict=True):
                if res.verdict is not None and res.verdict.status != VerdictStatus.OK:
                    norm_controls.append(f"norme : réponse non validée par le vérificateur ({q[:60]}…)")
        out.norm = [points[i] for i in sorted(points)]

    # 4. Rédacteur : une note par groupe
    for g in groups:
        g_norm = [n for n in out.norm if g.csm.onerous or n.question != ONEROUS_QUESTION]
        g.controls = g.controls + norm_controls
        checks = ["Calcul effectué par le moteur Python (le LLM ne calcule jamais)"]
        if g.extraction is not None:
            checks.append(f"Chiffres extraits contrôlés contre le document ({g.extraction.grounding})")
        if g_norm:
            checks.append("Citations de la norme vérifiées par le code, réponses relues par le vérificateur")
        checks.append("Projection du passif rapprochée période par période, sensibilités recalculées par le moteur")
        context = note_context(settings, case_id, data, mime, source_name, g.extraction, g.portfolio)
        context.human_changes = list(human_changes or []) if g is groups[0] else []
        with _timed(out.steps, "redacteur", on_step) as st:
            g.note = write_note(g.portfolio, g.csm, g_norm, g.controls, checks + [
                "Résumé et commentaire : chaque nombre et chaque paragraphe cité vérifiés par le code"], client, case_id,
                context=context)
            st.status = "ok" if g.note.synthesis_source == "llm" else "repli"
            st.detail = ((f"{g.portfolio.group_id} : " if len(groups) > 1 else "")
                         + ("synthèse du LLM vérifiée" if st.status == "ok" else "synthèse écrite par le code"))
            out.warnings += g.note.warnings

    # le groupe présenté en premier (formulaire de validation) est le premier qui a un point à valider
    primary = next((g for g in groups if g.controls), groups[0])
    out.groups = [primary] + [g for g in groups if g is not primary]
    out.portfolio, out.csm = primary.portfolio, primary.csm
    if primary.extraction is not None:
        out.extraction = primary.extraction
    if len(groups) == 1:
        out.note = primary.note
        out.controls += primary.controls
    else:
        from agents.note_report import combine_notes

        out.controls += [c for g in out.groups for c in g.controls if c not in out.controls]
        md, page = combine_notes(case_id, [(g.portfolio, g.csm, g.note, g.controls) for g in out.groups])
        out.note = dataclasses.replace(primary.note, markdown=md, html=page)
    if out.controls:
        out.status = "validation_humaine"
    return out


def run_lic_case(out: CaseOutcome, settings: Settings, text_client: Callable[[], LLMClient], case_id: str,
                 data: bytes, mime: str, source_name: str, on_step, add, doc: DocumentText | None = None,
                 triangle: TriangleData | None = None, human_changes: list[str] | None = None,
                 validated_by: str = "") -> CaseOutcome:
    """Dossier de sinistres survenus (D-083) : triangle lu et vérifié → Chain Ladder, Mack, actualisation et RA
    par le moteur → note écrite par le code. Aucune question à la norme : les références sont fixes."""
    from actuariat.registre import current as registry_now
    from agents.lic_report import render_lic_note
    from engine.lic import TriangleError, compute_lic
    from multimodal.triangle import extract_triangle

    out.kind = "lic"
    tres = None
    if triangle is None:
        with _timed(out.steps, "extracteur", on_step) as st:
            tres = extract_triangle(doc, text_client(), case_id=case_id,
                                    mode="tableur" if mime in (XLSX_MIME, CSV_MIME) else "texte")
            out.triangle_extraction = tres
            st.status = tres.status
            st.detail = ("triangle de sinistres survenus" + (f", {tres.data.n_years} années" if tres.data else "")
                         + f", double lecture {tres.double_read}" + (f", {len(tres.issues)} problème(s)" if tres.issues else ""))
        if tres.data is None:
            out.status = "document_illisible"
            out.controls = tres.issues or ["aucune donnée exploitable"]
            return out
        triangle = tres.data
        out.controls += ([f"extraction : {i}" for i in tres.issues]
                         + [f"extraction : champ absent du document ({m})" for m in tres.missing])
        out.warnings += tres.warnings
    else:
        add(Step(agent="extracteur", status="saute", detail="triangle fourni (validé)"))
    out.triangle = triangle
    with _timed(out.steps, "calculateur", on_step) as st:
        level = triangle.confidence_level
        if level is None:
            level = float(registry_now()["ajustement_risque"].get("niveau_cible") or 0.75)
            out.warnings.append(f"niveau de confiance non indiqué dans le document : niveau cible du registre ({level:.0%})")
        try:
            lic = compute_lic(triangle.cumulative_triangle(), triangle.discount_rates, level,
                              cv=triangle.declared_cv,
                              cv_source="volatilité imposée par le document" if triangle.declared_cv else "",
                              tail=triangle.tail_factor, labels=triangle.origin_years, premiums=triangle.premiums)
        except TriangleError as exc:
            st.status = "erreur"
            st.detail = str(exc)
            out.status = "document_illisible"
            out.controls.append(f"calcul impossible : {exc}")
            return out
        out.lic = lic
        st.status = "ok"
        from agents.writer import fr
        st.detail = f"Chain Ladder et Mack : provision {fr(lic.reserve)}, LIC {fr(lic.lic)}"
    checks = ["Chaque montant du triangle retrouvé dans le document (contrôle d'ancrage)" if tres else
              "Triangle fourni par un valideur",
              "Calcul effectué par le moteur Python (Chain Ladder, Mack, actualisation, RA) : le LLM ne calcule jamais",
              "Méthode de Mack validée sur l'exemple publié (Mack 1993 : provision 18 680 856, erreur 2 447 095)"]
    if tres is not None and tres.double_read == "concordante":
        checks.insert(1, "Triangle relu par le code : lecture concordante cellule par cellule")
    with _timed(out.steps, "redacteur", on_step) as st:
        md, page = render_lic_note(triangle, lic, case_id, controls=out.controls, checks=checks,
                                   entity=settings.note_entity, source_name=source_name,
                                   source_sha256=hashlib.sha256(data).hexdigest() if data else "",
                                   double_read=tres.double_read if tres else "", warnings=out.warnings,
                                   human_changes=human_changes, validated_by=validated_by)
        out.note = Note(markdown=md, html=page, synthesis="", synthesis_source="code")
        st.status = "ok"
        st.detail = "note écrite par le code (aucun LLM)"
    if out.controls:
        out.status = "validation_humaine"
    return out
