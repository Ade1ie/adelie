---
description: How to publish a new version of adelie-ai to npm
---

# NPM Publish Workflow

// turbo-all

## Prerequisites

- npm login 완료 (`npm whoami` 로 확인)
- 모든 변경사항 커밋 완료

## Steps

### 1. Run all tests
```bash
cd c:\Users\bunhine0452\git\adelie
python -m pytest tests/ -v
```
- **모든 테스트 통과 필수** — 실패 시 publish 금지

### 2. Determine version bump

[Semantic Versioning](https://semver.org/) 을 따릅니다:

| Change Type | Bump | Example |
|---|---|---|
| Breaking changes (API 변경, 삭제) | **MAJOR** | 0.2.1 → 1.0.0 |
| New features (하위 호환) | **MINOR** | 0.2.1 → 0.3.0 |
| Bug fixes, docs, refactors | **PATCH** | 0.2.1 → 0.2.2 |

> **Note**: 0.x.x 동안은 MINOR를 feature, PATCH를 bugfix로 사용

### 3. Bump version in package.json

`package.json`의 `"version"` 필드를 수정합니다.
- **Single source of truth**: `adelie/__init__.py`가 `package.json`에서 버전을 읽으므로 `package.json`만 수정하면 됩니다.
- 다른 파일에 버전이 하드코딩되어 있지 않은지 확인: `grep -r "0\.2\.1" --include="*.py" --include="*.md"`

### 4. Update CHANGELOG.md

`CHANGELOG.md` 에 새 버전 섹션 추가:

```markdown
## [0.2.2] - 2026-03-22

### Added
- Feature description

### Fixed  
- Bug fix description

### Changed
- Change description
```

- [Keep a Changelog](https://keepachangelog.com/) 형식을 따릅니다.
- 카테고리: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`

### 5. Git commit & tag

```bash
git add -A
git commit -m "chore: release v0.2.2"
git tag v0.2.2
```

- 커밋 메시지 형식: `chore: release v{VERSION}`
- 태그 형식: `v{VERSION}`

### 6. Publish to npm

```bash
npm publish
```

- `npm publish --dry-run` 으로 먼저 확인 가능
- `package.json`의 `"files"` 필드가 필요한 파일만 포함하는지 확인
- **prepack** 스크립트가 자동으로 `__pycache__` 등을 정리합니다

### 7. Push to git

```bash
git push origin main --tags
```

## Checklist (publish 전 최종 확인)

- [ ] 모든 테스트 통과 (`python -m pytest tests/ -v`)
- [ ] Version bumped in `package.json`
- [ ] CHANGELOG.md 업데이트
- [ ] `npm publish --dry-run` 정상
- [ ] Git commit & tag 생성
- [ ] `npm publish` 실행
- [ ] `git push origin main --tags`
