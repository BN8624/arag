# Golem Studio v0.1 replay 하니스 — fake 픽스처를 계약 검증기에 돌려 expected와 대조한다(API 콜0)
"""fixtures/ 하위에서 expected.json을 가진 픽스처를 모두 찾아 contract_validator.validate를 돌린다.
통과 픽스처는 ok=true, 음성 픽스처는 ok=false이고 지정한 failing_check가 실제로 실패해야 '검증기 정상'으로 본다.
산출물: replay_result.json, contract_validation_report.md. 실제 Gemini/Gemma 호출은 없다.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract_validator  # noqa: E402

FIXTURES = HERE / "fixtures"


def _failed_checks(result):
    return [c["name"] for c in result["checks"] if not c["ok"]]


def run():
    fixtures = sorted(d for d in FIXTURES.iterdir()
                      if (d / "expected.json").is_file() and (d / "module_manifest.json").is_file())
    records = []
    for d in fixtures:
        expected = json.loads((d / "expected.json").read_text(encoding="utf-8"))
        result = contract_validator.validate(d / "workspace", d / "module_manifest.json")
        failed = _failed_checks(result)

        if expected["ok"]:
            assertion_ok = result["ok"] is True
            reason = "ok=true 기대" if assertion_ok else f"통과 기대인데 실패: {result['errors']}"
        else:
            want = expected.get("failing_check")
            assertion_ok = (result["ok"] is False) and (want in failed)
            if assertion_ok:
                reason = f"기대대로 {want} 실패"
            elif result["ok"]:
                reason = "실패 기대인데 통과함(검증기 빠뜨림)"
            else:
                reason = f"실패는 했으나 기대 check({want}) 아님. 실패: {failed}"

        records.append({
            "fixture": d.name,
            "expected": expected,
            "result_ok": result["ok"],
            "failed_checks": failed,
            "assertion_ok": assertion_ok,
            "reason": reason,
            "errors": result["errors"],
        })

    all_ok = all(r["assertion_ok"] for r in records)
    summary = {
        "ok": all_ok,
        "api_calls": 0,
        "fixtures_total": len(records),
        "fixtures_passed": sum(1 for r in records if r["assertion_ok"]),
        "records": records,
    }
    (HERE / "replay_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(summary)
    return summary


def _write_report(summary):
    lines = ["# Contract Validation Report (Golem Studio v0.1)", ""]
    lines.append(f"- 전체 판정: {'[OK]' if summary['ok'] else '[FAIL]'}")
    lines.append(f"- API 호출: {summary['api_calls']}회")
    lines.append(f"- 픽스처: {summary['fixtures_passed']}/{summary['fixtures_total']} 통과")
    lines.append("")
    lines.append("| 픽스처 | 기대 | 결과 ok | 실패한 check | 판정 |")
    lines.append("|---|---|---|---|---|")
    for r in summary["records"]:
        exp = "통과" if r["expected"]["ok"] else f"실패@{r['expected'].get('failing_check')}"
        mark = "[OK]" if r["assertion_ok"] else "[FAIL]"
        failed = ", ".join(r["failed_checks"]) or "-"
        lines.append(f"| {r['fixture']} | {exp} | {r['result_ok']} | {failed} | {mark} |")
    lines.append("")
    for r in summary["records"]:
        if not r["assertion_ok"]:
            lines.append(f"### {r['fixture']} 불일치")
            lines.append(f"- {r['reason']}")
            for e in r["errors"]:
                lines.append(f"  - {e}")
    (HERE / "contract_validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass
    s = run()
    print(f"[{'OK' if s['ok'] else 'FAIL'}] {s['fixtures_passed']}/{s['fixtures_total']} fixtures, API calls={s['api_calls']}")
    for r in s["records"]:
        print(f"  [{'OK' if r['assertion_ok'] else 'FAIL'}] {r['fixture']}: {r['reason']}")
    sys.exit(0 if s["ok"] else 1)
