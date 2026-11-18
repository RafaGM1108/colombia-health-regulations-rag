# Input contract

The API and the chat UI accept two kinds of input. The boundary between them follows the [corpus policy](data.md): only official public regulations are in scope, and no patient-specific, person-specific, or private input may reach an external service.

| Operation | Input | Where it runs | External request |
|---|---|---|---|
| Cited answer | ID of a reviewed public question from the fixed set | Local retrieval, then the Anthropic API | Yes: only the reviewed question text and retrieved official passages |
| Passage search | Free-form query, 3–300 characters | Local embedding model and index | No |

## Why generation accepts only reviewed questions

Free-form screening cannot reliably detect personal details in Spanish text: names, case descriptions, and identifiers take too many forms. The interface therefore never sends user-written text to the external generation API. Each answerable request names one of the 26 reviewed public questions in `data/06_evaluation/questions.json`, and the service looks up its text; an unknown ID is rejected before any retrieval or API call.

## Search queries stay local

Search embeds the query with the pinned E5 model on the serving machine and ranks passages in the local Chroma index. The query is not stored, written to logs, or sent to another service. Request bodies are not part of the server's access log. Do not type patient or personal details anyway: the search box is for regulation topics only.

## API

`make api` serves the FastAPI application locally; interactive documentation is at `/docs`. It needs the verified local index (see the [data layers](data.md)), and `/answers` also needs `ANTHROPIC_API_KEY` in the local `.env`.

| Method and path | Body | Returns |
|---|---|---|
| `GET /health` | — | Service status and version |
| `GET /questions` | — | The reviewed public questions (`id`, `question`) |
| `POST /search` | `{"query": "..."}`, 3–300 characters | Up to five official passages with citation, text, and a link to the PDF page |
| `POST /answers` | `{"question_id": "q01"}` | Claims with exact quotations and citations, or a refusal with its reason |

Unknown fields are rejected, so free text cannot be passed to `/answers`. Errors: `404` for an unknown question ID, `422` for invalid input, `503` when the index or the API key is missing, and `502` when the generation service fails. Every search and answer response includes the informational-only disclaimer.

## Chat UI

`make app` opens the Streamlit interface in Spanish. It shows the informational-only disclaimer at the top and has two tabs:

- **Preguntas revisadas**: choose a reviewed public question and press *Responder*. Each claim appears with its exact quotation and a link to the official PDF page; a refusal shows its reason. The conversation lives only in the browser session and is not saved.
- **Buscar en la normativa**: type a regulation topic to list official passages with their citations and page links. The search runs locally and the text field warns against entering personal details.

It uses the same service and rules as the API, so it needs the same local index and, for answers, the same API key.

## Limits

- The answer set is fixed. New public questions require a reviewed change to the question set, not user input.
- Search results are official passages, not answers. They carry the resolution, article or annex location, official PDF link, and page, and they still require reading the cited source.
- Hosting this service on a shared server moves the local search to that server. The same no-storage and no-logging rules apply there.
- The output is informational only; it is not legal or medical advice.
