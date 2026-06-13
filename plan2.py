# PLAN 2 파생 레이어 (콜0): 결과 라벨 5종 + 점수 _auto + protocol_fingerprint를 index+observability에서 파생
"""PLAN.md §3·§4 구현 — 측정용 파생 뷰. 정본을 새로 저장하지 않고
runs/index.json 엔트리 + observability.classify_run에서 계산한다.

- 결과 라벨 5종: PASS / PARTIAL_USEFUL / MODEL_FAIL / INFRA_FAIL / HARNESS_FAIL
- 점수 _auto: prototype_score_auto, failure_usefulness_auto (사람이 폰 감사에서 _user로 덮어씀)
- protocol_fingerprint: 비교 조건(프롬프트·예산·카드풀·라벨셋·모드) 펼쳐 기록 (해시 X)
"""

from observability import classify_run

PROTOCOL_VERSION = "p2.0"
CARD_POOL_VERSION = "p2-cards-v1"
LABEL_SET_VERSION = "p2-labels-v1"
REPAIR_BUDGET = 3  # K=3 (가드레일 동결값)

LABELS = ("PASS", "PARTIAL_USEFUL", "MODEL_FAIL", "INFRA_FAIL", "HARNESS_FAIL")

# observability limit_type → PLAN2 라벨 (실패 런만)
_LIMIT_TO_LABEL = {
    "INFRA_LIMIT": "INFRA_FAIL",
    "SPEC_LIMIT": "HARNESS_FAIL",   # 시험지/oracle 결함
    "LOOP_LIMIT": "HARNESS_FAIL",   # 루프 구조가 기회를 못 줌 (모델 탓 아님)
}


def run_label(entry: dict, classify_row: dict) -> str:
    """런 하나의 PLAN2 결과 라벨. entry=index 엔트리, classify_row=classify_run 결과."""
    if entry.get("ok") or str(entry.get("status", "")).startswith("OK"):
        return "PASS"
    limit = classify_row.get("limit_type", "UNKNOWN")
    if limit in _LIMIT_TO_LABEL:
        return _LIMIT_TO_LABEL[limit]
    # MODEL_LIMIT / UNKNOWN: 관측가능한 좋은 실패면 PARTIAL_USEFUL, 아니면 MODEL_FAIL
    if classify_row.get("quality") == "good":
        return "PARTIAL_USEFUL"
    return "MODEL_FAIL"


def prototype_score_auto(entry: dict, classify_row: dict) -> int:
    """0~5 기계 잠정치. 사람이 폰 감사에서 _user로 덮어씀."""
    score = entry.get("score") or {}
    passed = score.get("passed") or 0
    total = score.get("total") or 0
    ratio = (passed / total) if total else 0
    if entry.get("ok") or str(entry.get("status", "")).startswith("OK"):
        if ratio >= 1:
            return 5
        if ratio >= 0.8:
            return 4
        return 3  # 통과했으나 수용기준 일부 미달(partial)
    if passed > 0:
        return 2  # 실패지만 일부 기능은 동작
    if classify_row.get("quality") == "junk":
        return 0  # 아무것도 안 남음
    return 1  # 실행 불안정/거의 없음


def failure_usefulness_auto(entry: dict, classify_row: dict) -> int:
    """0~5 기계 잠정치. 성공 런은 0(실패 부산물 없음), 실패 런은 artifact_score 재사용."""
    if entry.get("ok") or str(entry.get("status", "")).startswith("OK"):
        return 0
    return int(classify_row.get("artifact_score") or 0)


def protocol_fingerprint(entry: dict) -> dict:
    """비교 조건을 펼친 객체(해시 X). 캠페인 간 비교 무결성 보호."""
    return {
        "prompt_version": entry.get("prompt_version"),
        "card_pool_version": CARD_POOL_VERSION,
        "label_set_version": LABEL_SET_VERSION,
        "repair_budget": REPAIR_BUDGET,
        "notes_mode": entry.get("mode", "warm"),
    }


def build_record(entry: dict, run_dir=None) -> dict:
    """index 엔트리 → PLAN2 측정 레코드(파생). run_dir 있으면 events로 분류 정밀."""
    classify_row = classify_run(run_dir, entry) if run_dir is not None \
        else {"ok": entry.get("ok"), "limit_type": "UNKNOWN",
              "artifact_score": 0, "quality": "junk"}
    return {
        "protocol_version": PROTOCOL_VERSION,
        "protocol_fingerprint": protocol_fingerprint(entry),
        "run": entry.get("run"),
        "task_id": entry.get("task_id"),
        "card_level": entry.get("level"),
        "mode": entry.get("mode", "warm"),
        "notes_enabled": entry.get("notes_enabled", True),
        "final_label": run_label(entry, classify_row),
        "repair_rounds": (entry.get("critique_rounds")
                          if entry.get("critique_rounds") is not None else None),
        "prototype_score_auto": prototype_score_auto(entry, classify_row),
        "prototype_score_user": None,
        "failure_usefulness_auto": failure_usefulness_auto(entry, classify_row),
        "failure_usefulness_user": None,
        "human_audit_status": "pending",
        "cost_usd": entry.get("cost_usd") or 0,
    }
