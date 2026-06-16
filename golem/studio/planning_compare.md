# Planning A/B/C 비교

- 아이디어: 방치형 게임: 틱마다 자원이 자동으로 쌓이고, 모은 자원으로 업그레이드를 사서 생산 속도를 올린다 (결정적, node main.js --scenario N)
- API 호출: None회

| arm | 모드 | total | unique | dup_rate | blocking |
|---|---|---|---|---|---|
| A | self-review | 6 | 6 | 0.0 | 3 |
| B | 3 independent reviewers | 11 | 11 | 0.0 | 6 |
| C | 10 independent reviewers | 28 | 27 | 0.036 | 12 |

## 판정(§19 PENDING-004)
- B vs A: unique 6->11 (gain=0.833) → 독립리뷰 채택 근거 있음
- C vs B: unique 11->27 (gain=1.455) → 10리뷰어 채택 근거 있음
