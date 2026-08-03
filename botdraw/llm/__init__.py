"""LettersBot-only LLM sidecar with graceful fallback."""

from __future__ import annotations

from typing import Protocol

from botdraw.letters import motifs_for_era


class LLMProvider(Protocol):
    def draft(self, prompt: str) -> str: ...


class NoneProvider:
    def draft(self, prompt: str) -> str:
        raise RuntimeError("LLM disabled")


class LocalOllamaProvider:
    def __init__(self, model: str = "llama3.2:3b", base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def draft(self, prompt: str) -> str:
        import httpx

        resp = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


_ACTIVE: LLMProvider | None = None
_LOADED = False


def set_provider(provider: LLMProvider | None) -> None:
    global _ACTIVE, _LOADED
    _ACTIVE = provider
    _LOADED = provider is not None


def unload() -> None:
    set_provider(None)


def is_loaded() -> bool:
    return _LOADED


def try_local_ollama() -> bool:
    try:
        import httpx

        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
        if r.status_code == 200:
            set_provider(LocalOllamaProvider())
            return True
    except Exception:
        pass
    unload()
    return False


def draft_wedding_letter(
    *,
    names: str,
    language: str = "en",
    era: str = "90s",
    mood: str = "romantic",
    facts: str = "",
    guest_quote: str | None = None,
) -> dict:
    motifs = motifs_for_era(era, mood)
    motif = motifs[0] if motifs else {"motif": "shared laughter", "allusion": "in the spirit of enduring love songs"}
    prompt = (
        f"Write a short handwritten love letter for a wedding.\n"
        f"Couple: {names}\nLanguage code: {language}\n"
        f"Facts: {facts}\nMotif: {motif.get('motif')}\n"
        f"Allusion mode only (no full lyrics): {motif.get('allusion')}\n"
        f"Guest quote to include if provided: {guest_quote or '(none)'}\n"
        f"Keep under 180 words. Warm, human, not robotic."
    )
    if _ACTIVE is not None:
        try:
            text = _ACTIVE.draft(prompt)
            return {"source": "llm", "body": text, "motif": motif}
        except Exception as exc:
            fallback = _template_letter(names, language, motif, facts, guest_quote)
            return {"source": "template", "body": fallback, "motif": motif, "llm_error": str(exc)}
    return {
        "source": "template",
        "body": _template_letter(names, language, motif, facts, guest_quote),
        "motif": motif,
    }


def _template_letter(names: str, language: str, motif: dict, facts: str, guest_quote: str | None) -> str:
    quote_block = f'\n\n"{guest_quote}"\n' if guest_quote else "\n"
    lang_note = {
        "en": "My dearest",
        "hi": "Mere pyar",
        "pa": "Mere dil",
        "ur": "Mere humsafar",
    }.get(language, "My dearest")
    return (
        f"{lang_note} {names},\n\n"
        f"Today I write with ink what my heart has practiced for years. "
        f"I keep returning to the feeling of {motif.get('motif')}, "
        f"{motif.get('allusion')}. "
        f"{facts.strip() + ' ' if facts else()}"
        f"Wherever the music leads us, I choose you again.{quote_block}"
        f"Forever,\nYour person"
    )
