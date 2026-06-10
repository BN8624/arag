"""로드맵 1단계: API 연결 확인.

- 키 로드 확인
- 사용 가능한 gemma 모델 목록 출력 (모델 ID 확정용)
- 26B(generator)·31B(critic) 각 1콜 성공 확인
- JSON 응답 가능 여부 간이 확인 (프롬프트 JSON 방식)

사용법: python check_api.py
"""

import sys

from config import force_utf8_stdout, get_api_key, get_model


def main() -> int:
    force_utf8_stdout()

    try:
        api_key = get_api_key()
    except RuntimeError as err:
        print(f"[ERROR] {err}")
        return 1
    print(f"[OK] API key loaded ({len(api_key)} chars)")

    from google import genai
    client = genai.Client(api_key=api_key)

    print("\n[STEP] listing available gemma models...")
    available = []
    try:
        for m in client.models.list():
            name = (m.name or "").removeprefix("models/")
            if "gemma" in name.lower():
                available.append(name)
                print(f"  - {name}")
    except Exception as err:  # noqa: BLE001
        print(f"[WARN] could not list models: {err}")
    if not available:
        print("  (no gemma models listed - IDs below may still work directly)")

    from llm import LLMClient
    llm = LLMClient()
    ok = True
    for role in ("generator", "critic"):
        model = get_model(role)
        hint = ""
        if available and model not in available:
            close = [a for a in available
                     if any(tag in a for tag in ("26", "31")) or "gemma-4" in a]
            hint = f" (not in the listed models - candidates: {close or available})"
        print(f"\n[STEP] test call: role={role} model={model}{hint}")
        try:
            text = llm.generate(role, "Reply with exactly: PONG")
            snippet = text.strip().replace("\n", " ")[:80]
            print(f"[OK] {role} responded: {snippet!r}")
        except Exception as err:  # noqa: BLE001
            print(f"[FAIL] {role} call failed: {err}")
            if available:
                print(f"       try setting {role.upper()}_MODEL in .env to one of: "
                      f"{available}")
            ok = False

    if ok:
        print("\n[STEP] JSON-by-prompt check (critic)...")
        try:
            text = llm.generate(
                "critic",
                'Reply with a single JSON object only, no prose, no fences: '
                '{"status": "ok", "answer": 42}')
            from schema import extract_json
            print(f"[OK] JSON extractable: {extract_json(text) is not None} "
                  f"(raw head: {text.strip()[:60]!r})")
        except Exception as err:  # noqa: BLE001
            print(f"[WARN] JSON check call failed: {err}")

    print("\n" + ("[OK] API check passed - both models reachable"
                  if ok else "[FAIL] API check failed - see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
