# 모든 API 키에 31B 최소 콜 1발씩 쏴 키별 가용성(OK/429/5xx/기타)을 점검하는 일회성 프로브
"""사용: python probe_keys.py
각 키로 짧은 generate 1콜(재시도 없음, 페이서 없음 — 생짜 상태 확인). 키 원문은 안 찍고
지문(앞4·뒤4)만. 429가 보이면 폭풍/소진, 5xx면 서버측 일시 장애."""

import concurrent.futures as cf

from config import force_utf8_stdout, get_api_keys

MODEL = "gemma-4-31b-it"
PROMPT = "Reply with the single word: pong"


def _probe(idx: int, key: str) -> tuple[int, str, str]:
    fp = f"{key[:4]}..{key[-4:]}"
    try:
        from google import genai
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=MODEL, contents=PROMPT,
            config={"max_output_tokens": 8, "temperature": 0})
        text = (getattr(resp, "text", None) or "").strip()
        return idx, fp, f"OK ({text[:20]!r})" if text else "OK (empty)"
    except Exception as err:  # noqa: BLE001 - 상태만 분류
        msg = str(err)
        code = "ERR"
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            code = "429"
        elif "500" in msg or "INTERNAL" in msg:
            code = "500"
        elif "503" in msg or "UNAVAILABLE" in msg:
            code = "503"
        return idx, fp, f"{code}: {msg[:90]}"


def main() -> int:
    force_utf8_stdout()
    keys = get_api_keys()
    print(f"[PROBE] {len(keys)}개 키, 모델 {MODEL}, 키당 1콜(병렬, 재시도 없음)\n")
    rows = []
    with cf.ThreadPoolExecutor(max_workers=len(keys)) as ex:
        futs = [ex.submit(_probe, i, k) for i, k in enumerate(keys, 1)]
        for fut in cf.as_completed(futs):
            rows.append(fut.result())
    rows.sort()
    ok = 0
    for idx, fp, status in rows:
        if status.startswith("OK"):
            ok += 1
        print(f"  키{idx:02d} [{fp}]  {status}")
    print(f"\n[PROBE] OK {ok}/{len(keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
