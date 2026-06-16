# 키 11개를 순차로 한 콜씩 찔러 생존·지연·에러를 판정하는 프로브(재시도 없음, 1키=1콜).
import sys
import time

sys.path.insert(0, r"C:\Users\USER\arag")
from config import force_utf8_stdout, get_api_keys, get_model  # noqa: E402

force_utf8_stdout()

MODEL = get_model("critic")  # 31solo = gemma-4-31b-it (캠페인이 쓰는 모델)
keys = get_api_keys()
print(f"[PROBE] model={MODEL}, keys={len(keys)}개, 순차 1콜씩 (재시도 없음)\n")

from google import genai  # noqa: E402

ok = 0
for i, key in enumerate(keys, 1):
    tag = f"key{i:02d}(...{key[-4:]})"
    t0 = time.monotonic()
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(model=MODEL, contents="Reply with exactly: PONG")
        dt = time.monotonic() - t0
        text = (getattr(resp, "text", "") or "").strip().replace("\n", " ")[:40]
        print(f"[OK]   {tag}  {dt:5.1f}s  resp={text!r}")
        ok += 1
    except Exception as err:  # noqa: BLE001
        dt = time.monotonic() - t0
        code = getattr(err, "code", None) or getattr(err, "status_code", None)
        msg = str(err).replace("\n", " ")[:120]
        print(f"[FAIL] {tag}  {dt:5.1f}s  code={code}  {msg}")
    time.sleep(1.0)  # 같은 구글 백엔드 분출 평탄화용 소간격

print(f"\n[PROBE] 생존 {ok}/{len(keys)}")
