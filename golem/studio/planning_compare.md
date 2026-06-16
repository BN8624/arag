# Planning A/B/C 비교

- 아이디어: 작은 텍스트 로그라이크: 타일 이동 + 적 전투 + 아이템 획득
- API 호출: 0회

| arm | 모드 | total | unique | dup_rate | blocking |
|---|---|---|---|---|---|
| A | self-review | 2 | 2 | 0.0 | 0 |
| B | 3 independent reviewers | 6 | 6 | 0.0 | 0 |
| C | 10 independent reviewers | 13 | 12 | 0.077 | 1 |

## 판정(§19 PENDING-004)
- B vs A: unique 2->6 (gain=2.0) → 독립리뷰 채택 근거 있음
- C vs B: unique 6->12 (gain=1.0) → 10리뷰어 채택 근거 있음
