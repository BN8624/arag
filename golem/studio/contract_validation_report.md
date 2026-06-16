# Contract Validation Report (Golem Studio v0.1)

- 전체 판정: [OK]
- API 호출: 0회
- 픽스처: 5/5 통과

| 픽스처 | 기대 | 결과 ok | 실패한 check | 판정 |
|---|---|---|---|---|
| demo_fail_bare_default | 실패@import_export | False | import_export | [OK] |
| demo_fail_circular | 실패@import_export | False | import_export | [OK] |
| demo_fail_export_mismatch | 실패@import_export | False | import_export | [OK] |
| demo_fail_missing_file | 실패@file_exists | False | file_exists, import_export | [OK] |
| demo_pass | 통과 | True | - | [OK] |

