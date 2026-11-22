-- 7.4 SQL DDL (SQLite 3.35+)
-- 요구사항 명세서 v1.0 3.4 Logical Database Requirements 기준.
-- 연결마다 실행: PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;
-- 시각은 ISO-8601 문자열(UTC, 'YYYY-MM-DDTHH:MM:SSZ'), 날짜는 'YYYY-MM-DD'로 저장한다.

PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- 1. 사용자 영역
------------------------------------------------------------
-- 11-14: 캘린더 파트 요청으로 학부(단과대학)를 테이블로 분리
CREATE TABLE faculty (
    faculty_id  INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE                     -- 표준 표기 (예: 소프트웨어융합대학)
);

CREATE TABLE department (
    dept_id     INTEGER PRIMARY KEY,
    faculty_id  INTEGER NOT NULL REFERENCES faculty(faculty_id),
    name        TEXT    NOT NULL UNIQUE,                    -- 표준 표기 (필터 값)
    campus      TEXT    NOT NULL CHECK (campus IN ('인문사회', '자연과학'))
);

CREATE TABLE department_alias (
    alias_id  INTEGER PRIMARY KEY,
    dept_id   INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE CASCADE,
    alias     TEXT    NOT NULL UNIQUE                       -- 크롤링에서 다르게 나오는 이름
);

CREATE TABLE app_user (
    user_id              INTEGER PRIMARY KEY,
    email_enc            BLOB    NOT NULL,                  -- AES-GCM 암호문
    email_hash           TEXT    NOT NULL UNIQUE,           -- HMAC-SHA256(소문자 이메일), 조회용
    dept_id              INTEGER REFERENCES department(dept_id) ON DELETE SET NULL,
    grade                INTEGER CHECK (grade BETWEEN 1 AND 6),
    admission_year       INTEGER CHECK (admission_year BETWEEN 1990 AND 2100),
    expected_graduation  TEXT,                              -- 'YYYY-MM', 삭제 안내 시점 참고값
    verified_at          TEXT    NOT NULL,                  -- 인증한 사용자만 레코드를 만든다
    created_at           TEXT    NOT NULL,
    last_access_at       TEXT    NOT NULL,
    deletion_notified_at TEXT                               -- 12개월 미접속 통지 시각
);

CREATE TABLE email_code (                                   -- 로그인 인증 코드 (로그인 파트 11/16 코드에 맞춤)
    code_id            INTEGER PRIMARY KEY,
    email_hash         TEXT    NOT NULL,                    -- 사용자 레코드가 없을 수 있어 FK 대신 식별값
    code_hash          TEXT    NOT NULL,                    -- HMAC(SECRET_KEY, "email:code"), 원문은 저장하지 않음
    sent_at            TEXT    NOT NULL,
    expires_at         TEXT    NOT NULL,                    -- 발송 후 10분 (11-22 결정, SRS 3.6.3의 3분에서 변경)
    used_at            TEXT,
    attempts           INTEGER NOT NULL DEFAULT 0,          -- 이 코드로 틀린 횟수
    send_count         INTEGER NOT NULL,                    -- 발송 제한 구간 안에서 몇 번째 발송인지
    window_started_at  TEXT    NOT NULL                     -- 발송 제한 구간 시작 시각
);
-- 발송할 때마다 새 행을 추가하고, 조회는 이메일의 가장 최근 행만 본다 (이전 코드는 자동으로 무효).
-- 오래된 행은 보존 기간 정리 batch가 지운다.

CREATE TABLE session (
    session_id  TEXT    PRIMARY KEY,                        -- UUIDv4, 쿠키 값
    user_id     INTEGER REFERENCES app_user(user_id) ON DELETE CASCADE,  -- 익명이면 NULL
    title       TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    expired_at  TEXT
);
-- 이미 다른 사용자에게 연결된 세션은 다시 연결할 수 없다
CREATE TRIGGER tr_session_no_relink
BEFORE UPDATE OF user_id ON session
WHEN OLD.user_id IS NOT NULL AND NEW.user_id IS NOT OLD.user_id
BEGIN
    SELECT RAISE(ABORT, 'session already linked to another user');
END;

CREATE TABLE interest_keyword (
    keyword_id    INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    keyword       TEXT    NOT NULL CHECK (length(keyword) BETWEEN 1 AND 30),       -- 사용자가 입력한 표기
    keyword_norm  TEXT    NOT NULL CHECK (length(keyword_norm) BETWEEN 1 AND 30),  -- 비교용 (공지·알림 파트 요청)
    created_at    TEXT    NOT NULL,
    UNIQUE (user_id, keyword_norm)
);

CREATE TABLE interest (                                     -- 온보딩에서 고르는 관심사 목록 (GET /api/interests)
    interest_id  INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 30),
    sort_order   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE user_interest (                                -- 사용자가 고른 관심사. 이름은 알림 키워드로도 쓴다 (11-22 결정)
    user_id      INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    interest_id  INTEGER NOT NULL REFERENCES interest(interest_id) ON DELETE CASCADE,
    created_at   TEXT    NOT NULL,
    PRIMARY KEY (user_id, interest_id)
);

-- 11-14: Google 캘린더 연결 (캘린더 파트 5.2.2 GoogleCalendarConnection). token은 이메일과 같은 방식으로 암호화
CREATE TABLE google_connection (
    user_id            INTEGER PRIMARY KEY REFERENCES app_user(user_id) ON DELETE CASCADE,
    google_account_id  TEXT    UNIQUE,                      -- calendar 권한만 받으면 Google이 주지 않을 수 있음
    google_email_enc   BLOB,
    access_token_enc   BLOB    NOT NULL,
    refresh_token_enc  BLOB,                                -- 재동의 때는 발급되지 않을 수 있어 NULL 허용 (있던 값 유지)
    token_expires_at   TEXT    NOT NULL,
    connected_at       TEXT    NOT NULL
);

-- 11-14: 지도 파트 요청 (장소 좋아요). 장소 자체는 카카오 API 실시간 조회라 테이블 없음
CREATE TABLE like_place (
    user_id     INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    place_id    TEXT    NOT NULL,                           -- 카카오 장소 id (숫자여도 문자열)
    place_url   TEXT    NOT NULL
                CHECK (place_url IN ('http://place.map.kakao.com/'  || place_id,
                                     'https://place.map.kakao.com/' || place_id)),
    campus      TEXT    NOT NULL CHECK (campus IN ('인문사회', '자연과학')),
    memo        TEXT,                                       -- 사용자가 붙인 이름 (화면에서는 글자로만 표시)
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (user_id, place_id)
);

------------------------------------------------------------
-- 2. 대화 기록 영역 (작업 환경이 메시지를 참조하므로 먼저 정의)
------------------------------------------------------------
CREATE TABLE message (
    message_id  INTEGER PRIMARY KEY,
    session_id  TEXT    NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT    NOT NULL CHECK (role IN ('user', 'agent', 'tool')),
    content     TEXT    NOT NULL,
    model       TEXT,                                       -- 에이전트 메시지만
    created_at  TEXT    NOT NULL,
    UNIQUE (session_id, seq)
);

-- 작업 환경 (사용자 기억): 인증 사용자에게만, 출처 메시지 필수
CREATE TABLE user_memory (
    memory_id          INTEGER PRIMARY KEY,
    user_id            INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    content            TEXT    NOT NULL,
    source_message_id  INTEGER REFERENCES message(message_id) ON DELETE SET NULL,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

CREATE TABLE tool_call (
    call_id         INTEGER PRIMARY KEY,
    message_id      INTEGER NOT NULL REFERENCES message(message_id) ON DELETE CASCADE,
    tool_name       TEXT    NOT NULL,
    input_json      TEXT    NOT NULL,
    result_summary  TEXT,
    success         INTEGER NOT NULL CHECK (success IN (0, 1)),
    duration_ms     INTEGER,
    called_at       TEXT    NOT NULL
);

------------------------------------------------------------
-- 3. 학칙 영역 (법제처 국가법령정보 구조)
------------------------------------------------------------
CREATE TABLE regulation (
    reg_id              INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL UNIQUE,
    part                TEXT,                               -- 편
    department_in_charge TEXT
);

CREATE TABLE regulation_version (
    version_id      INTEGER PRIMARY KEY,
    reg_id          INTEGER NOT NULL REFERENCES regulation(reg_id) ON DELETE CASCADE,
    amend_type      TEXT    NOT NULL CHECK (amend_type IN ('제정', '일부개정', '전부개정', '폐지')),
    promulgated_on  TEXT,
    effective_from  TEXT    NOT NULL,
    effective_to    TEXT,                                   -- NULL = 현행
    source_url      TEXT    NOT NULL,
    amend_reason    TEXT,
    collected_at    TEXT    NOT NULL,
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    UNIQUE (reg_id, effective_from)
);
-- 같은 규정에서 시행 기간이 겹치는 버전은 존재할 수 없다
CREATE TRIGGER tr_version_no_overlap_ins
BEFORE INSERT ON regulation_version
WHEN EXISTS (
    SELECT 1 FROM regulation_version v
    WHERE v.reg_id = NEW.reg_id
      AND v.effective_from < COALESCE(NEW.effective_to, '9999-12-31')
      AND NEW.effective_from < COALESCE(v.effective_to, '9999-12-31'))
BEGIN
    SELECT RAISE(ABORT, 'overlapping regulation version');
END;
CREATE TRIGGER tr_version_no_overlap_upd
BEFORE UPDATE OF effective_from, effective_to ON regulation_version
WHEN EXISTS (
    SELECT 1 FROM regulation_version v
    WHERE v.reg_id = NEW.reg_id AND v.version_id <> NEW.version_id
      AND v.effective_from < COALESCE(NEW.effective_to, '9999-12-31')
      AND NEW.effective_from < COALESCE(v.effective_to, '9999-12-31'))
BEGIN
    SELECT RAISE(ABORT, 'overlapping regulation version');
END;

CREATE TABLE article (
    article_id      INTEGER PRIMARY KEY,
    version_id      INTEGER NOT NULL REFERENCES regulation_version(version_id) ON DELETE CASCADE,
    article_no      INTEGER NOT NULL,                       -- 제25조 → 25
    branch_no       INTEGER NOT NULL DEFAULT 0,             -- 제25조의2 → 2
    title           TEXT,
    chapter         TEXT,                                   -- 장·절 위치
    effective_from  TEXT,                                   -- 조문시행일 (NULL이면 버전 시행일)
    is_changed      INTEGER NOT NULL DEFAULT 0 CHECK (is_changed IN (0, 1)),
    content         TEXT    NOT NULL,                       -- 항·호·목 포함
    source_page     INTEGER,
    UNIQUE (version_id, article_no, branch_no)
);

CREATE TABLE addendum (
    addendum_id          INTEGER PRIMARY KEY,
    version_id           INTEGER NOT NULL REFERENCES regulation_version(version_id) ON DELETE CASCADE,
    content              TEXT    NOT NULL,
    admission_year_from  INTEGER,                           -- NULL = 하한 없음
    admission_year_to    INTEGER,                           -- NULL = 상한 없음
    CHECK (admission_year_to IS NULL OR admission_year_from IS NULL
           OR admission_year_to >= admission_year_from)
);

CREATE TABLE annex (
    annex_id    INTEGER PRIMARY KEY,
    version_id  INTEGER NOT NULL REFERENCES regulation_version(version_id) ON DELETE CASCADE,
    annex_no    INTEGER NOT NULL,
    branch_no   INTEGER NOT NULL DEFAULT 0,
    title       TEXT,
    content     TEXT    NOT NULL,                           -- 표는 Markdown 표로 정규화해 저장
    UNIQUE (version_id, annex_no, branch_no)
);

------------------------------------------------------------
-- 4. 공지·일정 영역 (11-14: 공지·알림 파트 설계로 교체, 일정은 캘린더 파트 합의 전 초안)
------------------------------------------------------------
CREATE TABLE board (                                        -- 수집 대상 게시판 + 크롤링 현황
    board_id              INTEGER PRIMARY KEY,
    name                  TEXT    NOT NULL UNIQUE,
    scope                 TEXT    NOT NULL CHECK (scope IN ('SCHOOL', 'COLLEGE', 'DEPT')),
    faculty_id            INTEGER REFERENCES faculty(faculty_id),      -- scope = COLLEGE일 때
    dept_id               INTEGER REFERENCES department(dept_id),      -- scope = DEPT일 때
    list_url              TEXT    NOT NULL,
    allowed_host          TEXT    NOT NULL,                 -- 원문 링크 검증용 도메인
    parser_type           TEXT    NOT NULL,
    is_active             INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    last_success_at       TEXT,
    last_article_no       INTEGER NOT NULL DEFAULT 0,       -- 다음 크롤링은 이 번호 다음부터
    CHECK ((scope = 'SCHOOL'  AND faculty_id IS NULL     AND dept_id IS NULL)
        OR (scope = 'COLLEGE' AND faculty_id IS NOT NULL AND dept_id IS NULL)
        OR (scope = 'DEPT'    AND faculty_id IS NULL     AND dept_id IS NOT NULL))
);

CREATE TABLE crawl_run (                                    -- 수집 실행 기록 (게시판마다 한 행)
    run_id            INTEGER PRIMARY KEY,
    board_id          INTEGER NOT NULL REFERENCES board(board_id) ON DELETE CASCADE,
    cycle_started_at  TEXT    NOT NULL,                     -- 같은 주기의 행을 묶는 값
    started_at        TEXT    NOT NULL,
    finished_at       TEXT,
    status            TEXT    NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    fetched_count     INTEGER NOT NULL DEFAULT 0,
    new_count         INTEGER NOT NULL DEFAULT 0,
    updated_count     INTEGER NOT NULL DEFAULT 0,
    skipped_count     INTEGER NOT NULL DEFAULT 0,
    error_message     TEXT
);

CREATE TABLE notice (                                       -- 같은 공지는 여러 게시판에 실려도 한 행
    notice_id           INTEGER PRIMARY KEY,                -- 내용을 덮어써도 유지
    category            TEXT,                               -- 말머리
    title               TEXT    NOT NULL,
    title_norm          TEXT    NOT NULL,
    dup_key             TEXT    NOT NULL,                   -- 같은 공지 후보 검색용 해시
    body                TEXT    NOT NULL,
    posted_at           TEXT    NOT NULL,
    url                 TEXT    NOT NULL,                   -- 대표 원문 링크
    attachments_json    TEXT,                               -- [{name, url}]
    summary_deadline    TEXT,
    summary_target      TEXT,
    summary_how         TEXT,
    content_hash        TEXT    NOT NULL,                   -- 원문 수정 감지
    is_pinned           INTEGER NOT NULL DEFAULT 0 CHECK (is_pinned IN (0, 1)),  -- 번호 없는 고정 공지 [확인 필요]
    collected_at        TEXT    NOT NULL,
    last_checked_at     TEXT    NOT NULL,
    content_updated_at  TEXT    NOT NULL,
    tags_changed_at     TEXT    NOT NULL                    -- 새 공지·노출 범위 확대 감지
);

CREATE TABLE notice_posting (                               -- 공지가 실린 게시판별 위치
    posting_id     INTEGER PRIMARY KEY,
    notice_id      INTEGER NOT NULL REFERENCES notice(notice_id) ON DELETE CASCADE,
    board_id       INTEGER NOT NULL REFERENCES board(board_id),
    article_no     INTEGER NOT NULL,
    url            TEXT    NOT NULL,
    posted_at      TEXT    NOT NULL,
    content_hash   TEXT    NOT NULL,
    first_seen_at  TEXT    NOT NULL,
    last_seen_at   TEXT    NOT NULL,
    UNIQUE (board_id, article_no)
);

CREATE TABLE notice_tag (                                   -- 노출 범위 (학교 / 단과대학 / 학과)
    tag_id      INTEGER PRIMARY KEY,
    notice_id   INTEGER NOT NULL REFERENCES notice(notice_id) ON DELETE CASCADE,
    scope       TEXT    NOT NULL CHECK (scope IN ('SCHOOL', 'COLLEGE', 'DEPT')),
    faculty_id  INTEGER REFERENCES faculty(faculty_id),
    dept_id     INTEGER REFERENCES department(dept_id),
    CHECK ((scope = 'SCHOOL'  AND faculty_id IS NULL     AND dept_id IS NULL)
        OR (scope = 'COLLEGE' AND faculty_id IS NOT NULL AND dept_id IS NULL)
        OR (scope = 'DEPT'    AND faculty_id IS NULL     AND dept_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_notice_tag ON notice_tag(notice_id, scope, IFNULL(faculty_id, 0), IFNULL(dept_id, 0));

CREATE TABLE user_board (                                   -- 사용자가 알림을 받을 게시판 (공지·알림 파트 요청)
    user_id   INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    board_id  INTEGER NOT NULL REFERENCES board(board_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, board_id)
);

CREATE TABLE schedule (                                     -- 캘린더 파트 안 (정우진 11-18)
    schedule_id      INTEGER PRIMARY KEY,
    notice_title     TEXT    NOT NULL,                      -- 크롤링한 원본 공지 제목
    event_title      TEXT,                                  -- agent가 만든 일정 제목
    description      TEXT,
    start_at         TEXT    NOT NULL,
    end_at           TEXT,
    all_day          INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0, 1)),
    place            TEXT,
    target_audience  TEXT,
    organizer        TEXT,
    kind             TEXT    NOT NULL CHECK (kind IN ('학사일정', '학과 행사', '공지 마감')),
    source_url       TEXT,
    image_path       TEXT,                                  -- 파일 저장소 경로 (예: events/1/poster.jpg), 조회 시 URL로 변환
    board_id         TEXT,                                  -- 게시판 식별자 (외래 키 아님)
    notice_id        TEXT,                                  -- 원본 게시글 번호 (외래 키 아님)
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),  -- 공지 수정으로 일정이 취소되면 0
    CHECK (end_at IS NULL OR end_at >= start_at)
);

CREATE TABLE schedule_department (                          -- 일정–학과 N:M (캘린더 파트 Event_department)
    schedule_id  INTEGER NOT NULL REFERENCES schedule(schedule_id) ON DELETE CASCADE,
    dept_id      INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE CASCADE,
    PRIMARY KEY (schedule_id, dept_id)
);

CREATE TABLE schedule_processing (                          -- 공지 한 건의 일정 추출 처리 결과 (캘린더 파트 3.2.7, 중복 전달 방지)
    board_id      TEXT    NOT NULL,
    notice_id     TEXT    NOT NULL,
    status        TEXT    NOT NULL CHECK (status IN ('COMPLETED', 'EXCLUDED', 'FAILED')),
    reason        TEXT,                                     -- LLM decisionReason
    error         TEXT,
    event_count   INTEGER NOT NULL DEFAULT 0,
    processed_at  TEXT    NOT NULL,
    PRIMARY KEY (board_id, notice_id)
);

CREATE TABLE calendar_export (                              -- Google 캘린더에 넣은 일정 (중복 등록 방지)
    user_id          INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    schedule_id      INTEGER NOT NULL REFERENCES schedule(schedule_id) ON DELETE CASCADE,
    google_event_id  TEXT    NOT NULL,
    exported_at      TEXT    NOT NULL,
    PRIMARY KEY (user_id, schedule_id)
);

CREATE TABLE notification (                                 -- 공지 알림과 일정 알림 공용
    notif_id          INTEGER PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    notice_id         INTEGER REFERENCES notice(notice_id) ON DELETE CASCADE,
    schedule_id       INTEGER REFERENCES schedule(schedule_id) ON DELETE CASCADE,
    kind              TEXT    NOT NULL CHECK (kind IN ('KEYWORD_MATCH', 'EVENT_REMINDER')),
    matched_keywords  TEXT,                                 -- JSON, 매칭 근거
    status            TEXT    NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'DEAD')),
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    created_at        TEXT    NOT NULL,
    sent_at           TEXT,
    CHECK ((notice_id IS NULL) <> (schedule_id IS NULL)),   -- 대상은 공지 또는 일정 중 정확히 하나
    UNIQUE (user_id, notice_id),
    UNIQUE (user_id, schedule_id)
);

------------------------------------------------------------
-- 5. 검색 영역 (벡터 색인 항목은 Chroma에 저장)
------------------------------------------------------------
CREATE TABLE document (
    doc_id        INTEGER PRIMARY KEY,
    doc_type      TEXT    NOT NULL CHECK (doc_type IN ('조문', '별표', '공지사항')),
    source_table  TEXT    NOT NULL CHECK (source_table IN ('article', 'annex', 'notice')),
    source_id     INTEGER NOT NULL,                         -- 원본 엔티티 참조 (다형 참조, FK 없음)
    title         TEXT    NOT NULL,
    source_url    TEXT    NOT NULL,
    published_at  TEXT,
    collected_at  TEXT    NOT NULL,
    dept_id       INTEGER REFERENCES department(dept_id) ON DELETE SET NULL,
    campus        TEXT,
    trust_level   TEXT    NOT NULL
                  CHECK (trust_level IN ('공식 규정', '공식 공지', '수집 정보', '사용자 생성')),
    UNIQUE (source_table, source_id)
);
-- 원본이 삭제되면 문서도 삭제 (다형 참조라 트리거로 처리, 청크는 FK CASCADE)
CREATE TRIGGER tr_article_del_doc AFTER DELETE ON article
BEGIN DELETE FROM document WHERE source_table = 'article' AND source_id = OLD.article_id; END;
CREATE TRIGGER tr_annex_del_doc AFTER DELETE ON annex
BEGIN DELETE FROM document WHERE source_table = 'annex' AND source_id = OLD.annex_id; END;
CREATE TRIGGER tr_notice_del_doc AFTER DELETE ON notice
BEGIN DELETE FROM document WHERE source_table = 'notice' AND source_id = OLD.notice_id; END;

CREATE TABLE chunk (
    chunk_id       INTEGER PRIMARY KEY,                     -- Chroma 항목 id와 같은 값
    doc_id         INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    seq            INTEGER NOT NULL,
    text           TEXT    NOT NULL,                        -- 청크 텍스트는 SQLite에만
    token_count    INTEGER NOT NULL,
    chunk_rule     TEXT    NOT NULL,                        -- 청킹 규칙 버전 (예: 'article-v1')
    created_at     TEXT    NOT NULL,
    UNIQUE (doc_id, chunk_rule, seq)
);

-- 삭제된 청크 id 대기열: 동기화 작업이 Chroma 전 컬렉션에서 지운 뒤 비운다
CREATE TABLE chunk_tombstone (
    chunk_id    INTEGER PRIMARY KEY,
    chunk_rule  TEXT    NOT NULL,
    deleted_at  TEXT    NOT NULL
);
CREATE TRIGGER tr_chunk_tombstone AFTER DELETE ON chunk
BEGIN
    INSERT OR REPLACE INTO chunk_tombstone(chunk_id, chunk_rule, deleted_at)
    VALUES (OLD.chunk_id, OLD.chunk_rule, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
END;

CREATE TABLE index_config (
    index_id         INTEGER PRIMARY KEY,
    name             TEXT    NOT NULL UNIQUE,               -- Chroma 컬렉션 이름
    embedding_model  TEXT    NOT NULL,                      -- 예: 'BAAI/bge-m3'
    dimension        INTEGER NOT NULL CHECK (dimension > 0),
    chunk_rule       TEXT    NOT NULL,
    scope            TEXT    NOT NULL,                      -- 대상 문서 종류 (예: '조문,별표')
    is_active        INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at       TEXT    NOT NULL,
    chunk_count      INTEGER NOT NULL DEFAULT 0             -- 구축 시점 기록값 (정합성 점검용)
);
-- 같은 scope에서 운영 중인 색인은 하나만
CREATE UNIQUE INDEX ux_index_active ON index_config(scope) WHERE is_active = 1;

CREATE TABLE retrieval (
    retrieval_id  INTEGER PRIMARY KEY,
    message_id    INTEGER NOT NULL REFERENCES message(message_id) ON DELETE CASCADE,
    query         TEXT    NOT NULL,
    filter_json   TEXT    NOT NULL,                         -- 생성된 메타데이터 필터
    index_id      INTEGER REFERENCES index_config(index_id) ON DELETE SET NULL,
    hit_count     INTEGER NOT NULL DEFAULT 0,               -- 0 = 검색 결과 없음도 기록
    searched_at   TEXT    NOT NULL
);

CREATE TABLE retrieval_hit (
    retrieval_id  INTEGER NOT NULL REFERENCES retrieval(retrieval_id) ON DELETE CASCADE,
    rank          INTEGER NOT NULL,
    chunk_id      INTEGER NOT NULL,                         -- FK 없음: 재색인으로 청크가 지워져도 기록 유지
    score         REAL    NOT NULL,
    adopted       INTEGER NOT NULL DEFAULT 0 CHECK (adopted IN (0, 1)),  -- 근거로 채택
    PRIMARY KEY (retrieval_id, rank)
);

------------------------------------------------------------
-- 6. 평가 영역
------------------------------------------------------------
CREATE TABLE eval_set (
    set_version  TEXT    PRIMARY KEY,                       -- 예: 'v1'
    description  TEXT,
    created_at   TEXT    NOT NULL
);

CREATE TABLE eval_question (
    question_id           INTEGER PRIMARY KEY,
    set_version           TEXT    NOT NULL REFERENCES eval_set(set_version) ON DELETE CASCADE,
    question              TEXT    NOT NULL,
    expected_evidence     TEXT    NOT NULL,                 -- 기대 근거 (예: '학칙 제25조')
    expected_answer_type  TEXT    NOT NULL CHECK (expected_answer_type IN ('단순 조회', '조건 판단', '여러 규정 조합', '답 없음')),
    author                TEXT
);

CREATE TABLE eval_run (
    run_id         INTEGER PRIMARY KEY,
    run_at         TEXT    NOT NULL,
    index_id       INTEGER NOT NULL REFERENCES index_config(index_id),
    set_version    TEXT    NOT NULL REFERENCES eval_set(set_version),
    hit_at_5       REAL,
    mrr            REAL,
    ragas_json     TEXT,                                    -- RAGAS 지표 묶음
    failures_json  TEXT                                     -- 실패 사례 목록
);

------------------------------------------------------------
-- 조회용 인덱스 (7.6)
------------------------------------------------------------
CREATE INDEX ix_session_user        ON session(user_id);
CREATE INDEX ix_message_created     ON message(created_at);           -- 30일 보존 삭제
CREATE INDEX ix_user_last_access    ON app_user(last_access_at);      -- 12개월 미접속 통지
CREATE INDEX ix_email_code_latest  ON email_code(email_hash, code_id DESC);  -- 이메일의 최신 코드
CREATE INDEX ix_memory_user         ON user_memory(user_id);
CREATE INDEX ix_tool_call_message   ON tool_call(message_id);
CREATE INDEX ix_retrieval_message   ON retrieval(message_id);
CREATE INDEX ix_version_reg         ON regulation_version(reg_id, effective_from);
CREATE INDEX ix_notice_posted       ON notice(posted_at);
CREATE INDEX ix_notice_dupkey       ON notice(dup_key);               -- 같은 공지 후보 검색
CREATE INDEX ix_notice_tags_changed ON notice(tags_changed_at);       -- 이번 주기 매칭 대상
CREATE INDEX ix_posting_notice      ON notice_posting(notice_id);
CREATE INDEX ix_tag_dept            ON notice_tag(dept_id);
CREATE INDEX ix_crawl_run_board     ON crawl_run(board_id, started_at);
CREATE INDEX ix_schedule_start      ON schedule(start_at);
CREATE INDEX ix_schedule_notice     ON schedule(board_id, notice_id);   -- 같은 공지에서 뽑은 일정
CREATE INDEX ix_sched_dept_dept     ON schedule_department(dept_id);
CREATE INDEX ix_notif_user          ON notification(user_id);
CREATE INDEX ix_notif_retry         ON notification(status, attempt_count);  -- 재발송 대상
CREATE INDEX ix_like_place          ON like_place(place_id);          -- 장소별 좋아요 수
CREATE INDEX ix_chunk_doc           ON chunk(doc_id);
CREATE INDEX ix_keyword_kw          ON interest_keyword(keyword_norm);     -- 새 공지와 키워드 매칭
