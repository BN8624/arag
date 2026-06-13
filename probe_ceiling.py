# 한도 예상지점(≈32k 토큰) 집중 프로브: 큰 n으로 MAX_TOKENS(출력 천장)를 실제로 띄운다
import json, sys, time
from datetime import datetime
from google import genai
from config import PROJECT_ROOT, get_api_key, get_model
client=genai.Client(api_key=get_api_key())
role=sys.argv[1] if len(sys.argv)>1 else "generator"
mode=sys.argv[2] if len(sys.argv)>2 else "off"
model=get_model(role)
SI={"off":"Do not produce any internal reasoning or thinking. Output only the final answer directly.",
    "on":"<|think|>"}[mode]
NS=[150,280,400,500]
def P(n): return (f"Write a SINGLE complete Python file containing {n} independent utility "
  f"functions named util_1 through util_{n}. Each fully implemented (6-10 lines), one-line "
  f"docstring, real body (no pass/.../TODO). Output ONLY code in one fenced block.")
out=PROJECT_ROOT/"runs"/f"probe_ceiling_{datetime.now():%Y%m%d-%H%M%S}_{mode}.jsonl"
print(f"[CEILING] {role} {model} think={mode}")
maxed=0
for n in NS:
    r=None
    for a in range(6):
        try:
            time.sleep(4.5)
            r=client.models.generate_content(model=model,contents=P(n),config={"temperature":0.2,"system_instruction":SI})
            break
        except Exception as e:
            print(f"  n={n} retry{a+1}: {str(e)[:60]}"); time.sleep(6*(a+1))
    if r is None: print(f"  n={n} 실패"); continue
    u=getattr(r,"usage_metadata",None); g=lambda x:(getattr(u,x,0)or 0) if u else 0
    fr=str(r.candidates[0].finish_reason); ch=len(getattr(r,"text","")or"")
    rec={"n":n,"input":g("prompt_token_count"),"output":g("candidates_token_count"),
         "thinking":g("thoughts_token_count"),"total":g("total_token_count"),"chars":ch,"finish":fr}
    open(out,"a",encoding="utf-8").write(json.dumps(rec)+"\n")
    print(f"  n={n} out={rec['output']} think={rec['thinking']} total={rec['total']} chars={ch} {fr.split('.')[-1]}")
    if "MAX_TOKENS" in fr:
        maxed+=1
        if maxed>=2: print("  [STOP] 천장 확인"); break
    else: maxed=0
print(f"[OK] {out}")
