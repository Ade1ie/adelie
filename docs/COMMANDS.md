# 🐧 Adelie — 전체 명령어 가이드

> Adelie CLI의 모든 명령어와 옵션을 상세히 설명하는 문서입니다.
>
> 🌐 [English Version →](./COMMANDS_EN.md)

---

## 목차

1. [설치 및 업데이트](#1-설치-및-업데이트)
2. [워크스페이스 관리](#2-워크스페이스-관리)
3. [AI 루프 실행](#3-ai-루프-실행)
4. [설정 관리](#4-설정-관리)
5. [런타임 설정 (Settings)](#5-런타임-설정-settings)
6. [모니터링 및 상태 확인](#6-모니터링-및-상태-확인)
7. [Knowledge Base (KB) 관리](#7-knowledge-base-kb-관리)
8. [프로젝트 관리](#8-프로젝트-관리)
9. [성능 메트릭](#9-성능-메트릭)
10. [Ollama 모델 관리](#10-ollama-모델-관리)
11. [Telegram 봇 연동](#11-telegram-봇-연동)
12. [프롬프트 관리](#12-프롬프트-관리)
13. [도구 레지스트리](#13-도구-레지스트리)
14. [커스텀 명령어](#14-커스텀-명령어)
15. [프로젝트 페이즈 (수명주기)](#15-프로젝트-페이즈-수명주기)
16. [환경 변수](#16-환경-변수)
17. [사용 시나리오별 예제](#17-사용-시나리오별-예제)

---

## 1. 설치 및 업데이트

### 사전 요구사항

| 항목 | 최소 버전 |
|------|----------|
| Python | 3.10+ |
| Node.js | 16+ |
| LLM 제공자 | Gemini API Key **또는** Ollama |

### 설치

```bash
# npm (권장)
npm install -g adelie-ai

# curl (macOS / Linux)
curl -fsSL https://raw.githubusercontent.com/Ade1ie/adelie/main/install.sh | bash

# PowerShell (Windows)
irm https://raw.githubusercontent.com/Ade1ie/adelie/main/install.ps1 | iex

# Homebrew (macOS / Linux)
brew tap Ade1ie/tap
brew install adelie

# 소스에서 설치
git clone https://github.com/Ade1ie/adelie.git
cd adelie && pip install -r requirements.txt
```

### 업데이트

```bash
# npm
npm install -g adelie-ai@latest

# Homebrew
brew upgrade adelie

# 버전 확인
adelie --version
```

---

## 2. 워크스페이스 관리

### `adelie init` — 워크스페이스 초기화

프로젝트 디렉토리에 `.adelie/` 폴더를 생성하고 Knowledge Base 구조를 초기화합니다.

```bash
adelie init                  # 현재 디렉토리
adelie init /path/to/project # 특정 디렉토리
adelie init --force          # 강제 재초기화
```

| 옵션 | 설명 |
|------|------|
| `[directory]` | 대상 디렉토리 (기본값: `.`) |
| `--force` | 이미 존재하는 `.adelie/` 재초기화 |

**초기화 시 자동 수행:**
- `.adelie/workspace/` 하위 6개 KB 카테고리 생성 (`skills/`, `dependencies/`, `errors/`, `logic/`, `exports/`, `maintenance/`)
- `.adelie/specs/` 폴더 생성, `config.json` 및 `.env` 템플릿 생성
- 기존 프로젝트 감지 (언어, 프레임워크) → 코드 발견 시 페이즈 `mid`로 자동 설정
- 글로벌 레지스트리 등록

### `adelie ws` — 워크스페이스 목록/관리

```bash
adelie ws               # 등록된 워크스페이스 목록
adelie ws remove <N>     # 워크스페이스 #N 제거
```

---

## 3. AI 루프 실행

### `adelie run` — AI 루프 시작

```bash
adelie run --goal "REST API 구축"          # 연속 루프
adelie run once --goal "코드 분석"          # 한 사이클만
adelie run ws 1                            # 워크스페이스 #1 재개
```

| 옵션 | 설명 |
|------|------|
| `--goal "텍스트"` | AI에게 전달할 고수준 목표 |
| `--once` | 한 사이클만 실행 후 종료 |
| `ws <N>` | 워크스페이스 #N에서 재개 |

**실행 순서:** Writer → Expert → Research → Coder Manager → Reviewer → Staging → Tester → Runner → Monitor → Phase Gates

---

## 4. 설정 관리

### `adelie config` — LLM 설정 조회/수정

LLM 프로바이더, 모델, API 키 등 핵심 설정을 관리합니다.

```bash
adelie config                              # 현재 설정 조회
adelie config --provider gemini            # Gemini로 전환
adelie config --provider ollama            # Ollama로 전환
adelie config --model gemini-2.5-flash     # 모델 변경
adelie config --api-key YOUR_KEY           # Gemini API 키
adelie config --ollama-url URL             # Ollama 서버 URL
adelie config --lang ko                    # 언어 변경
adelie config --sandbox docker             # 샌드박스 모드
adelie config --plan-mode true             # Plan Mode 활성화
```

| 옵션 | 설명 |
|------|------|
| `--provider` | `gemini` 또는 `ollama` |
| `--model` | 사용할 모델명 |
| `--api-key` | Gemini API 키 |
| `--ollama-url` | Ollama 서버 URL |
| `--lang` | 언어 (`ko`, `en`) |
| `--sandbox` | `none`, `seatbelt`, `docker` |
| `--plan-mode` | `true` 또는 `false` |

---

## 5. 런타임 설정 (Settings)

### `adelie settings` — 2계층 설정 관리

Global (`~/.adelie/settings.json`)과 Workspace (`.adelie/.env` + `config.json`)으로 나뉩니다.

```
 우선순위: Workspace > Global > Default
```

```bash
adelie settings                              # 전체 설정 보기
adelie settings --global                     # 글로벌 설정만 보기
adelie settings set dashboard false          # 워크스페이스 대시보드 비활성화
adelie settings set --global language en     # 글로벌 언어 설정
adelie settings reset dashboard.port         # 기본값으로 복원
```

| 서브커맨드 | 설명 |
|-----------|------|
| `show` (기본) | 모든 설정을 테이블로 표시 (소스 표시: workspace/global/default) |
| `set <key> <value>` | 설정 값 변경 |
| `reset <key>` | 기본값으로 복원 |

| 옵션 | 설명 |
|------|------|
| `--global` | 글로벌 설정 대상으로 지정 |

### 설정 항목

| Key | 기본값 | 설명 |
|-----|-------|------|
| `dashboard` | `true` | 대시보드 on/off |
| `dashboard.port` | `5042` | 대시보드 포트 |
| `loop.interval` | `30` | 루프 간격 (초) |
| `plan.mode` | `false` | Plan Mode (승인 후 실행) |
| `sandbox` | `none` | 샌드박스 (none/seatbelt/docker) |
| `mcp` | `true` | MCP 프로토콜 on/off |
| `browser.search` | `true` | 브라우저 검색 on/off |
| `browser.max_pages` | `3` | 검색 최대 페이지 |
| `fallback.models` | — | 폴백 모델 체인 |
| `fallback.cooldown` | `60` | 폴백 쿨다운 (초) |
| `language` | `ko` | 언어 (ko/en) |

---

## 6. 모니터링 및 상태 확인

### `adelie status` — 시스템 상태

```bash
adelie status
```

LLM 연결 상태, 루프 간격, 워크스페이스 경로, KB 파일 수를 표시합니다.

### `adelie inform` — AI 상태 리포트

```bash
adelie inform
adelie inform --goal "마이크로서비스 전환"
```

Inform AI를 호출하여 프로젝트 상태 리포트를 생성합니다. (`workspace/exports/status_report.md`에 저장)

### `adelie phase` — 프로젝트 페이즈

```bash
adelie phase                  # 현재 페이즈 확인
adelie phase set mid_1        # 페이즈 수동 변경
```

유효 값: `initial`, `mid`, `mid_1`, `mid_2`, `late`, `evolve`

---

## 7. Knowledge Base (KB) 관리

### `adelie kb` — KB 조회/관리

```bash
adelie kb                    # 카테고리별 파일 수
adelie kb --clear-errors     # 에러 파일만 삭제
adelie kb --reset            # 전체 KB 초기화 (확인 필요)
```

### `adelie scan` — 코드베이스 스캔

```bash
adelie scan                          # 현재 디렉토리 스캔
adelie scan --directory /path/to/src # 특정 디렉토리
```

### `adelie spec` — 명세 파일 로드

```bash
adelie spec load spec.md                       # MD 로드
adelie spec load architecture.pdf              # PDF 자동 변환
adelie spec load requirements.docx             # DOCX 자동 변환
adelie spec load api.pdf --category dependencies
adelie spec list                               # 로드된 스펙 목록
adelie spec remove spec_my_spec                # 스펙 삭제
```

지원 형식: `.md`, `.pdf`, `.docx`

---

## 8. 프로젝트 관리

### `adelie goal` — 목표 관리

```bash
adelie goal                              # 현재 목표 조회
adelie goal set "실시간 채팅 앱 구축"     # 목표 설정
```

### `adelie feedback` — 피드백 전송

```bash
adelie feedback "인증 기능 먼저 구현"                 # 일반 피드백
adelie feedback "프로덕션 배포 중단" --priority critical  # 긴급 피드백
adelie feedback --list                                # 대기 중 피드백 조회
```

### `adelie research` — 웹 리서치

```bash
adelie research "FastAPI WebSocket 구현"
adelie research "Redis 캐싱" --context "고성능 API" --category skills
adelie research --list
```

### `adelie git` — Git 상태

```bash
adelie git              # Git 상태 + 최근 5개 커밋
```

---

## 9. 성능 메트릭

### `adelie metrics` — 사이클 메트릭

```bash
adelie metrics                   # 최근 사이클 메트릭
adelie metrics --agents          # 에이전트별 토큰 사용량
adelie metrics --trend           # 성능 트렌드
adelie metrics --last 50         # 최근 50 사이클
adelie metrics --since 24h       # 최근 24시간
```

| 옵션 | 설명 |
|------|------|
| `--agents` | 에이전트별 토큰 사용량 표시 |
| `--trend` | 성능 트렌드 (시간, 토큰, 점수) |
| `--last N` | 최근 N 사이클만 표시 (기본: 20) |
| `--since` | 시간 필터 (`1h`, `6h`, `24h`, `48h`, `7d`) |

---

## 10. Ollama 모델 관리

```bash
adelie ollama list               # 설치된 모델 목록
adelie ollama pull gemma3:12b    # 모델 다운로드
adelie ollama remove gemma3:12b  # 모델 삭제
adelie ollama run                # 대화형 채팅 (현재 모델)
adelie ollama run gemma3:12b     # 특정 모델로 채팅
```

---

## 11. Telegram 봇 연동

```bash
adelie telegram setup            # 봇 토큰 설정 (대화형)
adelie telegram start            # 봇 시작
adelie telegram start --ws 1     # 워크스페이스 #1 바인딩
adelie telegram start --token T  # 토큰 직접 지정
```

---

## 12. 프롬프트 관리

### `adelie prompts` — 에이전트 시스템 프롬프트

```bash
adelie prompts                   # 사용 가능한 프롬프트 목록
adelie prompts export            # 기본 프롬프트를 .adelie/prompts/로 내보내기
adelie prompts reset             # 커스텀 프롬프트 삭제 (기본으로 복원)
```

내보낸 프롬프트 파일을 수정하면 AI 에이전트가 자동으로 커스텀 프롬프트를 사용합니다.

---

## 13. 도구 레지스트리

### `adelie tools` — 활성 도구 관리

```bash
adelie tools                     # 사용 가능한 도구 목록
adelie tools enable <tool>       # 도구 활성화
adelie tools disable <tool>      # 도구 비활성화
```

---

## 14. 커스텀 명령어

### `adelie commands` — 사용자 정의 명령어

`.adelie/commands/` 디렉토리에 커스텀 스크립트를 배치하면 자동으로 인식됩니다.

```bash
adelie commands                  # 커스텀 명령어 목록
```

---

## 15. 프로젝트 페이즈 (수명주기)

```
🌱 INITIAL ──▶ 🔨 MID ──▶ 🚀 MID_1 ──▶ ⚡ MID_2 ──▶ 🛡️ LATE ──▶ 🧬 EVOLVE
 기획/문서화     구현/코딩    실행/테스트    안정화/최적화   유지보수     자율 발전
```

| 페이즈 | 값 | 코더 레이어 | 목표 |
|--------|-----|-----------|------|
| 🌱 초기 | `initial` | — | 비전 문서화, 아키텍처 설계 |
| 🔨 중기 | `mid` | L0 | 구현, 테스트, 코드 고도화 |
| 🚀 중기1 | `mid_1` | L0-1 | 실행, 로드맵 체크 |
| ⚡ 중기2 | `mid_2` | L0-2 | 안정화, 최적화, 배포 |
| 🛡️ 후기 | `late` | L0-2 | 유지보수, 새 기능 |
| 🧬 발전 | `evolve` | L0-2 | 자율 발전 |

---

## 16. 환경 변수

`.adelie/.env` 파일에서 설정합니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_PROVIDER` | `gemini` | `gemini` 또는 `ollama` |
| `GEMINI_API_KEY` | — | Gemini API 키 |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini 모델명 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama 모델명 |
| `FALLBACK_MODELS` | — | 폴백 체인 (`gemini:flash,ollama:llama3.2`) |
| `FALLBACK_COOLDOWN_SECONDS` | `60` | 쿨다운 (초) |
| `DASHBOARD_ENABLED` | `true` | 대시보드 on/off |
| `DASHBOARD_PORT` | `5042` | 대시보드 포트 |
| `PLAN_MODE` | `false` | Plan Mode |
| `SANDBOX_MODE` | `none` | 샌드박스 모드 |
| `MCP_ENABLED` | `true` | MCP 프로토콜 |
| `BROWSER_SEARCH_ENABLED` | `true` | 브라우저 검색 |

---

## 17. 사용 시나리오별 예제

### 새 프로젝트 시작 (Gemini)

```bash
mkdir my-app && cd my-app
adelie init
adelie config --provider gemini --api-key YOUR_KEY
adelie goal set "SaaS 프로젝트 관리 앱 구축"
adelie run --goal "SaaS 프로젝트 관리 앱 구축"
```

### 기존 프로젝트 (Ollama)

```bash
cd /path/to/project
adelie init
adelie config --provider ollama --model gemma3:12b
adelie scan
adelie run once --goal "코드 분석 및 개선점 도출"
```

### 설정 관리

```bash
# 이 프로젝트만 대시보드 끄기
adelie settings set dashboard false

# 모든 프로젝트에 기본 언어 영어
adelie settings set --global language en

# 확인
adelie settings
```

### 여러 워크스페이스

```bash
cd ~/projects/frontend && adelie init
cd ~/projects/backend && adelie init
adelie ws
adelie run ws 1
```

---

## 빠른 참조

```
┌──────────────────────────────────────────────────────────────┐
│                   🐧 Adelie Quick Reference                  │
├──────────────────────────────────────────────────────────────┤
│  시작       adelie init / config / run --goal "..."          │
│  설정       adelie settings [set/reset] [--global]           │
│  상태       adelie status / phase / kb / git / metrics       │
│  프로젝트   adelie goal set / feedback / research / scan     │
│  모델       adelie ollama list / pull / run                  │
│  워크스페이스  adelie ws / run ws <N>                          │
│  도구       adelie tools / prompts / commands                │
│  도움말     adelie help / --version                          │
└──────────────────────────────────────────────────────────────┘
```

---

<p align="center">
  Made with 🐧 by Adelie
</p>
