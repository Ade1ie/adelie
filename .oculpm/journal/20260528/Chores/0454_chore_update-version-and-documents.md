---
schema_version: 1
type: chore
slug: update-version-and-documents
status: done
difficulty: low
created_at: "2026-05-28T04:54:00+09:00"
updated_at: "2026-05-28T04:54:00+09:00"
session_id: "manual-20260528-045400"
agent:
  id: antigravity
  version: "1.0"
language: ko
verified_by_user: false
files_touched:
  - path: docs/index.html
    op: update
  - path: README.md
    op: update
  - path: docs/adelie.rb
    op: update
related: []
tags: ["release", "chore", "documentation", "homebrew"]
---
[x] 0.3.5 릴리즈 버전 명시 및 문서/Homebrew 포뮬러 최신화

## 변경 요약
1. `docs/index.html` 내 내비게이션 바 배지 및 히어로 섹션 버전 표기를 `v0.3.5`로 최신화하여 최신 변경사항을 완전히 정렬했습니다.
2. `README.md`에서 패키지 버전 표기를 `v0.3.5`로 업데이트하고, 최근 테스트 구동 성공 결과를 반영하여 테스트 배지 개수를 `750 passing`으로 조정했습니다.
3. `docs/adelie.rb` Homebrew 포뮬러 파일의 배포 tarball URL을 `0.3.5`로 업데이트하고, `npm pack`을 통해 직접 산출해 낸 새로운 SHA-256 해시값 `4235e1c8b4fe9cda7eac22e9ac6aec340b7bafaafadd8e9fd336f665db72515f`를 연동했습니다.

## 검증
1. `git diff`를 통해 수정한 `docs/index.html`, `README.md`, `docs/adelie.rb` 파일들의 내용에 문법적 혹은 논리적 하자가 없음을 면밀히 육안 검수했습니다.
2. 로컬 가상환경에서 `pytest`를 활용하여 전체 750개 테스트 케이스가 100% 정상 통과함을 보장했습니다.
