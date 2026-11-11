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
├── frontend/          # React + Vite 웹 클라이언트
├── backend/           # Flask 서버
│   ├── agent/         # 에이전트 루프, 시스템 프롬프트
│   ├── tools/         # 에이전트 툴 (정의 + 실행 함수)
│   ├── services/      # 외부 API 클라이언트 (카카오 등)
│   ├── api/           # HTTP 엔드포인트
│   └── db/            # DB 모델, seed 데이터
├── docs/              # 디자인 명세서, 공통 합의서, API 명세
├── .gitignore
└── README.md
```
