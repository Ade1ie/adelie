---
schema_version: 1
type: bug
slug: monorepo-scaffolding-check-loop-fix
status: done
difficulty: medium
created_at: "2026-05-28T12:33:00+09:00"
updated_at: "2026-05-28T12:33:15+09:00"
session_id: "manual-20260528-123300"
agent:
  id: antigravity
  version: "3.5"
language: ko
verified_by_user: false
files_touched:
  - path: adelie/agents/expert_ai.py
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
related: []
tags: ["scaffolding", "monorepo", "expert-ai", "loop-detection"]
---

[x] 모노레포 워크스페이스 스캐폴딩 무한 루프 감지 오류 수정 및 v0.3.7 릴리즈

## 발생 원인
Adelie의 Expert AI 의사결정 프로세스 중 프로젝트 진입 파일 존재 여부를 체크하는 `_get_scaffolding_need()` 함수가 모노레포 구조(예: nested `client` / `server` 폴더)를 인지하지 못하는 결함이 있었습니다. 
Vite/React 프로젝트에서 `package.json`은 프로젝트 루트에 있지만, 실제 진입점인 `index.html`, `vite.config.ts`, `src/main.tsx` 등은 `client` 하위 폴더 내에 분리되어 위치합니다. 하지만 기존 로직은 프로젝트 루트에서만 이 파일들을 찾았기 때문에 매 루프마다 **"스캐폴딩 파일이 유실되었습니다"**라는 경고(Checks)를 생성했고, Expert AI는 이에 대응하느라 매 사이클마다 불필요한 `project_scaffolding` Coder 태스크를 반복Dispatch하면서 13루프 동안 아무 진전 없이 루프 교착상태(Stagnation Loop)에 빠졌습니다.

## 해결 방법
1. **모노레포 인지형 스캐폴딩 검사 구축**: `expert_ai.py`의 `_get_scaffolding_need()` 함수를 리팩토링했습니다. 
   - 루트 `package.json`의 `workspaces` 필드 또는 프로젝트 내 `client`, `server`, `frontend`, `backend` 하위 디렉터리 존재 여부를 검색하여 nested 워크스페이스를 자동 감지하도록 설계했습니다.
   - 각 하위 워크스페이스 타겟 디렉터리를 돌며 해당 프레임워크/언어별 스캐폴딩 파일(예: `client/index.html`, `server/tsconfig.json` 등)을 검증하도록 보완했습니다.
   - 모든 워크스페이스에 진입 파일이 존재하면 검사 경고를 생략(`""` 리턴)하여 Expert AI가 막힘없이 기능 개발 단계로 진행할 수 있도록 해결했습니다.
2. **릴리즈 패키지 버전 범프 (v0.3.7)**:
   - `package.json` 및 `adelie/__init__.py`에서 버전을 `0.3.7`로 올렸습니다.
   - `CHANGELOG.md`, `docs/index.html`(Changelog 항목 추가 및 버전 배지 업데이트), `docs/adelie.rb` Homebrew 포뮬러 내 tarball URL을 `0.3.7` 기준으로 갱신했습니다.

## 검증
1. **단위 및 전체 테스트 자동화 검증**:
   - `pytest tests/test_scaffolding.py tests/test_expert_ai.py`를 실행하여 11개 핵심 테스트 통과 완료.
   - `pytest` 전체 통합 테스트 실행 결과: **750 passed, 3 skipped, 2 warnings** 완료.
2. **수동 모의 검증**:
   - 테스트용 모노레포 프로젝트인 `/Users/kimhyunbin/Desktop/adelie_test/test01` 폴더 구조를 목(Mock)하여 수동 검증 스크립트 실행.
   - 기존의 유실 파일 에러 대신 `SUCCESS: No scaffolding needed!` 메세지와 함께 정상 통과함을 최종 입증했습니다.

## 메모
* 본 패치로 인해 모노레포를 활용하는 더 큰 하이브리드 프로젝트들에서도 Adelie가 중간에 스캐폴딩 교착상태에 걸리지 않고 원활하게 코딩을 진행할 수 있게 되었습니다.
