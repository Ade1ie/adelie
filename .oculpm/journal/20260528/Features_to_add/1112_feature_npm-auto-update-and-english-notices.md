---
schema_version: 1
type: feature
slug: npm-auto-update-and-english-notices
status: done
difficulty: low
created_at: "2026-05-28T11:12:00+09:00"
session_id: "manual-20260528-111200"
agent:
  id: antigravity
  version: "1.0"
language: ko
verified_by_user: false
files_touched:
  - path: adelie/cli.py
    op: update
    bytes_added: 650
    bytes_removed: 50
  - path: adelie/interactive.py
    op: update
    bytes_added: 480
    bytes_removed: 20
  - path: adelie/updater.py
    op: update
    bytes_added: 1200
    bytes_removed: 1200
  - path: adelie/__init__.py
    op: update
    bytes_added: 6
    bytes_removed: 6
  - path: package.json
    op: update
    bytes_added: 1
    bytes_removed: 1
  - path: CHANGELOG.md
    op: update
    bytes_added: 600
    bytes_removed: 0
  - path: docs/index.html
    op: update
    bytes_added: 900
    bytes_removed: 0
  - path: docs/adelie.rb
    op: update
    bytes_added: 1
    bytes_removed: 1
related: []
tags: ["cli", "updater", "localization", "release"]
---

[x] adelie CLI 자율 업데이트 기능 추가 및 전체 영어 현지화 작업 완료

## 추가 기능
- **`--update` 글로벌 옵션**: npm 패키지 레지스트리에서 최신 버전을 조회하여 비교한 뒤, 신규 버전이 존재하면 자동으로 글로벌 업그레이드 명령어(`npm install -g adelie-ai@latest`)를 수행해 자율적으로 버전을 동기화합니다.
- **시작 화면 및 REPL 백그라운드 버전 체크**:
  - `adelie` 기본 실행(스플래시 화면) 시 1.0초의 타임아웃을 두고 최신 버전을 탐색하여 펭귄 알림 메세지를 노출합니다.
  - `adelie run` 실행 시 대화형 기동에 방해를 주지 않도록 데몬 스레드에서 비동기 버전 확인을 수행합니다.
- **영어 현지화**: 글로벌 유저 배포를 고려하여 모든 버전 업그레이드 체크 피드백 및 안내 이모지 알림 텍스트를 한글에서 영어로 수정하였습니다.
- **버전 릴리즈 준비**: 배포를 위해 `package.json`, `__init__.py`, `CHANGELOG.md`, `docs/index.html`, `docs/adelie.rb` 파일의 버전을 `0.3.6`으로 일괄 마이그레이션했습니다.

## 동작 흐름
1. `adelie --update` 실행 시 `check_for_update()` -> `do_update()` 호출을 통해 CLI 환경에서 동기 방식으로 최신화.
2. 스플래시 기동 및 `AdelieApp.run()` REPL 시작 시 백그라운드로 버전 체크 스레드 기동하여 귀여운 펭귄 이모티콘과 함께 영어 노티 출력.

## 검증
- `python -m adelie.cli --update`를 통해 `Checking for updates... You are already running the latest version! (v0.3.5)` 정상 출력을 확인했습니다.
- 임의의 하위 버전 모의 지정을 통해 스플래시 화면에 `Brrr... 🐧 A new version is available! Run adelie --update to update now ✨`와 같이 귀엽고 매끄러운 영문 알림이 노출되는 것을 확인했습니다.
