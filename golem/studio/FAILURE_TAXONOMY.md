# 실패 분류 통합 인벤토리 (golem studio)

목적은 "새 분류를 추가하는 것"이 아니라 **이미 있는 분류의 난립을 막는 것**이다.
실패 시 롤백 위치를 감이 아니라 분류로 정하되, 상위 taxonomy를 새로 도입하기 전에
기존 라벨(plan2 + reconcile + 게이트)로 충분한지 먼저 판정한다.

## 1. 이미 있는 분류 (나란히 정리)
| 출처 | 라벨/진단 | 범위 |
|---|---|---|
| `plan2.py` | PASS / PARTIAL_USEFUL / MODEL_FAIL / INFRA_FAIL / HARNESS_FAIL | 런 단위 결과 |
| `reconcile.py` | CONTRACT_AMBIGUOUS / ORACLE_BUG / BUILD_BUG (+ AUTO/ESCALATE) | **Build 합의 ↔ oracle 슬라이스만** |
| 게이트 | manifest_schema / file_exists / import_export / static_gate | 정적 차단 |

**reconcile는 "Gemma 빌드 합의가 oracle과 다를 때"만 자동 진단·라우팅한다.** Planning/Design/Manifest/
Integration/Scope 전체를 덮지 않는다 — 이 슬라이스 밖 실패는 plan2 라벨/게이트 결과로 분류한다.

## 2. 판정 게이트 (상위 taxonomy 도입 전에)
- 새 실패를 만나면 먼저 위 3종으로 분류되는지 본다.
- 기존 라벨로 롤백 위치가 정해지면 **새 분류를 만들지 않는다**(난립 금지).
- 기존 라벨로 안 잡히는 실패가 반복될 때만 아래 상위 분류를 **그때 도입**한다.

## 3. 도입 후보 (필요할 때만 — 아직 정식 분류 아님)
| 후보 분류 | 언제 필요 | 롤백 대상 | 기존 라벨로 덮이나 |
|---|---|---|---|
| SPEC_AMBIGUITY | 요구가 두 해석 가능 | Planning/Design | reconcile=CONTRACT_AMBIGUOUS로 대개 덮임 |
| TEST_ORACLE_ERROR | expected가 계약과 다름 | Spec QA | reconcile=ORACLE_BUG로 덮임 |
| IMPLEMENTATION_BUG | 계약 맞는데 코드 틀림 | Build | reconcile=BUILD_BUG로 덮임 |
| MANIFEST_MISMATCH | 파일/export/import 불일치 | Design/Tasking | 게이트(import_export/file_exists)로 덮임 |
| INTEGRATION_ERROR | 모듈 OK인데 조립 실패 | Integration/Design | 게이트(static_gate 도달성)로 일부 덮임 — 미흡 시 도입 |
| SCOPE_BLOAT | 기능 과다로 핵심 실패 | Planning/DEPRECATION | 아직 자동 라벨 없음 — 도입 후보 1순위 |

판정: 위 6개 중 **MANIFEST/SPEC/ORACLE/IMPL은 기존 라벨로 충분**(새로 안 만듦).
INTEGRATION_ERROR·SCOPE_BLOAT만 기존 라벨에 빈틈이 있어 향후 도입 검토 대상이다.
