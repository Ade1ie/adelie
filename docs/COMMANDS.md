# 🐧 Adelie — 전체 명령어 가이드

> Adelie CLI의 모든 명령어와 옵션을 상세히 설명하는 문서입니다.

---

## 목차

1. [설치 및 초기 설정](#1-설치-및-초기-설정)
2. [워크스페이스 관리](#2-워크스페이스-관리)
3. [AI 루프 실행](#3-ai-루프-실행)
4. [설정 관리](#4-설정-관리)
5. [모니터링 및 상태 확인](#5-모니터링-및-상태-확인)
6. [Knowledge Base (KB) 관리](#6-knowledge-base-kb-관리)
7. [프로젝트 관리](#7-프로젝트-관리)
8. [Ollama 모델 관리](#8-ollama-모델-관리)
9. [Telegram 봇 연동](#9-telegram-봇-연동)
10. [프로젝트 페이즈 (수명주기)](#10-프로젝트-페이즈-수명주기)
11. [환경 변수](#11-환경-변수)
12. [사용 시나리오별 예제](#12-사용-시나리오별-예제)

---

## 1. 설치 및 초기 설정

### 사전 요구사항

| 항목 | 최소 버전 |
|------|----------|
| Python | 3.10+ |
| Node.js | 16+ |
| LLM 제공자 | Gemini API Key **또는** Ollama 로컬 서버 |

### 설치

```bash
# 저장소 클론
git clone https://github.com/your-username/Adelie.git
cd Adelie

# Python 의존성 설치
pip install -r requirements.txt

# CLI 글로벌 설치 (Node.js 래퍼)
npm install -g .
```

### Python 의존성 목록

| 패키지 | 용도 |
|--------|------|
| `google-genai>=0.5.0` | Gemini LLM 클라이언트 |
| `python-dotenv>=1.0.0` | `.env` 파일 로딩 |
| `rich>=13.0.0` | CLI 터미널 UI (테이블, 패널, 컬러) |
| `requests>=2.28.0` | Ollama HTTP API 통신 |
| `python-telegram-bot>=20.0` | Telegram 봇 연동 |
| `pytest>=7.0.0` | 테스트 프레임워크 |

---

## 2. 워크스페이스 관리

### `adelie init` — 워크스페이스 초기화

프로젝트 디렉토리에 `.adelie/` 폴더를 생성하고 Knowledge Base 구조를 초기화합니다.

```bash
# 현재 디렉토리에 초기화
adelie init

# 특정 디렉토리에 초기화
adelie init /path/to/project

# 기존 워크스페이스를 강제 재초기화
adelie init --force
```

| 옵션 | 설명 |
|------|------|
| `[directory]` | 대상 디렉토리 (기본값: 현재 디렉토리 `.`) |
| `--force` | 이미 존재하는 `.adelie/` 를 재초기화 |

**초기화 시 자동 수행되는 작업:**

1. `.adelie/workspace/` 하위에 6개 KB 카테고리 폴더 생성
   - `skills/`, `dependencies/`, `errors/`, `logic/`, `exports/`, `maintenance/`
2. `.adelie/specs/` 폴더 생성 (명세 파일 자동 인식용)
3. `index.json` 파일 생성 (KB 인덱스)
4. `.adelie/config.json` 기본 설정 생성
5. 기존 프로젝트 감지 (언어, 프레임워크 자동 탐지)
   - 코드가 발견되면 페이즈를 `mid`로 자동 설정
6. 글로벌 워크스페이스 레지스트리에 등록

> **📄 명세 자동 인식:** `.adelie/specs/` 폴더에 MD, PDF, DOCX 파일을 넣어두면 `adelie run` 시 자동으로 KB에 로드됩니다. 파일이 수정되면 다음 실행 시 자동 재동기화됩니다.

**지원하는 프로젝트 자동 감지:**

| 마커 파일 | 감지 언어 | 감지 프레임워크 |
|-----------|----------|---------------|
| `package.json` | JavaScript | Node.js, React, Vue, Svelte, Next.js 등 |
| `requirements.txt` / `pyproject.toml` / `setup.py` | Python | — |
| `Cargo.toml` | Rust | — |
| `go.mod` | Go | — |
| `pom.xml` | Java | Maven |
| `build.gradle` | Java | Gradle |
| `Gemfile` | Ruby | Rails |
| `composer.json` | PHP | Laravel |

---

### `adelie ws` — 워크스페이스 목록/관리

```bash
# 등록된 모든 워크스페이스 목록
adelie ws

# 특정 워크스페이스 삭제
adelie ws remove <번호>
```

| 서브커맨드 | 설명 |
|-----------|------|
| `list` (기본) | 등록된 워크스페이스 테이블 표시 (번호, 경로, 마지막 목표, 마지막 사용일) |
| `remove <N>` | 워크스페이스 #N 을 레지스트리에서 제거 (`.adelie/` 데이터 삭제 여부 추가 확인) |

---

## 3. AI 루프 실행

### `adelie run` — AI 루프 시작

자율 AI 루프를 시작합니다. 모든 에이전트가 순차적으로 실행됩니다.

```bash
# 목표를 지정하여 루프 시작
adelie run --goal "REST API for task management 구축"

# 특정 워크스페이스에서 루프 재개
adelie run ws 1

# 정확히 한 사이클만 실행 후 종료
adelie run once --goal "코드베이스 분석 및 문서화"

# 한 사이클 실행 (once 플래그)
adelie run --once --goal "현재 상태 점검"
```

| 옵션 | 설명 |
|------|------|
| `--goal "텍스트"` | AI 에이전트들에게 전달할 고수준 목표 (기본값: `"Operate and improve the Adelie autonomous AI system"`) |
| `--once` | 정확히 한 사이클만 실행 후 종료 |
| `ws <N>` | 워크스페이스 #N 에서 루프 재개 (이전 목표 자동 로드) |
| `once` | `--once`와 동일 (서브커맨드 형태) |

**한 사이클의 실행 순서:**

```
Writer AI → Expert AI → Research AI → Coder Manager → Reviewer AI
  → Staging → Tester AI → Runner AI → Monitor AI → Phase Gates
```

---

## 4. 설정 관리

### `adelie config` — 설정 조회/수정

```bash
# 현재 설정 조회
adelie config

# LLM 제공자 변경
adelie config --provider gemini
adelie config --provider ollama

# 모델 변경 (현재 provider에 따라 자동 적용)
adelie config --model gemini-2.5-flash     # Gemini 사용 시
adelie config --model gemma3:12b           # Ollama 사용 시

# Gemini API 키 설정
adelie config --api-key YOUR_GEMINI_API_KEY

# Ollama 서버 URL 변경
adelie config --ollama-url http://192.168.1.100:11434

# 루프 간격 변경 (초 단위)
adelie config --interval 60
```

| 옵션 | 설명 | 예시 |
|------|------|------|
| (없음) | 현재 설정을 테이블로 표시 | `adelie config` |
| `--provider` | LLM 제공자 설정 | `gemini` 또는 `ollama` |
| `--model` | 사용할 모델명 | `gemini-2.5-flash`, `gemma3:12b` |
| `--api-key` | Gemini API 키 | `AIzaSy...` |
| `--ollama-url` | Ollama 서버 URL | `http://localhost:11434` |
| `--interval` | 루프 사이클 간격 (초) | `30`, `60`, `120` |

> **참고:** 설정은 `.adelie/config.json`에 저장됩니다. `.env` 파일의 환경 변수보다 config.json이 우선합니다.

---

## 5. 모니터링 및 상태 확인

### `adelie status` — 시스템 상태 확인

```bash
adelie status
```

현재 시스템의 전체 상태를 표시합니다:

- LLM 제공자 정보 및 연결 상태
- 루프 간격
- 워크스페이스 경로
- KB 파일 수 (카테고리별)
- Gemini API 키 설정 여부 또는 Ollama 연결 상태

---

### `adelie inform` — 프로젝트 상태 리포트 생성

```bash
# 기본 리포트 생성
adelie inform

# 목표 컨텍스트를 포함한 리포트
adelie inform --goal "마이크로서비스 아키텍처 전환"
```

| 옵션 | 설명 |
|------|------|
| `--goal` | 리포트에 포함할 프로젝트 목표 컨텍스트 |

Inform AI를 호출하여 프로젝트 현재 상태를 분석하고 마크다운 리포트를 생성합니다.  
리포트는 `workspace/exports/status_report.md`에 저장됩니다.

---

### `adelie phase` — 프로젝트 페이즈 관리

```bash
# 현재 페이즈 확인 (전체 라이프사이클 시각화)
adelie phase

# 페이즈 수동 설정
adelie phase set mid
adelie phase set mid_1
adelie phase set late
```

| 서브커맨드 | 설명 |
|-----------|------|
| `show` (기본) | 현재 페이즈를 라이프사이클과 함께 표시 |
| `set <phase>` | 페이즈 수동 변경 |

유효한 페이즈 값: `initial`, `mid`, `mid_1`, `mid_2`, `late`, `evolve`

---

## 6. Knowledge Base (KB) 관리

### `adelie kb` — KB 조회/관리

```bash
# KB 파일 수 카테고리별 조회
adelie kb

# 에러 파일만 삭제
adelie kb --clear-errors

# KB 전체 초기화 (⚠️ 위험: 모든 KB 문서 삭제)
adelie kb --reset
```

| 옵션 | 설명 |
|------|------|
| (없음) | 카테고리별 파일 수를 테이블로 표시 |
| `--clear-errors` | `errors/` 카테고리의 파일만 삭제 |
| `--reset` | 전체 KB 초기화 (확인 입력 필요: `yes`) |

**KB 카테고리 구조:**

```
.adelie/workspace/
├── skills/          # How-to 가이드, 절차, 능력
├── dependencies/    # 외부 API, 라이브러리, 서비스 문서
├── errors/          # 알려진 에러, 원인, 복구 방법
├── logic/           # 의사결정 패턴, 계획 문서
├── exports/         # 리포트, 로드맵, 산출물
└── maintenance/     # 시스템 상태, 유지보수 업데이트
```

---

### `adelie scan` — 기존 코드베이스 스캔

기존 프로젝트의 소스코드를 분석하여 KB 문서를 자동 생성합니다.

```bash
# 현재 디렉토리 스캔
adelie scan

# 특정 디렉토리 스캔
adelie scan --directory /path/to/project
```

| 옵션 | 설명 |
|------|------|
| `--directory` | 스캔할 프로젝트 디렉토리 (기본값: `.`) |

Scanner AI가 소스코드를 분석하여 아키텍처, 의존성, 패턴 등을 KB에 문서화합니다.

---

### `adelie spec` — 명세 파일 로드 (MD, PDF, DOCX)

프로젝트 명세 파일을 KB에 로드합니다. PDF와 DOCX 파일은 자동으로 Markdown으로 변환됩니다.

```bash
# MD 파일 로드
adelie spec load spec.md

# PDF 파일 로드
adelie spec load architecture.pdf

# DOCX 파일 로드
adelie spec load requirements.docx

# KB 카테고리 지정 (기본: logic)
adelie spec load api_spec.pdf --category dependencies

# 로드된 스펙 목록
adelie spec list

# 스펙 삭제
adelie spec remove spec_my_spec
```

| 서브커맨드 | 설명 |
|-----------|------|
| `load <file>` | 명세 파일을 KB에 로드 (자동 변환) |
| `list` (기본) | 로드된 명세 파일 목록 표시 |
| `remove <name>` | KB에서 명세 파일 삭제 |

| 옵션 | 설명 |
|------|------|
| `--category` | KB 저장 카테고리: `logic` (기본), `dependencies`, `skills`, `errors`, `maintenance` |

**지원 파일 형식:**

| 확장자 | 변환 방식 |
|--------|----------|
| `.md` | 그대로 복사 |
| `.pdf` | 페이지별 텍스트 추출 → Markdown 구조화 |
| `.docx` / `.doc` | 제목/본문/테이블 → Markdown 변환 |

> **참고:** 로드된 스펙 파일은 `.adelie/workspace/{category}/spec_*.md` 형식으로 저장됩니다. AI 에이전트들이 자동으로 참조합니다.

---

## 7. 프로젝트 관리

### `adelie goal` — 프로젝트 목표 관리

```bash
# 현재 목표 조회
adelie goal

# 목표 설정 (KB의 logic/project_goal.md에 저장)
adelie goal set "실시간 채팅 앱 구축 with WebSocket"
```

| 서브커맨드 | 설명 |
|-----------|------|
| `show` (기본) | 현재 프로젝트 목표 표시 |
| `set "텍스트"` | 프로젝트 목표 설정 (Expert AI와 Writer AI가 자동 참조) |

---

### `adelie feedback` — AI 루프에 피드백 전송

실행 중인 AI 루프에 사용자 피드백을 주입합니다.

```bash
# 피드백 전송
adelie feedback "인증 기능을 먼저 구현해주세요"

# 높은 우선순위 피드백
adelie feedback "프로덕션 배포 중단하세요" --priority critical

# 대기 중인 피드백 조회
adelie feedback --list
```

| 옵션 | 설명 |
|------|------|
| `"메시지"` | 피드백 내용 |
| `--priority` | 우선순위: `low`, `normal` (기본), `high`, `critical` |
| `--list` | 대기 중인 피드백 목록 표시 |

---

### `adelie research` — 웹 리서치

Gemini Search를 활용하여 웹에서 정보를 검색하고 KB에 저장합니다.

```bash
# 특정 주제 리서치
adelie research "FastAPI WebSocket 구현 방법"

# 컨텍스트와 카테고리 지정
adelie research "Redis 캐싱 전략" --context "고성능 API 최적화" --category skills

# 최근 리서치 결과 조회
adelie research --list
```

| 옵션 | 설명 |
|------|------|
| `"주제"` | 검색할 주제/쿼리 |
| `--context` | 리서치가 필요한 맥락 설명 |
| `--category` | KB 저장 카테고리: `dependencies` (기본), `skills`, `logic`, `errors`, `maintenance` |
| `--list` | 최근 5개 리서치 결과 표시 |

---

### `adelie git` — Git 상태 확인

```bash
adelie git
```

현재 프로젝트의 Git 상태와 최근 5개 커밋을 표시합니다:
- 워킹 트리 변경사항
- 변경된 파일 목록
- 최근 커밋 해시 및 메시지

---

## 8. Ollama 모델 관리

로컬 Ollama 서버의 모델을 관리합니다.

### `adelie ollama list` — 설치된 모델 목록

```bash
adelie ollama list
```

설치된 모든 Ollama 모델의 이름, 크기, 수정일을 표시합니다. 현재 활성 모델에 `← active` 마커가 표시됩니다.

### `adelie ollama pull` — 모델 다운로드

```bash
adelie ollama pull gemma3:12b
adelie ollama pull llama3.2
adelie ollama pull codellama
```

### `adelie ollama remove` — 모델 삭제

```bash
adelie ollama remove gemma3:12b
```

### `adelie ollama run` — 대화형 채팅

```bash
# 현재 설정된 모델로 채팅
adelie ollama run

# 특정 모델로 채팅
adelie ollama run gemma3:12b
```

---

## 9. Telegram 봇 연동

Adelie를 Telegram 봇으로 연동하여 원격으로 모니터링/제어할 수 있습니다.

### `adelie telegram setup` — 봇 토큰 설정

```bash
adelie telegram setup
```

대화형으로 Telegram 봇 토큰을 입력받아 저장합니다.

**설정 순서:**
1. Telegram에서 `@BotFather` 검색
2. `/newbot` 명령으로 봇 생성
3. 발급된 토큰을 입력

### `adelie telegram start` — 봇 시작

```bash
# 현재 워크스페이스의 봇 시작
adelie telegram start

# 특정 워크스페이스 바인딩
adelie telegram start --ws 1

# 토큰 직접 지정
adelie telegram start --token YOUR_BOT_TOKEN
```

| 옵션 | 설명 |
|------|------|
| `--ws <N>` | 워크스페이스 번호 바인딩 |
| `--token` | 봇 토큰 직접 지정 (저장된 토큰 오버라이드) |

---

## 10. 프로젝트 페이즈 (수명주기)

Adelie는 프로젝트를 6단계의 페이즈로 관리합니다. 각 페이즈는 AI 에이전트의 행동과 활성화되는 코더 레이어를 결정합니다.

```
🌱 INITIAL ──▶ 🔨 MID ──▶ 🚀 MID_1 ──▶ ⚡ MID_2 ──▶ 🛡️ LATE ──▶ 🧬 EVOLVE
 기획/문서화     구현/코딩    실행/테스트    안정화/최적화   유지보수     자율 발전
```

| 페이즈 | 값 | 활성 코더 레이어 | 목표 | 전환 조건 |
|--------|-----|-----------------|------|----------|
| 🌱 초기 | `initial` | 없음 | 비전 문서화, 아키텍처 설계, 로드맵 작성 | roadmap.md 존재, 아키텍처 문서화, KB 파일 5개 이상 |
| 🔨 중기 | `mid` | Layer 0 (기능) | 프로덕션 구현, 테스트, 코드 고도화 | 핵심 기능 구현, 기본 테스트 통과 |
| 🚀 중기 1기 | `mid_1` | Layer 0-1 (기능+커넥터) | 실행, 로드맵 체크, 중복 방지 | 테스트 통과, 로드맵 업데이트, 운영 가이드 |
| ⚡ 중기 2기 | `mid_2` | Layer 0-2 (전체) | 안정화, 최적화, 배포 | 배포 완료, 안정화, 수익화 전략 |
| 🛡️ 후기 | `late` | Layer 0-2 (전체) | 유지보수, 새 기능, 로드맵 확장 | 안정적 운영, 기능 제안서 축적 |
| 🧬 자율 발전 | `evolve` | Layer 0-2 (전체) | AI가 자율적으로 프로덕트 발전 | 이전 페이즈로 순환 가능 |

---

## 11. 환경 변수

`.env.example`을 `.env`로 복사하여 설정합니다.

```bash
cp .env.example .env
```

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LLM_PROVIDER` | `gemini` | LLM 제공자 (`gemini` 또는 `ollama`) |
| `GEMINI_API_KEY` | — | Gemini API 키 (Gemini 사용 시 필수) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini 모델명 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 서버 URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama 모델명 |
| `FALLBACK_MODELS` | — | 모델 폴백 체인 (쉼표 구분, 예: `gemini:gemini-2.5-flash,ollama:llama3.2`) |
| `FALLBACK_COOLDOWN_SECONDS` | `60` | 실패한 모델 재시도 전 쿨다운 (초) |
| `LOOP_INTERVAL_SECONDS` | `30` | 루프 사이클 간격 (초) |
| `WORKSPACE_PATH` | `./workspace` | Knowledge Base 경로 |

**폴백 모델 설정 예시:**

```env
# 첫 번째 모델이 실패하면 순서대로 다음 모델 시도
FALLBACK_MODELS=gemini:gemini-2.5-flash,gemini:gemini-2.0-flash,ollama:llama3.2

# 60초 쿨다운 후 실패한 모델 재시도
FALLBACK_COOLDOWN_SECONDS=60
```

---

## 12. 사용 시나리오별 예제

### 시나리오 1: 새 프로젝트 시작 (Gemini 사용)

```bash
# 1. 프로젝트 디렉토리 생성
mkdir my-saas-app && cd my-saas-app

# 2. Adelie 워크스페이스 초기화
adelie init

# 3. Gemini 설정
adelie config --provider gemini
adelie config --api-key YOUR_API_KEY
adelie config --model gemini-2.5-flash

# 4. 프로젝트 목표 설정
adelie goal set "SaaS 형태의 프로젝트 관리 웹 앱 구축"

# 5. AI 루프 시작
adelie run --goal "SaaS 프로젝트 관리 앱 구축"

# 6. (별도 터미널) 진행 중 피드백 전송
adelie feedback "인증은 JWT 기반으로 구현해주세요" --priority high

# 7. 상태 확인
adelie status
adelie phase
adelie kb
```

### 시나리오 2: 기존 프로젝트에 적용 (Ollama 사용)

```bash
# 1. 기존 프로젝트로 이동
cd /path/to/existing-project

# 2. 워크스페이스 초기화 (기존 코드 자동 감지)
adelie init

# 3. Ollama 설정
adelie config --provider ollama
adelie config --model gemma3:12b

# 4. 기존 코드베이스 스캔 (KB 문서 자동 생성)
adelie scan

# 5. KB 확인
adelie kb

# 6. 한 사이클만 실행하여 분석
adelie run once --goal "기존 코드베이스 분석 및 개선점 도출"
```

### 시나리오 3: 여러 워크스페이스 운영

```bash
# 각 프로젝트에서 초기화
cd ~/projects/frontend-app && adelie init
cd ~/projects/backend-api && adelie init

# 워크스페이스 목록 확인
adelie ws

# 특정 워크스페이스에서 루프 실행
adelie run ws 1  # frontend-app
adelie run ws 2  # backend-api

# 워크스페이스 제거
adelie ws remove 2
```

### 시나리오 4: 웹 리서치 활용

```bash
# 특정 기술 리서치
adelie research "GraphQL vs REST API 비교 분석" --category logic

# 의존성 조사
adelie research "Node.js ORM 라이브러리 비교" --context "PostgreSQL 기반 백엔드" --category dependencies

# 에러 해결을 위한 리서치
adelie research "CORS preflight request 403 에러 해결" --category errors

# 리서치 이력 확인
adelie research --list
```

### 시나리오 5: Telegram으로 원격 모니터링

```bash
# 1. 봇 설정
adelie telegram setup

# 2. 봇 시작 (워크스페이스 바인딩)
adelie telegram start --ws 1
```

---

## 빠른 참조 (Cheat Sheet)

```
┌─────────────────────────────────────────────────────────────────┐
│                    🐧 Adelie Quick Reference                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  시작하기                                                        │
│    adelie init                    워크스페이스 초기화              │
│    adelie config --provider ...   LLM 제공자 설정                │
│    adelie run --goal "..."        AI 루프 시작                   │
│                                                                 │
│  상태 확인                                                       │
│    adelie status                  시스템 상태                     │
│    adelie phase                   현재 페이즈                    │
│    adelie kb                      KB 파일 수                     │
│    adelie git                     Git 상태                       │
│    adelie inform                  AI 리포트 생성                  │
│                                                                 │
│  프로젝트 관리                                                    │
│    adelie goal set "..."          목표 설정                      │
│    adelie feedback "..."          피드백 전송                     │
│    adelie research "..."          웹 리서치                      │
│    adelie scan                    코드베이스 스캔                  │
│                                                                 │
│  모델 관리                                                       │
│    adelie ollama list             모델 목록                      │
│    adelie ollama pull <model>     모델 다운로드                   │
│    adelie ollama run              대화형 채팅                    │
│                                                                 │
│  워크스페이스                                                     │
│    adelie ws                      목록                           │
│    adelie run ws <N>              재개                           │
│    adelie ws remove <N>           삭제                           │
│                                                                 │
│  도움말                                                          │
│    adelie help                    전체 명령어 레퍼런스             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

<p align="center">
  Made with 🐧 by Adelie
</p>
