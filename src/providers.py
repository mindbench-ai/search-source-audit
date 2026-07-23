# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Provider adapters and the registry that maps config entries onto them.

A "provider" here means an API surface rather than a company. `gemini` is the
Gemini Developer API; a Vertex AI adapter would be a separate provider even
though both are Google.

Models are declared in config.json, not here, so swapping or adding a model needs
no code change. Adapters translate between that config and one HTTP API.

ADDING A PROVIDER
Subclass Provider, implement call() and usage(), and register it in PROVIDERS:

    class MyProvider(Provider):
        name = "myapi"
        env_key = "MYAPI_API_KEY"

        def call(self, model_id, prompt, search, options):
            raw = self._post(...)
            return raw["text"], [{"url": ..., "title": ..., "provider_field": ...}], raw

        def usage(self, raw):
            return {"input_tokens": ..., "output_tokens": ...}

    PROVIDERS["myapi"] = MyProvider()

Then add a model in config.json with "provider": "myapi". Override
reported_cost() if the API returns its own billed total, and
is_indirect_url()/resolve_url() if it returns redirect or proxy URLs that hide
the real publisher.

Every adapter returns (text, sources, raw) where each source is at minimum
{"url": str|None, "title": str|None, "provider_field": str}, and `raw` is the
untouched response body. runner.py stores `raw` verbatim, so extraction can be
rewritten later without re-spending API calls.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import paths


def _load_env() -> None:
    """Read .env without depending on python-dotenv. Real env vars win."""
    if not paths.ENV.exists():
        return
    for line in paths.ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


_load_env()


class ProviderError(RuntimeError):
    pass


class Provider:
    """Base adapter. Subclasses implement call() and usage()."""

    name: str = ""
    env_key: str = ""

    def api_key(self) -> str:
        key = os.environ.get(self.env_key)
        if not key:
            raise ProviderError(
                f"{self.env_key} is not set (needed by provider '{self.name}'). "
                f"Copy .env.example to .env and add it."
            )
        return key

    def call(self, model_id: str, prompt: str, search: bool, options: dict):
        """Return (text, sources, raw)."""
        raise NotImplementedError

    def usage(self, raw: dict) -> dict:
        """Return {"input_tokens": int, "output_tokens": int}."""
        raise NotImplementedError

    def reported_cost(self, raw: dict) -> float | None:
        """Provider-billed total, if the API reports one. None means compute it."""
        return None

    def reported_sampling(self, raw: dict) -> dict:
        """Effective sampling parameters the API echoes back, if any.

        Some APIs (OpenAI Responses) return the temperature/top_p actually used;
        others (Gemini generateContent, Perplexity) return nothing, in which case
        this is empty and the value is the provider/model default. See
        make_caller, which records this alongside what the caller requested.
        """
        return {}

    def is_indirect_url(self, url: str | None) -> bool:
        """True if `url` is a redirect/proxy that hides the real publisher."""
        return False

    def resolve_url(self, url: str, timeout: int = 20) -> tuple[str | None, int | None]:
        """Resolve an indirect URL. Returns (resolved_url|None, http_status|None)."""
        return None, None

    # shared HTTP helper
    def _post(self, url: str, payload: dict, headers: dict, timeout: int = 180) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:2000]
            raise ProviderError(f"{self.name} HTTP {exc.code}: {body}") from exc


class OpenAIProvider(Provider):
    """OpenAI Responses API with the built-in `web_search` tool.

    Citations arrive as url_citation annotations on output_text content blocks.

    A note for cost estimation: retrieved search content is added to the prompt
    and billed as input tokens at full model rates, so a grounded call can carry
    far more input tokens than the question itself.

    options:
      search_context_size  "low" | "medium" | "high" (provider default if unset)
      extra_payload        dict merged into the request body
    """

    name = "openai"
    env_key = "OPENAI_API_KEY"
    endpoint = "https://api.openai.com/v1/responses"

    def call(self, model_id, prompt, search, options):
        payload: dict = {"model": model_id, "input": prompt}
        if search:
            tool: dict = {"type": "web_search"}
            if options.get("search_context_size"):
                tool["search_context_size"] = options["search_context_size"]
            payload["tools"] = [tool]
        payload.update(options.get("extra_payload") or {})

        raw = self._post(
            self.endpoint, payload, {"Authorization": f"Bearer {self.api_key()}"}
        )

        text_parts, sources = [], []
        for item in raw.get("output", []):
            if item.get("type") != "message":
                continue
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    text_parts.append(block.get("text", ""))
                for ann in block.get("annotations", []):
                    if ann.get("type") == "url_citation":
                        sources.append(
                            {
                                "url": ann.get("url"),
                                "title": ann.get("title"),
                                "provider_field": "annotations.url_citation",
                            }
                        )
        return "".join(text_parts), sources, raw

    def usage(self, raw):
        u = raw.get("usage") or {}
        return {
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
        }

    def reported_sampling(self, raw):
        # The Responses API echoes the sampling config actually applied.
        return {k: raw[k] for k in
                ("temperature", "top_p", "frequency_penalty", "presence_penalty")
                if k in raw}


class GeminiProvider(Provider):
    """Gemini Developer API with the `google_search` grounding tool.

    Sources come back as groundingMetadata.groundingChunks[].web, where `title`
    is the registrable domain and `uri` is a vertexaisearch redirect rather than
    the publisher URL. resolve_url() turns those into real URLs.

    The model decides whether to search at all. A response with no
    groundingMetadata is a real zero-source result, not an error.

    options:
      extra_payload  dict merged into the request body (e.g. generationConfig)
    """

    name = "gemini"
    env_key = "GOOGLE_API_KEY"
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    REDIRECT_HOST = "vertexaisearch.cloud.google.com/grounding-api-redirect"

    def call(self, model_id, prompt, search, options):
        payload: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        if search:
            payload["tools"] = [{"google_search": {}}]
        payload.update(options.get("extra_payload") or {})

        raw = self._post(
            f"{self.base}/{model_id}:generateContent",
            payload,
            {"x-goog-api-key": self.api_key()},
        )

        cand = (raw.get("candidates") or [{}])[0]
        text = "".join(
            p.get("text", "") for p in cand.get("content", {}).get("parts", [])
        )
        sources = []
        for chunk in cand.get("groundingMetadata", {}).get("groundingChunks", []):
            web = chunk.get("web") or {}
            if web:
                sources.append(
                    {
                        "url": web.get("uri"),
                        "title": web.get("title"),
                        "provider_field": "groundingMetadata.groundingChunks.web",
                    }
                )
        return text, sources, raw

    def usage(self, raw):
        u = raw.get("usageMetadata") or {}
        # Thinking tokens bill as output but are reported in their own field.
        return {
            "input_tokens": u.get("promptTokenCount", 0),
            "output_tokens": u.get("candidatesTokenCount", 0)
            + u.get("thoughtsTokenCount", 0),
        }

    def is_indirect_url(self, url):
        return bool(url) and self.REDIRECT_HOST in url

    def resolve_url(self, url, timeout=20):
        """Read the redirect target without fetching the destination page.

        This relies on undocumented behavior that has been stable in practice:
        the endpoint returns a 3xx whose Location header is the real URL, so only
        the headers are read.
        """

        class _Catch(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):  # noqa: ANN001
                raise _Redirect(newurl, code)

        opener = urllib.request.build_opener(_Catch)
        try:
            with opener.open(
                urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                timeout=timeout,
            ) as resp:
                return None, resp.status
        except _Redirect as r:
            return r.url, r.code
        except urllib.error.HTTPError as exc:
            return None, exc.code
        except Exception:
            return None, None


class _Redirect(Exception):
    def __init__(self, url: str, code: int) -> None:
        super().__init__(url)
        self.url = url
        self.code = code


class PerplexityProvider(Provider):
    """Perplexity Sonar, an OpenAI-compatible chat/completions surface.

    Sonar always retrieves; there is no tool-free mode, so models using it should
    set supports_search_off: false in config.json.

    options:
      extra_payload  dict merged into the request body (e.g. search_domain_filter)
    """

    name = "perplexity"
    env_key = "PERPLEXITY_API_KEY"
    endpoint = "https://api.perplexity.ai/chat/completions"

    def call(self, model_id, prompt, search, options):
        if not search:
            raise ProviderError(
                "Perplexity always retrieves and has no search-off mode. Set "
                "supports_search_off: false for this model, or run only "
                "--conditions search_on."
            )
        payload = {"model": model_id, "messages": [{"role": "user", "content": prompt}]}
        payload.update(options.get("extra_payload") or {})

        raw = self._post(
            self.endpoint, payload, {"Authorization": f"Bearer {self.api_key()}"}
        )

        text = (raw.get("choices") or [{}])[0].get("message", {}).get("content", "")
        sources = []
        for result in raw.get("search_results") or []:
            sources.append(
                {
                    "url": result.get("url"),
                    "title": result.get("title"),
                    "provider_field": "search_results",
                }
            )
        if not sources:
            for url in raw.get("citations") or []:
                sources.append(
                    {"url": url, "title": None, "provider_field": "citations"}
                )
        return text, sources, raw

    def usage(self, raw):
        u = raw.get("usage") or {}
        return {
            "input_tokens": u.get("prompt_tokens", 0),
            "output_tokens": u.get("completion_tokens", 0),
        }

    def reported_cost(self, raw):
        cost = (raw.get("usage", {}).get("cost") or {}).get("total_cost")
        return float(cost) if cost is not None else None


PROVIDERS: dict[str, Provider] = {
    p.name: p for p in (OpenAIProvider(), GeminiProvider(), PerplexityProvider())
}


def load_models() -> dict:
    """Model definitions from config.json, validated against the registry."""
    models = paths.load_config().get("models") or {}
    if not models:
        raise ProviderError("config.json defines no models.")
    for key, spec in models.items():
        for field in ("provider", "model_id"):
            if not spec.get(field):
                raise ProviderError(f"model '{key}' is missing required field '{field}'")
        if spec["provider"] not in PROVIDERS:
            raise ProviderError(
                f"model '{key}' names unknown provider '{spec['provider']}'. "
                f"Known providers: {', '.join(sorted(PROVIDERS))}"
            )
    return models


def provider_for(model_key: str) -> Provider:
    return PROVIDERS[load_models()[model_key]["provider"]]


_SAMPLING_KEYS = ("temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty")


def _requested_sampling(provider_name: str, options: dict) -> dict:
    """Sampling parameters the caller set via options.extra_payload, if any.

    Empty means none were set and the provider/model default applied. Gemini nests
    generation parameters under generationConfig, so look there for that provider.
    """
    payload = (options or {}).get("extra_payload") or {}
    src = payload.get("generationConfig", payload) if provider_name == "gemini" else payload
    return {k: src[k] for k in _SAMPLING_KEYS if k in src}


def make_caller():
    """Return the function runner.py invokes per cell."""
    models = load_models()

    def call(cell, prompt: dict) -> dict:
        spec = models[cell.model_key]
        provider = PROVIDERS[spec["provider"]]
        search = cell.search == "search_on"
        if not search and not spec.get("supports_search_off", True):
            raise ProviderError(
                f"model '{cell.model_key}' declares supports_search_off: false; "
                f"exclude it from the search_off condition"
            )

        options = spec.get("options") or {}
        started = time.time()
        text, sources, raw = provider.call(
            spec["model_id"], prompt["text"], search, options
        )
        return {
            "cell_id": cell.cell_id,
            "provider": spec["provider"],
            "model_key": cell.model_key,
            "model_id": spec["model_id"],
            "search": cell.search,
            "prompt_id": cell.prompt_id,
            "prompt_text": prompt["text"],
            "language": prompt.get("language"),
            "variant": prompt.get("variant"),
            "topic": prompt.get("topic"),
            "run_index": cell.run_index,
            "text": text,
            "structured_sources": sources,
            # Sampling config, so it need not be reconstructed from vendor docs later.
            # `requested` is what the caller set (empty means the provider default
            # applied); `reported` is what the API echoed back (empty for providers
            # that don't return it).
            "sampling": {
                "requested": _requested_sampling(spec["provider"], options),
                "reported": provider.reported_sampling(raw),
            },
            "latency_ms": int((time.time() - started) * 1000),
            "raw": raw,
        }

    return call
