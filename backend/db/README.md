# backend/db

SQLite(원본) + SQLAlchemy 2.0 ORM. 다른 파트는 아래 함수만 부르고 SQL·ORM 객체를 직접 다루지 않는다. 함수는 dict(또는 dict 목록)를 돌려준다.

## 준비

```bash
pip install -r backend/requirements.txt
export DB_PATH=data/app.db                      # 기본값 data/app.db
export DB_SECRET_KEY=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
```

```python
from backend.db import get_engine, init_db
init_db(get_engine())        # 빈 DB면 schema.sql 실행, 이미 있으면 그대로
```

```bash
python -m backend.db.seed_data   # 단과대학·학과·게시판·관심사 넣기 (프로토타입, 이미 있으면 건너뜀)
```

- 참조 데이터는 `seed/prototype_reference.json`이다. 이서영 님 `공지사항 주소.xlsx`(11/17)에서 만든 **프로토타입**이라 캠퍼스는 추정값이고 `parser_type`은 `TBD`다. 크롤링해 본 뒤 공지·알림 파트와 확정한다. 학과 id는 이 파일이 정하고 FE 드롭다운도 같은 id를 쓴다.
- 로그인 파트 코드(`backend/api`)는 `backend/`를 기준으로 `db.user`처럼 import한다. 서버는 `backend/`에서 실행하거나 `backend/`를 `PYTHONPATH`에 넣는다.

- 테이블 정의의 기준은 `schema.sql`이다. 열을 바꾸면 `schema.sql`과 `models.py`를 같이 고치고 `pytest backend/tests`로 둘이 맞는지 확인한다.
- 시각은 모두 UTC 문자열 `YYYY-MM-DDTHH:MM:SSZ`.
- 사용자 식별자는 서버 세션에서 꺼내 넘긴다. 요청 본문이나 LLM tool 인자로 받지 않는다.
- 사용자를 지우면 키워드·좋아요·알림·대화가 DB에서 함께 지워진다(CASCADE).

## 함수

| 모듈 | 함수 | 쓰는 파트 |
|---|---|---|
| `email_verification` | `get_code`, `upsert_code`, `increment_attempts`, `mark_code_used` | 로그인 (`api/auth`) |
| `user` | `get_user_by_id`, `get_user_by_email`, `create_user`, `update_last_login` | 로그인 |
| `profile` | `list_departments`, `list_interests`, `department_exists`, `interests_exist`, `get_department_name`, `list_user_interest_ids`, `save_profile` | 로그인 (온보딩, `/api/departments`, `/api/interests`), 채팅 |
| `errors` | `DbError` (잠금 시간 초과 등 일시 오류, API가 503으로 바꿈) | 공통 |
| `schedules` (초안) | `get_all_faculties_with_departments`, `get_department_events(id, month)`, `get_department_calendar(id, month)`, `get_events_by_ids` | 캘린더 조회 (`/api/departments`, `/api/departments/{id}/events`) |
| `schedules` (초안) | `find_events_by_notice`, `save_event_changes(events, department_id)`, `deactivate_event`, `record_processing_result`, `get_processing_result` | 일정 추출 파이프라인 |
| `schedules` (초안) | `save_google_tokens`, `get_google_tokens`, `delete_google_connection`, `get_exported_events`, `record_export` | Google 캘린더 등록 |
| `users` | `get_user_scope`, `list_departments` | 공통 (캘린더 `/api/users/me`, `/api/departments`) |
| `users` | `list_keywords`, `add_keyword`, `update_keyword`, `delete_keyword`, `set_keywords` | 키워드 (채팅 tool, 가입 직후 등록) |
| `users` | `list_user_boards`, `set_user_boards`, `list_keyword_subscribers(board_id)` | 알림 배치 |
| `notices` | `list_active_boards`, `start_crawl_run`, `finish_crawl_run(..., last_article_no)`, `set_board_active`, `last_successful_sync_at` | 크롤러 |
| `notices` | `find_posting`, `find_duplicate_candidates`, `create_notice(post, board_id, tags)`, `add_notice_posting`, `update_notice_content`, `touch_posting`, `update_notice_summary` | 크롤러 |
| `notices` | `get_notice`, `get_notice_tags`, `list_visible_notices`, `list_notices_changed_since(since, field)` | Agent, 알림, 캘린더 |
| `notifications` | `create_pending_notification`, `mark_notification_sent`, `mark_notification_failed`, `list_retryable_notifications`, `list_user_notifications` | 알림 |
| `likes` | `insert_like`, `delete_like`, `like_stats`, `count_likes_by_place_ids`, `get_liked_place_ids`, `count_user_likes`, `list_likes_by_user` | 지도 |

공유 Docs 요청과 다른 점:
- `create_notice`는 첫 게시 위치와 노출 태그까지 한 트랜잭션으로 만든다. 검색용 문서도 공지 저장·수정 때 자동으로 맞추므로 `upsert_notice_document`를 따로 부르지 않는다.
- `finish_crawl_run`은 성공했을 때만 게시판의 `last_article_no`를 올린다.
- `list_visible_notices(None)`은 학교 전체 공지만 준다 (학과를 모르는 익명 사용자).
- `list_notices_changed_since(field="content")`는 내용이 바뀐 공지 (캘린더 일정 추출용).
- `like_stats`가 좋아요 수와 내가 눌렀는지를 한 번에 준다. `delete_likes_of_user`는 CASCADE로 대신한다.

로그인 파트 코드에 맞춘 것 (11-22):
- 인증 코드는 `email_code`에 발송마다 새 행을 추가하고, 조회는 그 이메일의 최신 행만 본다. 이름은 `upsert_code`지만 덮어쓰지 않는다. 만료는 10분(로그인 코드 `CODE_TTL_SEC`).
- 반환은 로그인 코드 형식 `{id, email, department_id}`, 인증 코드 시각은 UTC datetime. DB 열 이름(`user_id`, `dept_id`, 암호화 이메일)은 그대로다.
- 관심사: `interest`(선택지) + `user_interest`(고른 것). 고른 관심사의 이름은 알림 키워드로도 쓴다 (`list_keyword_subscribers`의 `keywords`에 `source: "INTEREST"`로 들어감).

캘린더 함수 초안 (11-22, 정우진 님 명세 기준. 바로 쓰거나 피드백 주시면 고침):
- 함수 이름은 명세서 이름을 따랐고, 반환은 명세 6.1 응답 필드를 snake_case로 (`event_id`, `image_urls`, `title`, `start_at`, `end_at`, `is_all_day`, `location`, `organization`, `summary`, `source_url` …). camelCase 변환은 API 쪽.
- `title`은 `event_title`(agent 생성)이 있으면 그것, 없으면 `notice_title`. `summary`는 `description` 열.
- 일정 시각은 한국 시간 그대로 `YYYY-MM-DD`(종일) 또는 `YYYY-MM-DDTHH:MM`로 저장 (다른 테이블의 UTC 규칙과 다름). 형식이 다르면 `save_event_changes`가 ValueError.
- `month` 조회는 그 달 앞뒤 2개월과 기간이 겹치는 일정 (명세 6.1).
- 같은 공지(`board_id`, `notice_id`)·같은 시작/종료·같은 제목이면 KEEP, 학과 연결만 추가.
- 처리 결과는 새 테이블 `schedule_processing` (COMPLETED/EXCLUDED/FAILED). OAuth state와 보류 중인 등록 대상은 Flask 세션에 두는 것을 제안.
- 확인할 것: `createdAt`/`updatedAt`은 11/18 요청으로 열을 지워 지금 null로 나감 / `kind`는 LLM 출력에 없어 기본값 '학과 행사' / 이미지는 지금 한 장(`image_path`)이라 `image_urls`는 0~1개 / `schedule.board_id`가 우리 `board.board_id`(정수)와 같은 것인지.

아직 없음: 대화 목록(이전 대화) API용 함수, Agent 검색 `search()`, 보존 기간 정리 batch(오래된 `email_code` 행 포함). `users.list_departments`와 `profile.list_departments`는 반환 형식이 달라 둘 다 두었다 (나중에 정리).
