# 실패 분류 ↔ 진단 ↔ 롤백 매핑 (golem studio)

목적은 실패할 때 "어디로 롤백하나"를 감이 아니라 분류로 정하는 것이다. 세 분류 체계가 이미 있으니
새로 만들지 말고 매핑한다. `reconcile.py`는 그중 **Build↔oracle 슬라이스만** 자동으로 덮는다.

## 분류 체계 (이미 존재)
- `plan2.py` 라벨 5종: PASS / PARTIAL_USEFUL / MODEL_FAIL / INFRA_FAIL / HARNESS_FAIL (런 단위).
- `reconcile.py` 진단 3종: CONTRACT_AMBIGUOUS / ORACLE_BUG / BUILD_BUG (Build 합의 vs oracle 슬라이스).
- 게이트 실패: static_gate / contract_validator의 check 이름(manifest_schema/file_exists/import_export/static_gate).

## 매핑 표
| 실패 유형 | 자동 진단(있으면) | 롤백 대상 | 자동 처리 |
|---|---|---|---|
| SPEC_AMBIGUITY (요구가 두 해석 가능) | reconcile=CONTRACT_AMBIGUOUS | Planning/Design(계약 명문화) | reconcile AUTO면 계약 자동수정, ESCALATE면 사람 |
| TEST_ORACLE_ERROR (expected가 계약과 다름) | reconcile=ORACLE_BUG | Spec QA(시나리오 expected) | reconcile --apply가 expected 자동교정 |
| IMPLEMENTATION_BUG (계약 맞는데 코드가 틀림) | reconcile=BUILD_BUG | Build(재생성) | 재빌드 트리거(자동화 예정) |
| MANIFEST_MISMATCH (파일/export/import 불일치) | contract_validator check 실패 | Design/Tasking | 정적 게이트가 차단, 자가수정 |
| INTEGRATION_ERROR (모듈 OK인데 조립 실패) | static_gate(도달성/위장) | Integration/Design | 정적 게이트가 차단 |
| SCOPE_BLOAT (기능 과다로 핵심 실패) | plan2=PARTIAL_USEFUL 등 | Planning(또는 DEPRECATION) | 사람 판단 |
| INFRA (서버 5xx/키 고갈) | plan2=INFRA_FAIL | 롤백 아님(재시도) | 콜 래퍼 백오프 |

## 범위 주의
- reconcile은 "Gemma 빌드 합의가 oracle과 다를 때"만 자동 진단·라우팅한다. 그 외(스코프·인프라·조립)는
  plan2 라벨/게이트 결과로 분류하고, 롤백 대상은 위 표를 따른다.
- 새 분류축을 추가하기 전에 plan2/reconcile로 덮이는지 먼저 확인한다(분류 난립 금지).
