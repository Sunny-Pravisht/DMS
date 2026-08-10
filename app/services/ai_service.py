from typing import Dict, Any, List, Optional
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from ..config import get_settings
from ..schemas import AIExtractedData
from ..models import DocType, Correspondent
from .doctype_manager import (
    DEFAULT_DOCUMENT_TYPES,
    FALLBACK_DOCUMENT_TYPE,
    add_document_type_if_not_exists,
)
from .ai_client_factory import AIClientFactory
from .embedding_service import EmbeddingService, EmbeddingError
from .sdk_compat import adapt_params, strip_reasoning_blocks

# One shared pool for the whole process. Previously each AIService created its
# own ThreadPoolExecutor and never shut it down, which leaked two threads per
# request because SearchService (and therefore AIService) is built per request.
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ai-request")

# Remembers request parameters a given (provider, model) has rejected, so we
# stop re-sending them after the first 400. Keyed by "provider::model".
_unsupported_params: Dict[str, set] = {}
_unsupported_lock = threading.Lock()

# Parameters we are willing to drop and retry without.
_OPTIONAL_PARAMS = (
    "reasoning_effort",
    "response_format",
    "temperature",
    "max_completion_tokens",
    "max_tokens",
)

# Reasoning models spend part of the completion budget on hidden reasoning
# tokens before emitting any visible content. Measured against Groq's
# openai/gpt-oss-120b: ~9 reasoning tokens at 'low' and ~38 at 'medium' for a
# trivial prompt, far more for real work. A budget below this floor returns an
# empty message with finish_reason='length', so enforce headroom.
MIN_REASONING_COMPLETION_TOKENS = 512


def _mark_unsupported(key: str, param: str):
    with _unsupported_lock:
        _unsupported_params.setdefault(key, set()).add(param)
    logger.warning(f"Disabling unsupported parameter '{param}' for {key}")


def _get_unsupported(key: str) -> set:
    with _unsupported_lock:
        return set(_unsupported_params.get(key, ()))


def reset_capability_cache():
    """Clear the negotiated-capability cache (used by tests and settings reload)."""
    with _unsupported_lock:
        _unsupported_params.clear()


class AIService:
    def __init__(self, db_session: Session = None, settings=None, client=None):
        self.settings = settings if settings is not None else get_settings(db_session)
        self.client = client if client is not None else AIClientFactory.create_client(db_session)
        self.db_session = db_session
        self._last_request_time = 0
        self._min_request_interval = 0.1  # Minimum 100ms between requests

        # Which Groq key is in hand, and how many there are to fall back to.
        # A client passed in explicitly (tests, the connection check) is left
        # alone: it was chosen deliberately and must not be swapped underneath
        # the caller.
        self._key_index = 0
        self._key_count = (
            0 if client is not None
            else len(AIClientFactory.groq_keys(db_session))
            if (self.settings.ai_provider or "").lower() == "groq"
            else 0
        )

        self.provider = (self.settings.ai_provider or "").lower()
        self.capabilities = AIClientFactory.get_capabilities(self.settings)

        self.chat_model = AIClientFactory.get_chat_model(self.settings)
        self.analysis_model = AIClientFactory.get_analysis_model(self.settings)
        self.vision_model = AIClientFactory.get_vision_model(self.settings)

        self.embeddings = EmbeddingService(self.settings, client=self.client)

        # Default document types that should always be available
        self.default_document_types = list(DEFAULT_DOCUMENT_TYPES)

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------
    def _capability_key(self, model: str) -> str:
        return f"{self.provider}::{model}"

    def _build_completion_params(
        self,
        model: str,
        messages: list,
        max_tokens: int = 1000,
        temperature: Optional[float] = None,
        reasoning: bool = False,
    ) -> dict:
        """Build completion parameters for the active provider/model."""
        params: Dict[str, Any] = {"model": model, "messages": messages}
        blocked = _get_unsupported(self._capability_key(model))

        # Reasoning tokens are billed against the completion budget, so a small
        # budget yields an empty response. Guarantee headroom.
        if self.capabilities.get("supports_reasoning_effort", False):
            max_tokens = max(max_tokens, MIN_REASONING_COMPLETION_TOKENS)

        # Token budget: providers disagree on the parameter name.
        token_param = self.capabilities.get("token_param", "max_tokens")
        if str(model).startswith("o1"):
            token_param = "max_completion_tokens"
        if token_param not in blocked:
            params[token_param] = max_tokens
        else:
            alternative = (
                "max_tokens" if token_param == "max_completion_tokens" else "max_completion_tokens"
            )
            if alternative not in blocked:
                params[alternative] = max_tokens

        # Temperature
        if (
            temperature is not None
            and self.capabilities.get("supports_temperature", True)
            and "temperature" not in blocked
            and not str(model).startswith("o1")
        ):
            params["temperature"] = temperature

        # Reasoning effort (gpt-oss on Groq, o-series elsewhere)
        effort = (getattr(self.settings, "reasoning_effort", "medium") or "medium").lower()
        if (
            reasoning
            and effort != "none"
            and self.capabilities.get("supports_reasoning_effort", False)
            and "reasoning_effort" not in blocked
        ):
            params["reasoning_effort"] = effort

        return params

    def _supports_json_schema(self, model: str) -> bool:
        if not self.capabilities.get("supports_json_schema", False):
            return False
        if "response_format" in _get_unsupported(self._capability_key(model)):
            return False
        if self.provider == "azure":
            api_version = getattr(self.settings, "azure_openai_api_version", "2024-06-01")
            return api_version >= "2024-08-01"
        return True

    # ------------------------------------------------------------------
    # Request execution
    # ------------------------------------------------------------------
    @staticmethod
    def _offending_param(error_message: str, params: dict) -> Optional[str]:
        """Guess which request parameter a 400 response is complaining about."""
        lowered = error_message.lower()
        for param in _OPTIONAL_PARAMS:
            if param in params and param in lowered:
                return param
        # Generic phrasing that does not name the field.
        if "response_format" in params and (
            "json_schema" in lowered or "schema" in lowered or "json" in lowered
        ):
            return "response_format"
        return None

    @staticmethod
    def _is_bad_request(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status == 400:
            return True
        text = str(exc).lower()
        return (
            "400" in text
            and ("unsupported" in text or "invalid" in text or "unrecognized" in text)
        ) or "unsupported_value" in text or "unknown_parameter" in text

    def _execute(self, params: dict):
        """Run one chat completion, dropping parameters the model rejects."""
        model = params.get("model", "")
        key = self._capability_key(model)
        attempt_params = dict(params)

        for _ in range(len(_OPTIONAL_PARAMS) + 1):
            try:
                return self.client.chat.completions.create(
                    **adapt_params(self.client, attempt_params)
                )
            except Exception as exc:
                if not self._is_bad_request(exc):
                    raise
                offender = self._offending_param(str(exc), attempt_params)
                if offender is None:
                    raise
                _mark_unsupported(key, offender)
                attempt_params.pop(offender, None)
                if offender == "response_format":
                    logger.info(
                        f"{model}: falling back to prompt-guided JSON (no structured outputs)"
                    )
        raise RuntimeError(f"Could not find a compatible parameter set for model '{model}'")

    def _make_ai_request_with_retry(self, request_func, max_retries=None):
        """Make an AI request with timeout and retry logic"""
        if max_retries is None:
            max_retries = self.settings.ai_max_retries

        # Rate limiting - ensure minimum interval between requests
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._min_request_interval:
            time.sleep(self._min_request_interval - time_since_last)

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                self._last_request_time = time.time()

                future = _EXECUTOR.submit(request_func)

                try:
                    response = future.result(timeout=self.settings.ai_request_timeout)
                    logger.debug(f"AI request succeeded on attempt {attempt + 1}")
                    return response

                except FutureTimeoutError:
                    logger.warning(
                        f"AI request timed out after {self.settings.ai_request_timeout}s "
                        f"(attempt {attempt + 1})"
                    )
                    future.cancel()
                    last_exception = TimeoutError(
                        f"AI request timed out after {self.settings.ai_request_timeout} seconds"
                    )

                except Exception as e:
                    logger.warning(f"AI request failed on attempt {attempt + 1}: {e}")
                    last_exception = e
                    # Authentication and permission errors will never succeed on retry.
                    if self._is_fatal(e):
                        break
                    # Out of quota on this account. Another account has its own
                    # allowance, so move to it and try again immediately.
                    if self._is_quota(e):
                        if self._switch_key():
                            continue
                        # Nowhere to fall back to. A per-minute limit clears on
                        # its own and is worth waiting out; a per-DAY cap will
                        # not clear before tomorrow, so backing off 1s, 2s, 4s
                        # only makes every upload take eight seconds longer to
                        # fail. Give up now and say so.
                        if self._is_daily_cap(e):
                            logger.error(
                                "Groq daily token allowance is exhausted and no second "
                                "key is configured. AI features stay unavailable until it "
                                "resets. Set GROQ_API_KEY_2 in .env to a key from another "
                                "account to keep working through this."
                            )
                            break

            except Exception as e:
                logger.warning(f"Failed to submit AI request on attempt {attempt + 1}: {e}")
                last_exception = e

            if attempt < max_retries:
                wait_time = min(2 ** attempt, 8)
                logger.info(f"Retrying AI request in {wait_time} seconds...")
                time.sleep(wait_time)

        error_msg = f"AI request failed after {max_retries + 1} attempts"
        if last_exception:
            error_msg += f": {last_exception}"

        logger.error(error_msg)
        raise Exception(error_msg) from last_exception

    @staticmethod
    def _is_quota(exc: Exception) -> bool:
        """
        Is this "you have used your allowance" rather than "something broke"?

        Worth telling apart, because the two want opposite responses: a broken
        request is worth retrying on the same key, and an exhausted allowance
        never is - a per-day cap resets tomorrow, not in eight seconds.
        """
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status == 429:
            return True
        text = str(exc).lower()
        return any(
            marker in text
            for marker in ("rate limit", "rate_limit", "quota", "too many requests",
                           "insufficient_quota", "tokens per day", "requests per day")
        )

    @staticmethod
    def _is_daily_cap(exc: Exception) -> bool:
        """
        Is this the DAILY allowance rather than the per-minute one?

        Groq enforces both and reports them the same way. The difference
        matters: a per-minute limit clears in under a minute and is worth
        waiting out, a per-day one is not going to clear this session.
        """
        text = str(exc).lower()
        return any(m in text for m in ("per day", "tpd", "rpd", "daily"))

    def _switch_key(self) -> bool:
        """
        Move to the next Groq account. False when there is nowhere left to go.

        The embedding service holds the same client, so it is rebuilt too -
        otherwise embeddings would carry on hammering the exhausted key.
        """
        if self._key_count < 2 or self._key_index + 1 >= self._key_count:
            return False

        self._key_index += 1
        try:
            self.client = AIClientFactory.create_client(self.db_session, self._key_index)
        except Exception as exc:
            logger.error(f"Could not switch to Groq key {self._key_index + 1}: {exc}")
            self._key_index -= 1
            return False

        try:
            self.embeddings = EmbeddingService(self.settings, client=self.client)
        except Exception as exc:                      # pragma: no cover
            logger.debug(f"Embedding client not rebuilt on key switch: {exc}")

        logger.warning(
            f"Groq key {self._key_index} is out of quota; "
            f"continuing on key {self._key_index + 1} of {self._key_count}"
        )
        return True

    @staticmethod
    def _is_fatal(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status in (401, 403, 404):
            return True
        text = str(exc).lower()
        return any(
            marker in text
            for marker in (
                "invalid api key",
                "invalid_api_key",
                "authentication",
                "does not exist",
                "model_not_found",
            )
        )

    def chat_completion(
        self,
        messages: list,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: Optional[float] = None,
        reasoning: bool = False,
        response_format: Optional[dict] = None,
    ):
        """Public helper used by extraction, RAG and connection tests."""
        target_model = model or self.chat_model
        budget = max_tokens

        for attempt in range(2):
            params = self._build_completion_params(
                model=target_model,
                messages=messages,
                max_tokens=budget,
                temperature=temperature,
                reasoning=reasoning,
            )
            if response_format is not None and self._supports_json_schema(target_model):
                params["response_format"] = response_format

            response = self._make_ai_request_with_retry(lambda: self._execute(params))

            if not self._is_starved_by_reasoning(response) or attempt == 1:
                return response

            # The whole budget went to reasoning tokens and no content came
            # back. Retry once with more room rather than returning "".
            budget = max(budget * 4, MIN_REASONING_COMPLETION_TOKENS * 4)
            logger.warning(
                f"{target_model}: response truncated before any content "
                f"(reasoning consumed the budget); retrying with {budget} tokens"
            )

        return response

    @staticmethod
    def _is_starved_by_reasoning(response) -> bool:
        """True when the model emitted no content because it ran out of budget."""
        try:
            choice = response.choices[0]
        except (AttributeError, IndexError, TypeError):
            return False

        content = getattr(getattr(choice, "message", None), "content", None)
        if content and content.strip():
            return False

        return getattr(choice, "finish_reason", None) == "length"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_available_document_types(self) -> List[str]:
        """Get all available document types from database plus defaults"""
        document_types = set(self.default_document_types)

        if self.db_session:
            try:
                db_types = self.db_session.query(DocType).all()
                for doc_type in db_types:
                    document_types.add(doc_type.name.lower())
            except Exception as e:
                logger.warning(f"Could not load document types from database: {e}")

        document_types.add(FALLBACK_DOCUMENT_TYPE)
        return sorted(document_types)

    def _get_existing_correspondents(self) -> List[str]:
        """Get existing correspondent names for AI guidance"""
        correspondents = []

        if self.db_session:
            try:
                db_correspondents = self.db_session.query(Correspondent).limit(50).all()
                correspondents = [c.name for c in db_correspondents]
            except Exception as e:
                logger.warning(f"Could not load correspondents from database: {e}")

        return correspondents

    @staticmethod
    def _extract_json(response_text: str) -> dict:
        """Parse a JSON object out of a model response, tolerating fences/prose."""
        if not response_text:
            raise ValueError("AI returned an empty response")

        # Hybrid reasoning models emit <think> blocks inline before the JSON.
        text = strip_reasoning_blocks(response_text).strip()

        # Strip markdown fences.
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Fall back to the outermost {...} block.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        raise ValueError("AI returned invalid JSON")

    def _validate_and_fix_title(
        self, title: str, document_type: str, sender: str, date: str
    ) -> str:
        """Validate and potentially fix the generated title to match naming convention"""
        # The document type part is matched language-neutrally (any unicode
        # letter) so legacy titles stay valid; new titles are English.
        expected_pattern = r"^\d{4}-\d{2}-\d{2}_[^\W\d_]+_[a-zA-Z0-9]+_\w+.*$"

        if title and re.match(expected_pattern, title):
            return title

        logger.warning(f"Title '{title}' doesn't match pattern, reconstructing...")

        date_part = date if date else datetime.now().strftime("%Y-%m-%d")
        clean_sender = "".join(
            word.capitalize() for word in re.findall(r"\w+", sender or "UnknownSender")
        ) or "UnknownSender"

        title_parts = (title or "").split("_")
        if len(title_parts) >= 4:
            description_parts = title_parts[3:]
        else:
            description_parts = ["Document", "Import", "System"]

        while len(description_parts) < 3:
            description_parts.append("Part")

        description = "_".join(description_parts[:3])
        reconstructed_title = f"{date_part}_{document_type}_{clean_sender}_{description}"
        logger.info(f"Reconstructed title: {reconstructed_title}")

        return reconstructed_title

    # ------------------------------------------------------------------
    # Metadata extraction
    # ------------------------------------------------------------------
    def extract_document_metadata(self, text: str, filename: str) -> AIExtractedData:
        """Extract structured metadata from document text using the configured LLM."""
        available_document_types = self._get_available_document_types()
        existing_correspondents = self._get_existing_correspondents()

        schema = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Document name following the convention: {YYYY-MM-DD}_{documenttype}_{SenderWithoutSpaces}_{ThreeWordDescription}, all in English. Example: 2025-06-01_invoice_MustermannGmbH_Building_Permit_Newbuild",
                },
                "document_type": {
                    "type": "string",
                    "enum": available_document_types,
                    "description": f"Type of the document, chosen from the available list: {', '.join(available_document_types)}. Use 'other' if nothing fits.",
                },
                "date": {
                    "type": ["string", "null"],
                    "description": "The relevant date in the document, formatted YYYY-MM-DD (prefer the issue date).",
                },
                "sender": {
                    "type": "string",
                    "description": "Sender or issuer of the document. Company name or person, without spaces, in CamelCase.",
                },
                "tax_relevant": {
                    "type": "boolean",
                    "description": "Is the document relevant for taxes? (true = yes, false = no)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 10,
                    "description": "Relevant English keywords describing the content. Minimum 2, maximum 10 tags.",
                },
                "summary": {
                    "type": "string",
                    "description": "A short English summary of the document, one to two sentences.",
                },
            },
            "required": [
                "title",
                "document_type",
                "date",
                "sender",
                "tax_relevant",
                "tags",
                "summary",
            ],
            "additionalProperties": False,
        }

        correspondent_hint = ""
        if existing_correspondents:
            joined = ", ".join(existing_correspondents[:100])
            suffix = "..." if len(existing_correspondents) > 100 else ""
            correspondent_hint = f"\n        - Existing senders for orientation: {joined}{suffix}"

        prompt = f"""
        Analyse the following document text and extract the metadata according to the schema.

        IMPORTANT NAMING CONVENTION for the title:
        Format: {{YYYY-MM-DD}}_{{documenttype}}_{{SenderWithoutSpaces}}_{{ThreeWordDescription}}

        Examples of good titles:
        - 2025-01-15_invoice_MustermannGmbH_Electricity_Bill_January
        - 2024-12-01_contract_CityOfBerlin_Apartment_Rental_Agreement
        - 2025-02-10_quote_AutohausMeier_Workshop_Service_Inspection

        Rules:
        - Date formatted YYYY-MM-DD (prefer the issue date)
        - Pick the document type from the available list: {', '.join(available_document_types)}
        - Sender without spaces in CamelCase (e.g. MaxMustermann, BerlinCity, ABCGmbH){correspondent_hint}
        - A 3-word description that describes the content precisely
        - Join all parts with underscores
        - Write every extracted value in English. The document itself may be in
          another language - translate the values you produce (title, description,
          tags, summary) into English. Keep proper nouns (company and person names)
          as they are spelled in the document.

        Original filename: {filename}

        Document text:
        {text[:self.settings.ai_text_limit]}
        """

        model_to_use = self.analysis_model
        use_schema = self._supports_json_schema(model_to_use)

        system_content = (
            "You are a precise document metadata extractor. You analyse documents in "
            "any language and extract structured metadata according to the given schema. "
            "Always produce the extracted values in English, and always follow the title "
            "naming convention exactly."
        )
        if not use_schema:
            # Without structured outputs the schema has to live in the prompt.
            system_content += (
                "\nRespond ONLY with a valid JSON object matching this JSON schema "
                f"(no explanations, no markdown):\n{json.dumps(schema, ensure_ascii=False)}"
            )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        response_format = None
        if use_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "document_metadata",
                    "strict": True,
                    "schema": schema,
                },
            }

        try:
            response = self.chat_completion(
                messages=messages,
                model=model_to_use,
                max_tokens=self.settings.ai_max_tokens_extraction,
                temperature=self.settings.ai_temperature_extraction,
                reasoning=True,
                response_format=response_format,
            )

            response_text = response.choices[0].message.content
            metadata = self._extract_json(response_text)

            validated_title = self._validate_and_fix_title(
                metadata.get("title", ""),
                metadata.get("document_type", FALLBACK_DOCUMENT_TYPE),
                metadata.get("sender", "UnknownSender"),
                metadata.get("date"),
            )

            doctype_name = (metadata.get("document_type") or FALLBACK_DOCUMENT_TYPE).lower()
            if self.db_session and doctype_name not in self.default_document_types:
                try:
                    add_document_type_if_not_exists(
                        self.db_session,
                        doctype_name,
                        f"Automatically added document type: {doctype_name}",
                    )
                except Exception as e:
                    logger.warning(f"Could not add new document type {doctype_name}: {e}")

            tags = metadata.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            return AIExtractedData(
                title=validated_title,
                summary=metadata.get("summary"),
                document_date=metadata.get("date"),
                correspondent_name=metadata.get("sender"),
                doctype_name=doctype_name,
                tag_names=[str(t) for t in tags],
                is_tax_relevant=bool(metadata.get("tax_relevant", False)),
            )

        except Exception as e:
            logger.error(f"Failed to extract metadata using AI: {e}")
            raise

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------
    def generate_embeddings(self, text: str) -> List[float]:
        """Generate an embedding vector using the configured embedding backend."""
        try:
            return self.embeddings.embed_query(text)
        except EmbeddingError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch variant used by the re-indexing paths."""
        return self.embeddings.embed_documents(texts)

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------
    def transcribe_image(self, image_path: Path) -> str:
        """Transcribe an image with the configured vision model."""
        from .vision_ocr import VisionOCR

        return VisionOCR(self.settings, client=self.client).transcribe_path(Path(image_path))

    # ------------------------------------------------------------------
    # RAG
    # ------------------------------------------------------------------
    def answer_question(
        self,
        question: str,
        context_documents: List[str],
        document_titles: List[str] = None,
        document_ids: List[str] = None,
    ) -> str:
        """Answer a question based on document context using RAG"""
        context_parts = []
        document_references = []

        for i, doc in enumerate(context_documents):
            doc_num = i + 1
            title = (
                document_titles[i]
                if document_titles and i < len(document_titles)
                else f"Document {doc_num}"
            )
            doc_id = document_ids[i] if document_ids and i < len(document_ids) else None

            doc_ref = f"[Doc{doc_num}: {title}]"
            if doc_id:
                document_references.append(f"Doc{doc_num} ({title}) - ID: {doc_id}")
            else:
                document_references.append(f"Doc{doc_num} ({title})")

            context_parts.append(f"{doc_ref}:\n{doc}")

        context = "\n\n".join(context_parts)
        references_list = "\n".join(document_references)

        prompt = f"""
        You are a helpful assistant that answers questions based on the provided document context.

        IMPORTANT INSTRUCTIONS:
        - Always use Markdown formatting in your response
        - ALWAYS cite your sources using the exact document references provided below
        - When referencing a document, use the format: [Doc1], [Doc2], etc.
        - Include relevant quotes with citation: "quoted text" ([Doc1])
        - Structure your answer with headers (##), bullet points, and formatting as appropriate
        - If information is not available in the documents, clearly state this
        - Always answer in English, even when the question or the documents are
          written in another language

        AVAILABLE DOCUMENT REFERENCES:
        {references_list}

        CONTEXT DOCUMENTS:
        {context[:self.settings.ai_context_limit]}

        QUESTION: {question}

        Please provide a comprehensive answer in Markdown format with proper source citations.
        """

        self._log_rag_prompt(question, prompt, document_titles, document_ids)

        try:
            model_to_use = self.chat_model
            system_content = (
                "You are a knowledgeable assistant that answers questions based only on "
                "the provided document context. Provide comprehensive and accurate answers."
            )

            if str(model_to_use).startswith("o1"):
                # o1 models do not accept a system role.
                messages = [{"role": "user", "content": f"{system_content}\n\n{prompt}"}]
            else:
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt},
                ]

            response = self.chat_completion(
                messages=messages,
                model=model_to_use,
                max_tokens=self.settings.ai_max_tokens_chat,
                temperature=self.settings.ai_temperature_chat,
                reasoning=True,
            )

            answer = strip_reasoning_blocks(
                response.choices[0].message.content or ""
            ).strip()
            if not answer:
                raise ValueError("Model returned an empty answer")

            logger.info(f"Generated RAG answer for question: {question[:50]}...")
            return answer

        except Exception as e:
            logger.error(f"Failed to generate RAG answer: {e}")
            raise

    def suggest_improvements(
        self, extracted_data: AIExtractedData, text: str
    ) -> Dict[str, Any]:
        """Suggest improvements or alternatives for extracted metadata"""
        prompt = f"""
        Review the following extracted metadata and suggest improvements or alternatives:

        Extracted data:
        - Title: {extracted_data.title}
        - Summary: {extracted_data.summary}
        - Date: {extracted_data.document_date}
        - Correspondent: {extracted_data.correspondent_name}
        - Document type: {extracted_data.doctype_name}
        - Tags: {', '.join(extracted_data.tag_names)}
        - Tax relevant: {extracted_data.is_tax_relevant}

        Document text (first 1000 chars): {text[:1000]}

        Return as JSON with structure:
        {{
            "alternative_titles": ["title1", "title2"],
            "additional_tags": ["tag1", "tag2"],
            "confidence_scores": {{
                "title": 0.9, "summary": 0.8, "date": 0.7,
                "correspondent": 0.9, "doctype": 0.95, "is_tax_relevant": 0.85
            }},
            "suggestions": ["suggestion1", "suggestion2"]
        }}
        """

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are a metadata quality expert. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]

            response = self.chat_completion(
                messages=messages,
                model=self.analysis_model,
                max_tokens=1024,
                temperature=self.settings.ai_temperature_extraction,
                response_format={"type": "json_object"},
            )

            return self._extract_json(response.choices[0].message.content)

        except Exception as e:
            logger.warning(f"Failed to generate suggestions: {e}")
            return {
                "alternative_titles": [],
                "additional_tags": [],
                "confidence_scores": {},
                "suggestions": [],
            }

    def _log_rag_prompt(
        self,
        question: str,
        prompt: str,
        document_titles: List[str] = None,
        document_ids: List[str] = None,
    ):
        """Log RAG prompts to file, keeping only the last 5"""
        try:
            log_dir = Path(self.settings.logs_folder)
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / "rag_prompts.json"

            if log_file.exists():
                with open(log_file, "r", encoding="utf-8") as f:
                    try:
                        prompts = json.load(f)
                    except json.JSONDecodeError:
                        prompts = []
            else:
                prompts = []

            prompts.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "question": question,
                    "prompt": prompt,
                    "document_titles": document_titles or [],
                    "document_ids": document_ids or [],
                    "prompt_length": len(prompt),
                }
            )
            if len(prompts) > 5:
                prompts = prompts[-5:]

            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(prompts, f, indent=2, ensure_ascii=False)

            logger.info(f"RAG prompt logged to {log_file} (Question: {question[:50]}...)")

        except Exception as e:
            logger.error(f"Failed to log RAG prompt: {e}")
            # Don't fail the main operation if logging fails
