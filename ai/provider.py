"""
ai/provider.py
One small class that talks to the AI service, so the provider can be swapped (requirement 16).
Default: Google Gemini free tier (Google AI Studio key). Only urllib is used.

    GEMINI_API_KEY   your key (never sent to the browser)
    GEMINI_MODEL     model name (default from config.GEMINI_DEFAULT_MODEL)

Every failure is turned into an AIError with a FRIENDLY message - pages never crash.
"""
import json
import os
import socket
import urllib.error
import urllib.request

from config import AI_TIMEOUT_SECONDS, GEMINI_DEFAULT_MODEL


class AIError(Exception):
    """kind: no_key | no_internet | rate_limit | timeout | bad_key | empty | http | blocked"""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind, self.message = kind, message


SETUP_STEPS = ("The AI features need a free Google Gemini API key. 1) Open https://aistudio.google.com/apikey and create a key. "
               "2) Set it as the environment variable GEMINI_API_KEY (Windows: setx GEMINI_API_KEY \"your-key\" then reopen the "
               "terminal; macOS/Linux: export GEMINI_API_KEY=\"your-key\"). 3) Restart the app. Everything else in SQMA works without a key.")


class GeminiProvider:
    name = "Google Gemini"

    def __init__(self, api_key=None, model=None, timeout=AI_TIMEOUT_SECONDS):
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self.model = model or os.environ.get("GEMINI_MODEL") or GEMINI_DEFAULT_MODEL
        self.timeout = timeout

    @property
    def configured(self):
        key = self.api_key.strip()
        return bool(key and key != "your_actual_api_key_here")

    # -- network layer (a single method so tests can replace it)
    def _post(self, url, payload, headers):
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def generate(self, system_text, messages, max_tokens=1200):
        """messages: [{"role": "user"|"model", "content": str}, ...]. Returns the answer text."""
        if not self.configured:
            raise AIError("no_key", SETUP_STEPS)
        
        # Build candidate models starting with user configured model, followed by reliable defaults
        candidates = [self.model]
        for fb in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-flash-latest"):
            if fb not in candidates:
                candidates.append(fb)

        last_error = None
        for cand in candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand}:generateContent"
            payload = {
                "system_instruction": {"parts": [{"text": system_text}]},
                "contents": [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
            }
            headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
            try:
                data = self._post(url, payload, headers)
                self.model = cand  # remember working model
                return self._extract(data)
            except urllib.error.HTTPError as e:
                code = e.code
                if code == 404:
                    # Model not found on this candidate, try the next candidate
                    last_error = AIError("http", f"Model '{cand}' was not found. Tried: {', '.join(candidates)}.")
                    continue
                if code == 429:
                    raise AIError("rate_limit", "The free AI quota is used up for the moment (rate limit). Wait a minute and try again.")
                if code in (400, 401, 403):
                    raise AIError("bad_key", "Google rejected the request - the GEMINI_API_KEY looks invalid or has no access to "
                                             f"model '{cand}'. Check the key and GEMINI_MODEL.")
                raise AIError("http", f"The AI service returned an error (HTTP {code}). Try again later.")
            except (socket.timeout, TimeoutError):
                raise AIError("timeout", "The AI service took too long to answer. Try again.")
            except urllib.error.URLError as e:
                if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
                    raise AIError("timeout", "The AI service took too long to answer. Try again.")
                raise AIError("no_internet", "Cannot reach the AI service - check your internet connection. "
                                             "(All other SQMA pages work offline.)")
            except (ValueError, OSError):
                raise AIError("http", "The AI service sent an unreadable answer. Try again.")
        if last_error:
            raise last_error
        raise AIError("http", "Could not reach any supported Gemini model.")

    @staticmethod
    def _extract(data):
        fb = (data or {}).get("promptFeedback", {})
        if fb.get("blockReason"):
            raise AIError("blocked", "The AI declined to answer this request. Rephrase your question.")
        cands = (data or {}).get("candidates") or []
        text = ""
        if cands:
            parts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise AIError("empty", "The AI returned an empty answer. Please try again or rephrase.")
        return text


def get_provider():
    return GeminiProvider()
