# Contract Validation Report (Golem Studio v0.1)

- 전체 판정: [OK]
- API 호출: 0회
- 픽스처: 11/11 통과

| 픽스처 | 기대 | 결과 ok | 실패한 check | 판정 |
|---|---|---|---|---|
| demo_fail_bare_default | 실패@import_export | False | import_export | [OK] |
| demo_fail_circular | 실패@import_export | False | import_export | [OK] |
| demo_fail_export_mismatch | 실패@import_export | False | import_export | [OK] |
| demo_fail_math_random | 실패@static_gate | False | static_gate | [OK] |
| demo_fail_missing_file | 실패@file_exists | False | file_exists, import_export | [OK] |
| demo_fail_npm_import | 실패@static_gate | False | static_gate | [OK] |
| demo_fail_parent_path_escape | 실패@import_export | False | import_export | [OK] |
| demo_fail_unreachable_module | 실패@static_gate | False | static_gate | [OK] |
| demo_pass | 통과 | True | - | [OK] |
| demo_pass_module_exports_prop | 통과 | True | - | [OK] |
| demo_pass_multiline_module_exports_object | 통과 | True | - | [OK] |

