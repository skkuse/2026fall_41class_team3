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

- 테이블 정의의 기준은 `schema.sql`이다. 열을 바꾸면 `schema.sql`과 `models.py`를 같이 고치고 `pytest backend/tests`로 둘이 맞는지 확인한다.
- 시각은 모두 UTC 문자열 `YYYY-MM-DDTHH:MM:SSZ`.
- 사용자 식별자는 서버 세션에서 꺼내 넘긴다. 요청 본문이나 LLM tool 인자로 받지 않는다.
- 사용자를 지우면 키워드·좋아요·알림·대화가 DB에서 함께 지워진다(CASCADE).

## 함수

| 모듈 | 함수 | 쓰는 파트 |
|---|---|---|
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

아직 없음: 캘린더 일정 함수(캘린더 파트와 테이블 합의 후), 이메일 인증·세션, Agent 검색 `search()`, 보존 기간 정리 batch.
