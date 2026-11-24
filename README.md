# (프로젝트 명)
학생들을 위한 생활정보 챗 에이전트 웹 서비스.

## 주 기능
- 교내 이메일 인증 로그인: 학교 이메일로 인증 후 작업 환경 저장
- 학규 정보 질의응답: 학규 문서를 근거로 출처와 함께 답변
- 학교 주변 인프라 지도: 질의에 따라 적절한 장소 목록 제시
- 학과 일정 캘린더: 학과 일정을 캘린더 페이지로 제공

## 기술 스택
| 영역 | 기술 |
|---|---|
| 프론트엔드 | React, Vite |
| 백엔드 | Python, Flask |
| 에이전트 | LangChain, OpenAI API |
| DB | SQLite, ChromaDB |
| 지도 | 카카오 지도 JavaScript SDK (프론트), 카카오 로컬 REST API (백엔드) |

## 폴더 구조안
```
.
├── frontend/              # React + Vite 웹 클라이언트
├── backend/               # Flask 서버
│   ├── app.py             # 서버 진입점
│   ├── agent/             # 에이전트 루프, 시스템 프롬프트
│   ├── tools/             # 에이전트 툴 (정의 + 실행 함수). 지도 검색 로직은 places.py
│   ├── services/          # 여러 곳에서 쓰는 외부 서비스 연동 (메일 발송, 카카오 로컬 API 등)와 지도 상수
│   ├── api/               # HTTP 엔드포인트
│   │   ├── auth/          # 이메일 인증 로그인, 세션, 사용자 정보 (로그인 담당)
│   │   ├── map_places.py  # 장소 좋아요 등록/취소/내 목록 (지도 담당)
│   │   ├── errors.py      # 공통 오류 응답 (모든 파트가 사용)
│   │   └── guards.py      # 공통 로그인 검사 (모든 파트가 사용)
│   ├── db/                # DB 접근 함수
│   ├── config/            # FE와 공유하는 설정 데이터 (campuses.json)
│   └── tests/             # 백엔드 테스트
├── docs/                  # 디자인 명세서, 공통 합의서, API 명세, 로그인 설계
├── .gitignore
└── README.md
```

## 실행 방법
처음 한 번은 아래 순서로 준비하고, 이후에는 백엔드와 프론트엔드를 각각 실행한다.

### 사전 준비
- Python 3.11 이상, Node.js 20 이상

### 백엔드 (Flask)
**1. `backend/` 에서 가상환경 만들고 패키지 설치**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. 환경변수 설정** (`backend/` 에서)
```bash
cp .env.example .env             # .env 구조를 .env에 복사 (값 설정은 로컬에서 직접)
```
| 변수 | 설명 |
|---|---|
| `SECRET_KEY` | 세션 쿠키 서명과 인증 코드 해시용 |
| `DB_SECRET_KEY` | 이메일 암호화용 |
| `DB_PATH` | DB 파일 위치|
| `COOKIE_SECURE` | 로컬 http 개발은 `0` |
| `SMTP_*` | 인증 메일 발송 설정 |
| `KAKAO_REST_API_KEY` | 카카오 로컬 REST API 키 (BE 지도 검색용) |

**3. DB 초기 데이터 넣기** (저장소 **루트**에서, 처음 한 번만)
```bash
python -m backend.db.seed_data
```
학과, 관심사 등 기본 데이터를 DB에 넣는다. 이미 있으면 건너뛰므로 여러 번 실행해도 된다. 
테이블은 서버를 띄울 때 자동으로 만들어진다.

**4. 서버 실행** (`backend/` 에서, 가상환경을 켠 상태)
```bash
flask --app app run --debug --port 5000
```

**5. 테스트** (`backend/` 에서)
```bash
pytest tests/test_login_db.py
```

### 프론트엔드 (React + Vite)

```bash
cd frontend
npm install
npm run dev                      # 기본 주소 http://localhost:5173
```

### 참고
- 백엔드는 항상 `backend/` 에서 실행한다. 시드 명령만 저장소 루트에서 실행한다.
- `.env`, `data/`(DB 파일)는 git에 올리지 않는다.
- 에이전트(`agent/`)는 아직 임시 스텁이라 채팅 응답은 고정 문구가 나온다.
