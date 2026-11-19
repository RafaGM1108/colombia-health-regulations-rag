"""Streamlit chat for reviewed public questions and local passage search. Run with ``make app``.

Input contract (docs/interface.md): answers only for reviewed public questions; free-form text
only for local search. Nothing typed here is stored, logged, or sent to an external API.
"""

from pathlib import Path

import streamlit as st
from anthropic import APIError

from colombia_health_rag.serving.generation import Answer, RefusalReason
from colombia_health_rag.serving.service import (
    MAX_QUERY_CHARS,
    GenerationUnavailableError,
    InvalidQueryError,
    RegulationService,
)

DISCLAIMER = (
    "Solo informativo; no es asesoría legal ni médica. Las respuestas citan el texto original "
    "de normas oficiales que pueden haber sido modificadas: confirme en el documento citado."
)
REFUSAL_REASONS: dict[RefusalReason, str] = {
    "no_evidence": "No se encontraron pasajes oficiales para esta pregunta.",
    "abstained": "Los pasajes recuperados no respaldan una respuesta.",
    "unverified_citation": "La respuesta propuesta no pudo verificarse contra el texto oficial.",
    "invalid_output": "No fue posible generar una respuesta verificable.",
    "model_refusal": "El modelo no respondió esta solicitud.",
}


@st.cache_resource
def get_service() -> RegulationService:
    """Create one service per server process; the index loads on first use."""
    return RegulationService(Path.cwd())


def render_answer(answer: Answer) -> None:
    """Show each claim with its exact quotation and a link to the official PDF page."""
    if answer.refused:
        st.warning(answer.text)
        if answer.refusal_reason:
            st.caption(REFUSAL_REASONS[answer.refusal_reason])
        return
    for claim in answer.claims:
        citation = claim.citation
        st.markdown(claim.text)
        st.markdown(f"> {claim.quote}")
        st.markdown(
            f"Fuente: [{citation.label}]({citation.source_url}#page={citation.page_start}) "
            f"· {citation.source_title}, versión {citation.version}"
        )


def questions_tab(service: RegulationService) -> None:
    """Answer one reviewed public question at a time; the chat lives only in this session."""
    questions = {item.id: item.question for item in service.public_questions()}
    history: list[tuple[str, Answer]] = st.session_state.setdefault("history", [])
    for question_text, answer in history:
        with st.chat_message("user"):
            st.markdown(question_text)
        with st.chat_message("assistant"):
            render_answer(answer)
    question_id = st.selectbox(
        "Pregunta pública revisada",
        options=list(questions),
        format_func=lambda key: questions[key],
    )
    if st.button("Responder", type="primary") and question_id:
        try:
            question, answer = service.answer(question_id)
        except GenerationUnavailableError:
            st.error("La generación de respuestas no está configurada (falta ANTHROPIC_API_KEY).")
            return
        except FileNotFoundError:
            st.error("El índice local no está construido. Ejecute make embeddings y make index.")
            return
        except APIError:
            st.error("El servicio de generación falló; intente de nuevo.")
            return
        history.append((question.question, answer))
        st.rerun()


def search_tab(service: RegulationService) -> None:
    """Show official passages for a regulation topic; the query is searched locally."""
    query = st.text_input(
        "Tema de la normativa",
        max_chars=MAX_QUERY_CHARS,
        help="No escriba datos de pacientes ni datos personales.",
    )
    if not query:
        return
    try:
        hits = service.search(query)
    except InvalidQueryError as error:
        st.error(str(error))
        return
    except FileNotFoundError:
        st.error("El índice local no está construido. Ejecute make embeddings y make index.")
        return
    for hit in hits:
        url, page = hit.metadata["source_url"], hit.metadata["page_start"]
        st.markdown(f"**[{hit.metadata['citation']}]({url}#page={page})**")
        st.caption(hit.text[:600] + ("…" if len(hit.text) > 600 else ""))


def main() -> None:
    """Lay out the disclaimer, the reviewed-question chat, and local search."""
    st.set_page_config(page_title="Colombian Health Regulations RAG")
    st.title("Normativa de salud de Colombia")
    st.info(DISCLAIMER)
    service = get_service()
    answers, search = st.tabs(["Preguntas revisadas", "Buscar en la normativa"])
    with answers:
        st.caption(
            "Las respuestas se generan solo para preguntas públicas revisadas, con citas "
            "verificadas contra el texto oficial."
        )
        questions_tab(service)
    with search:
        st.caption("La búsqueda es local: devuelve pasajes oficiales, no respuestas.")
        search_tab(service)


main()
