---
schema_version: 1
type: bug
slug: "orchestrator-robustness-fixes"
status: done
difficulty: high
created_at: "2026-05-27T11:45:00+09:00"
updated_at: "2026-05-27T11:48:00+09:00"
session_id: "manual-20260527-114500"
agent:
  id: "antigravity"
  version: "1.0"
language: "ko"
verified_by_user: true
files_touched:
  - path: "adelie/orchestrator.py"
    op: update
  - path: "package.json"
    op: update
  - path: "adelie/__init__.py"
    op: update
  - path: "CHANGELOG.md"
    op: update
  - path: "docs/index.html"
    op: update
related: []
tags:
  - "orchestrator"
  - "concurrency"
  - "self-healing"
  - "validation"
---
[x] 에이전트 오케스트레이터의 7대 안정성 및 자동 자율 복구 결함 수정 (v0.3.5)

## 발생 원인
1. **new_logic 조기 리턴 상태 리크**: `new_logic` 사이클 임계치 도달 시의 조기 `return`으로 인해 메트릭 저장, config.json 보존, process supervisor 정비 등 후속 마무리 처리가 누락되는 리크 현상.
2. **테스트 실패 시 Coder 피드백 대상 파일 누수**: Tester retry 내부에서 `_files = new_files` 형태로 전체 검증 대상을 단순 덮어써버려, Coder가 수정하지 않은 기존 타겟 파일들이 후속 테스트 회차에서 누락되는 취약성.
3. **스레드 안전성 결여 및 Data Race**: Phase 3 Tester 스레드에서 Coder task를 shallow copy하여 task의 feedback을 직접 덮어쓰는 과정에서, 원본 Expert 의사결정 오브젝트의 훼손 및 동시성 데이터 레이스가 발생함.
4. **에러 콘텍스트 데드락**: stuck 루프 감지를 통해 NORMAL 상태로 강제 전환될 때 이전 사이클의 잔류 에러 파일들이 지워지지 않아 AI가 오래된 오류 콘텍스트에 계속 갇힘.
5. **자체 문법 검증 실패 시의 무조건 폐기**: Staging 코드 문법 검증(`py_compile`) 실패 시 Coder에 피드백을 전달하는 재시도 장치가 전혀 없어, 작성된 코드가 소리소문없이 staging cleanup에 의해 삭제되는 문제.
6. **롤백(Self-Healing) 기구 누락**: `CheckpointManager`를 통해 Promotion 전 스냅샷을 생성하지만, 실제 에러 상황이나 복구 한계 도달 시 이 백업을 활용해 소스코드를 복구해주는 로직이 오케스트레이터 내에 전혀 구현되어 있지 않음.
7. **무실적 streak 카운팅 누수**: Coder가 파일은 썼지만 Reviewer나 PolicyGate 등에 막혀 최종 반영이 안 되는 무실적 stalemates 상황을 `zero_file_streak`가 올바르게 감지하지 못하고 0개 파일 쓰기 상태만 스캔함.

## 해결 방법
1. **new_logic 얼리 리턴 구문 제거**: `next_situation = "normal"`로 전환한 뒤 execution flow가 정상적으로 하단 로그 및 상태 저장 블록으로 이어지게 개선.
2. **Tester 파일 리스트 병합**: `new_files`에 포함된 신규 수정 파일을 기존 검증 목록에 병합하여 전체 타겟에 대한 통합 테스트가 계속 유지되도록 보장.
3. **Deep Copy 적용**: `copy.deepcopy(coder_tasks)`를 사용하여 스레드별 Coder 태스크 객체를 완벽히 독립적으로 분리.
4. **루프 감지 복구 시 에러 아카이빙 연동**: Stuck 복구 강제 NORMAL 전환 시 `self._archive_errors()`를 실행해 에러 히스토리를 아카이브로 밀어냄.
5. **구문 검증 Coder Retry 루프 신설**: promotion 직전 `_verify_staged_files`를 직접 실행하고, 실패한 파일의 문법 에러 로그를 취합하여 Coder에게 피드백을 제공하고 최대 2회 수정 기회를 부여함.
6. **체크포인트 복구(Self-Healing) 연동**: `action == "RECOVER"` 시 복구 한계에 다다르면 `CheckpointManager`의 `list_checkpoints()`를 뒤져 가장 최근의 정상 스냅샷으로 프로젝트 파일들을 자동 롤백(`restore()`) 처리함.
7. **Promotion 기준 streak 감지**: streak checker가 `all_written_files` 대신 실제로 최종 promotion 성공을 마친 `promoted_count == 0` 상황을 모니터링하여 코더 레지스트리 리셋을 유도함.
8. **버전 및 릴리즈 업데이트**: package.json, __init__.py, CHANGELOG.md, docs/index.html 파일에 0.3.5 버전 변경 내용을 통합 반영함.

## 검증
1. `source .venv/bin/activate && python -m adelie.cli --version` 실행 시 `adelie 0.3.5`가 오차 없이 출력되는 것을 확인.
2. 가상환경 내부에서 전체 750개 pytest 유닛 테스트 스위트를 구동하여 100% 통과 및 동시성/오케스트레이션 검증에 이상이 없음을 규명함.
