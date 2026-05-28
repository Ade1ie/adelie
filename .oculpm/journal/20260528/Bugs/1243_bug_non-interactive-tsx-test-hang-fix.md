---
schema_version: 1
type: bug
slug: non-interactive-tsx-test-hang-fix
status: done
difficulty: medium
created_at: "2026-05-28T12:43:00+09:00"
updated_at: "2026-05-28T12:43:15+09:00"
session_id: "manual-20260528-124300"
agent:
  id: antigravity
  version: "3.5"
language: ko
verified_by_user: false
files_touched:
  - path: adelie/agents/tester_ai.py
    op: update
  - path: package.json
    op: update
  - path: adelie/__init__.py
    op: update
  - path: CHANGELOG.md
    op: update
  - path: docs/index.html
    op: update
  - path: docs/adelie.rb
    op: update
related:
  - .oculpm/journal/20260528/Bugs/1233_bug_monorepo-scaffolding-check-loop-fix.md
tags: ["testing", "npx", "hang-prevention", "fail-fast", "tester-ai"]
---

[x] 비대화형 환경에서의 npx tsx 테스트 행(Hang) 방지 및 v0.3.8 릴리즈

## 발생 원인
프론트엔드 React 컴포넌트나 커스텀 훅 등의 `.ts`, `.tsx`, `.jsx` 테스트 코드를 실행할 때 Tester AI는 내부적으로 `npx tsx <테스트파일명>` 명령어를 조립하여 실행합니다. 
그러나 비대화형 쉘(Subprocess 실행 환경)에 `tsx` 패키지가 로컬/전역으로 존재하지 않는 경우, npm은 터미널에 **"Need to install the following packages: tsx. Ok to proceed? (y)"** 라는 사용자의 대화식 입력을 요청하며 정체(Hang) 상태가 됩니다. 이로 인해 제한시간인 60초(EXEC_TIMEOUT) 동안 응답 대기 상태로 머물다 결국 타임아웃 오류로 실패하면서, Coder AI와 Tester AI 간에 의미 없는 코드 재생성 루프가 무한히 반복되었습니다.

## 해결 방법
1. **무인 설치 플래그(-y) 도입**: `tester_ai.py` 내의 테스트 명령어 생성 로직에서 `npx tsx`를 **`npx -y tsx`**로 변경했습니다.
   - `-y` 플래그는 설치 질문 없이 자동으로 `tsx`를 실시간 무인 설치하여 즉각적인 검사를 속행하게 해 줍니다.
   - 행(Hang) 현상이 제거되어, 만약 Jest 글로벌이 정의되지 않아 생기는 다른 오류 등이 발생하더라도 지체 없이 즉각 에러 로그(예: `ReferenceError: describe is not defined`)를 뱉으며 1~2초 만에 종료됩니다(Fail-Fast).
   - 이를 통해 Coder AI는 테스트 실패 이유(정상 에러 백트레이스)를 투명하게 수집하여, 환경에 걸맞은 무결한 테스트 스크립트로 올바르게 회복할 수 있는 능력을 얻게 됩니다.
2. **릴리즈 패키지 버전 범프 (v0.3.8)**:
   - `package.json` 및 `adelie/__init__.py`에서 버전을 `0.3.8`로 올렸습니다.
   - `CHANGELOG.md`, `docs/index.html`(Changelog 항목 추가 및 배지 업데이트), `docs/adelie.rb` Homebrew URL을 `0.3.8`에 맞춤 업데이트했습니다.

## 검증
1. **단위 및 전체 테스트 자동화 검증**:
   - `pytest tests/test_tester_ai.py` 통과 완료.
   - `pytest` 전체 통합 테스트 실행 결과: **750 passed, 3 skipped, 2 warnings** 완료.
2. **수동 모의 검증**:
   - 테스트용 수동 검증 스크립트(`verify_tester_command.py`)를 통해 `run_tests` 함수가 실제 `npx -y tsx`를 포함하는 올바른 명령어를 조립하여 성공적으로 동작함을 최종 입증했습니다.

## 메모
* 비대화형 Agent 루프 환경에서 무인 패키지 설치 플래그(`-y`) 누락은 가장 흔하게 발생하는 교착의 원인 중 하나입니다. 이번 보완으로 60초 대기 지연이 영구히 소멸하여 코딩 루프 속도가 비약적으로 단축될 것입니다.
