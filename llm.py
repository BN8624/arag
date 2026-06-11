"""API 콜 래퍼. 쿼터 4원칙 중 1·4를 여기서 강제한다.

- 순차 호출 (단일 스레드 전제, 동시 호출 없음)
- 콜 간 최소 간격 4초 (RPM 15 보호)
- 429 백오프 재시도 (RPM/RPD 구분)
- 500/502/503/504 + 네트워크 에러 재시도
- 빈 응답 재시도
- 회차당 콜 수 상한 (가드레일)
"""

import re
import socket
import time

from config import get_api_key, get_model

MIN_INTERVAL_SEC = 4.0

# 오픈라우터 유료 단가 (USD / 1M tokens, 2026-06 기준). thinking은 출력으로 과금.
# 실제 사용은 AI Studio 무료지만, "유료였다면 얼마"를 REPORT에 환산 표기한다.
OPENROUTER_PRICES = {
    "generator": {"input": 0.06, "output": 0.33},   # gemma-4-26b-a4b
    "critic":    {"input": 0.12, "output": 0.36},   # gemma-4-31b
}
MAX_RETRIES = 4
BACKOFF_RPM_SEC = 20.0   # RPM 초과: 20→40→80→160s
BACKOFF_500_SEC = 5.0    # 서버 에러: 5→10→20→40s
EMPTY_RETRIES = 2        # 빈 응답 재시도 상한


class CallBudgetExceeded(Exception):
    """회차당 API 콜 상한 초과."""


class ReplayExhausted(Exception):
    """재생할 녹음이 바닥남 (코드가 바뀌어 콜 순서가 달라졌을 때도 발생)."""


class ReplayLLM:
    """녹음(llm_calls.jsonl)을 역할별 순서대로 재생 (콜 0).

    실제 런에서 이상 동작이 났을 때, 같은 응답으로 orchestrator·게이트·rollback
    경로를 그대로 재현해 회귀를 잡는 용도. API 키·네트워크 불필요.
    """

    def __init__(self, record_path):
        import json
        from pathlib import Path

        self.queues: dict[str, list[str]] = {}
        for line in Path(record_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            self.queues.setdefault(entry["role"], []).append(entry["response"])
        self.call_count = 0
        self.max_calls = None
        self.record_path = None  # 재생 중에는 녹음하지 않는다
        self.tokens: dict[str, int] = {"input": 0, "output": 0, "thinking": 0}

    def generate(self, role: str, prompt: str, temperature: float | None = None) -> str:
        queue = self.queues.get(role)
        if not queue:
            raise ReplayExhausted(f"no recorded response left for role {role!r}")
        self.call_count += 1
        return queue.pop(0)


class DailyQuotaExceeded(Exception):
    """RPD(일일 한도) 초과 — 오늘은 더 이상 콜 불가."""


class EmptyResponse(Exception):
    """모델이 빈 응답을 반환."""


def _is_rate_limit(err: Exception) -> bool:
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if code == 429:
        return True
    return "429" in str(err) or "RESOURCE_EXHAUSTED" in str(err)


def _is_daily_quota(err: Exception) -> bool:
    """RPD 초과 여부. 일일 한도는 백오프로 복구 불가."""
    msg = str(err).lower()
    return any(k in msg for k in ("daily", "per day", "quota exceeded", "daily_limit"))


def _is_transient(err: Exception) -> bool:
    """서버 에러(5xx) 또는 네트워크 에러."""
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if isinstance(code, int) and code >= 500:
        return True
    if bool(re.search(r"\b(500|502|503|504)\b", str(err))):
        return True
    # SDK가 소켓 에러를 자기 예외로 감싸면 isinstance에 안 걸린다 —
    # 메시지 패턴으로도 잡는다 (WinError 10054 즉사 실관측, 2026-06-12 배치)
    msg = str(err).lower()
    if any(k in msg for k in ("winerror 10054", "connection reset",
                              "connection aborted", "connection refused",
                              "timed out", "deadline exceeded")):
        return True
    return isinstance(err, (ConnectionError, TimeoutError, socket.error,
                            OSError))


class LLMClient:
    def __init__(self, max_calls: int | None = None):
        # import을 여기서 해서, API를 안 쓰는 코드(게이트 등)는 SDK 없이도 돈다
        from google import genai

        self._client = genai.Client(api_key=get_api_key())
        self._last_call_at = 0.0
        self.call_count = 0
        self.max_calls = max_calls
        # 녹음: 경로를 지정하면 콜마다 응답 전문을 jsonl로 기록 (replay 재현용)
        self.record_path = None
        self.tokens: dict[str, int] = {"input": 0, "output": 0, "thinking": 0}
        self.tokens_by_role: dict[str, dict[str, int]] = {
            "generator": {"input": 0, "output": 0, "thinking": 0},
            "critic": {"input": 0, "output": 0, "thinking": 0},
        }

    def _record(self, role: str, model: str, prompt: str, response: str) -> None:
        """콜 1건 녹음. 실패해도 콜을 막지 않는다.

        prompt는 크기·머리만 (다이어트 효과 측정용), response는 전문 (replay용).
        """
        if not self.record_path:
            return
        try:
            import json
            from datetime import datetime
            entry = {"t": datetime.now().isoformat(timespec="seconds"),
                     "role": role, "model": model,
                     "prompt_chars": len(prompt), "prompt_head": prompt[:300],
                     "response": response}
            with open(self.record_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def cost_usd(self) -> dict[str, float]:
        """오픈라우터 유료 단가 환산 비용(USD). 역할별 + 합계."""
        costs: dict[str, float] = {}
        for role, toks in self.tokens_by_role.items():
            price = OPENROUTER_PRICES.get(role)
            if not price:
                continue
            costs[role] = (toks["input"] * price["input"]
                           + (toks["output"] + toks["thinking"]) * price["output"]
                           ) / 1_000_000
        costs["total"] = sum(costs.values())
        return costs

    def _wait_interval(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - elapsed)

    def generate(self, role: str, prompt: str, temperature: float | None = None) -> str:
        """role('generator'|'critic')의 모델로 1콜. 텍스트를 반환한다."""
        if self.max_calls is not None and self.call_count >= self.max_calls:
            raise CallBudgetExceeded(
                f"call budget exhausted ({self.call_count}/{self.max_calls})"
            )
        model = get_model(role)
        config = {}
        if temperature is not None:
            config["temperature"] = temperature

        last_err: Exception | None = None
        empty_count = 0
        for attempt in range(MAX_RETRIES + 1):
            self._wait_interval()
            try:
                self._last_call_at = time.monotonic()
                resp = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config or None,
                )
                self.call_count += 1
                usage = getattr(resp, "usage_metadata", None)
                if usage:
                    by_role = self.tokens_by_role.setdefault(
                        role, {"input": 0, "output": 0, "thinking": 0})
                    for key, attr in (("input", "prompt_token_count"),
                                      ("output", "candidates_token_count"),
                                      ("thinking", "thoughts_token_count")):
                        n = getattr(usage, attr, 0) or 0
                        self.tokens[key] += n
                        by_role[key] += n
                text = getattr(resp, "text", None)
                if text and text.strip():
                    self._record(role, model, prompt, text)
                if not text or not text.strip():
                    empty_count += 1
                    if empty_count > EMPTY_RETRIES:
                        raise EmptyResponse(f"empty response from {model} "
                                            f"({empty_count} times)")
                    wait = 4.0 * empty_count
                    print(f"[WAIT] empty response, retrying in {wait:.0f}s "
                          f"(attempt {empty_count}/{EMPTY_RETRIES})")
                    time.sleep(wait)
                    continue
                return text
            except EmptyResponse:
                raise
            except Exception as err:  # noqa: BLE001 - SDK 예외 타입이 유동적
                last_err = err
                if attempt >= MAX_RETRIES:
                    break
                if _is_rate_limit(err):
                    if _is_daily_quota(err):
                        raise DailyQuotaExceeded(
                            f"daily quota exhausted for {model}: {err}"
                        ) from err
                    wait = BACKOFF_RPM_SEC * (2 ** attempt)
                    print(f"[WAIT] rate limited (429), retrying in {wait:.0f}s "
                          f"(attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait)
                elif _is_transient(err):
                    wait = BACKOFF_500_SEC * (2 ** attempt)
                    print(f"[WAIT] server/network error, retrying in {wait:.0f}s "
                          f"(attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"API call failed after {MAX_RETRIES} retries: {last_err}")
