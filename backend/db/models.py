"""ORM 매핑. 테이블 생성은 schema.sql이 맡고, 여기서는 이미 있는 테이블에 연결만 한다.

schema.sql에서 sqlacodegen으로 생성한 뒤 다듬었다. 테이블·열을 바꾸면 schema.sql과 함께 고치고
tests/test_models_match_schema.py로 둘이 맞는지 확인한다.
"""
from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, LargeBinary, REAL, Table, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class ChunkTombstone(Base):
    __tablename__ = 'chunk_tombstone'

    chunk_rule: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class EmailToken(Base):
    __tablename__ = 'email_token'

    email_hash: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    send_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    token_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    used_at: Mapped[Optional[str]] = mapped_column(Text)
    revoked_at: Mapped[Optional[str]] = mapped_column(Text)


class EvalSet(Base):
    __tablename__ = 'eval_set'

    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    set_version: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    eval_question: Mapped[list['EvalQuestion']] = relationship('EvalQuestion', back_populates='eval_set')
    eval_run: Mapped[list['EvalRun']] = relationship('EvalRun', back_populates='eval_set')


class Faculty(Base):
    __tablename__ = 'faculty'

    name: Mapped[str] = mapped_column(Text, nullable=False)
    faculty_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    department: Mapped[list['Department']] = relationship('Department', back_populates='faculty')
    board: Mapped[list['Board']] = relationship('Board', back_populates='faculty')
    notice_tag: Mapped[list['NoticeTag']] = relationship('NoticeTag', back_populates='faculty')


class IndexConfig(Base):
    __tablename__ = 'index_config'

    name: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_rule: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    index_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    eval_run: Mapped[list['EvalRun']] = relationship('EvalRun', back_populates='index')
    retrieval: Mapped[list['Retrieval']] = relationship('Retrieval', back_populates='index')


class Notice(Base):
    __tablename__ = 'notice'

    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_norm: Mapped[str] = mapped_column(Text, nullable=False)
    dup_key: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_pinned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    collected_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_checked_at: Mapped[str] = mapped_column(Text, nullable=False)
    content_updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    tags_changed_at: Mapped[str] = mapped_column(Text, nullable=False)
    notice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[Optional[str]] = mapped_column(Text)
    attachments_json: Mapped[Optional[str]] = mapped_column(Text)
    summary_deadline: Mapped[Optional[str]] = mapped_column(Text)
    summary_target: Mapped[Optional[str]] = mapped_column(Text)
    summary_how: Mapped[Optional[str]] = mapped_column(Text)

    notice_tag: Mapped[list['NoticeTag']] = relationship('NoticeTag', back_populates='notice')
    notice_posting: Mapped[list['NoticePosting']] = relationship('NoticePosting', back_populates='notice')
    notification: Mapped[list['Notification']] = relationship('Notification', back_populates='notice')


class Regulation(Base):
    __tablename__ = 'regulation'

    name: Mapped[str] = mapped_column(Text, nullable=False)
    reg_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    part: Mapped[Optional[str]] = mapped_column(Text)
    department_in_charge: Mapped[Optional[str]] = mapped_column(Text)

    regulation_version: Mapped[list['RegulationVersion']] = relationship('RegulationVersion', back_populates='reg')


class Department(Base):
    __tablename__ = 'department'

    faculty_id: Mapped[int] = mapped_column(ForeignKey('faculty.faculty_id'), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    campus: Mapped[str] = mapped_column(Text, nullable=False)
    dept_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    faculty: Mapped['Faculty'] = relationship('Faculty', back_populates='department')
    schedule: Mapped[list['Schedule']] = relationship('Schedule', secondary='schedule_department', back_populates='dept')
    app_user: Mapped[list['AppUser']] = relationship('AppUser', back_populates='dept')
    board: Mapped[list['Board']] = relationship('Board', back_populates='dept')
    department_alias: Mapped[list['DepartmentAlias']] = relationship('DepartmentAlias', back_populates='dept')
    document: Mapped[list['Document']] = relationship('Document', back_populates='dept')
    notice_tag: Mapped[list['NoticeTag']] = relationship('NoticeTag', back_populates='dept')


class EvalQuestion(Base):
    __tablename__ = 'eval_question'

    set_version: Mapped[str] = mapped_column(ForeignKey('eval_set.set_version'), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer_type: Mapped[str] = mapped_column(Text, nullable=False)
    question_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author: Mapped[Optional[str]] = mapped_column(Text)

    eval_set: Mapped['EvalSet'] = relationship('EvalSet', back_populates='eval_question')


class EvalRun(Base):
    __tablename__ = 'eval_run'

    run_at: Mapped[str] = mapped_column(Text, nullable=False)
    index_id: Mapped[int] = mapped_column(ForeignKey('index_config.index_id'), nullable=False)
    set_version: Mapped[str] = mapped_column(ForeignKey('eval_set.set_version'), nullable=False)
    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hit_at_5: Mapped[Optional[float]] = mapped_column(REAL)
    mrr: Mapped[Optional[float]] = mapped_column(REAL)
    ragas_json: Mapped[Optional[str]] = mapped_column(Text)
    failures_json: Mapped[Optional[str]] = mapped_column(Text)

    index: Mapped['IndexConfig'] = relationship('IndexConfig', back_populates='eval_run')
    eval_set: Mapped['EvalSet'] = relationship('EvalSet', back_populates='eval_run')


class RegulationVersion(Base):
    __tablename__ = 'regulation_version'

    reg_id: Mapped[int] = mapped_column(ForeignKey('regulation.reg_id'), nullable=False)
    amend_type: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[str] = mapped_column(Text, nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promulgated_on: Mapped[Optional[str]] = mapped_column(Text)
    effective_to: Mapped[Optional[str]] = mapped_column(Text)
    amend_reason: Mapped[Optional[str]] = mapped_column(Text)

    reg: Mapped['Regulation'] = relationship('Regulation', back_populates='regulation_version')
    addendum: Mapped[list['Addendum']] = relationship('Addendum', back_populates='version')
    annex: Mapped[list['Annex']] = relationship('Annex', back_populates='version')
    article: Mapped[list['Article']] = relationship('Article', back_populates='version')


class Schedule(Base):
    __tablename__ = 'schedule'

    notice_title: Mapped[str] = mapped_column(Text, nullable=False)
    start_at: Mapped[str] = mapped_column(Text, nullable=False)
    all_day: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    schedule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    end_at: Mapped[Optional[str]] = mapped_column(Text)
    place: Mapped[Optional[str]] = mapped_column(Text)
    target_audience: Mapped[Optional[str]] = mapped_column(Text)
    organizer: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    image_path: Mapped[Optional[str]] = mapped_column(Text)
    event_title: Mapped[Optional[str]] = mapped_column(Text)
    board_id: Mapped[Optional[str]] = mapped_column(Text)
    notice_id: Mapped[Optional[str]] = mapped_column(Text)

    dept: Mapped[list['Department']] = relationship('Department', secondary='schedule_department', back_populates='schedule')
    calendar_export: Mapped[list['CalendarExport']] = relationship('CalendarExport', back_populates='schedule')
    notification: Mapped[list['Notification']] = relationship('Notification', back_populates='schedule')


class Addendum(Base):
    __tablename__ = 'addendum'

    version_id: Mapped[int] = mapped_column(ForeignKey('regulation_version.version_id'), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    addendum_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admission_year_from: Mapped[Optional[int]] = mapped_column(Integer)
    admission_year_to: Mapped[Optional[int]] = mapped_column(Integer)

    version: Mapped['RegulationVersion'] = relationship('RegulationVersion', back_populates='addendum')


class Annex(Base):
    __tablename__ = 'annex'

    version_id: Mapped[int] = mapped_column(ForeignKey('regulation_version.version_id'), nullable=False)
    annex_no: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    annex_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(Text)

    version: Mapped['RegulationVersion'] = relationship('RegulationVersion', back_populates='annex')


class AppUser(Base):
    __tablename__ = 'app_user'

    email_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    email_hash: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_access_at: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dept_id: Mapped[Optional[int]] = mapped_column(ForeignKey('department.dept_id'))
    grade: Mapped[Optional[int]] = mapped_column(Integer)
    admission_year: Mapped[Optional[int]] = mapped_column(Integer)
    expected_graduation: Mapped[Optional[str]] = mapped_column(Text)
    deletion_notified_at: Mapped[Optional[str]] = mapped_column(Text)

    dept: Mapped[Optional['Department']] = relationship('Department', back_populates='app_user')
    board: Mapped[list['Board']] = relationship('Board', secondary='user_board', back_populates='user')
    calendar_export: Mapped[list['CalendarExport']] = relationship('CalendarExport', back_populates='user')
    interest_keyword: Mapped[list['InterestKeyword']] = relationship('InterestKeyword', back_populates='user')
    like_place: Mapped[list['LikePlace']] = relationship('LikePlace', back_populates='user')
    notification: Mapped[list['Notification']] = relationship('Notification', back_populates='user')
    session: Mapped[list['Session']] = relationship('Session', back_populates='user')
    user_memory: Mapped[list['UserMemory']] = relationship('UserMemory', back_populates='user')


class Article(Base):
    __tablename__ = 'article'

    version_id: Mapped[int] = mapped_column(ForeignKey('regulation_version.version_id'), nullable=False)
    article_no: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    is_changed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    chapter: Mapped[Optional[str]] = mapped_column(Text)
    effective_from: Mapped[Optional[str]] = mapped_column(Text)
    source_page: Mapped[Optional[int]] = mapped_column(Integer)

    version: Mapped['RegulationVersion'] = relationship('RegulationVersion', back_populates='article')


class Board(Base):
    __tablename__ = 'board'

    name: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    list_url: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_host: Mapped[str] = mapped_column(Text, nullable=False)
    parser_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    last_article_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    board_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    faculty_id: Mapped[Optional[int]] = mapped_column(ForeignKey('faculty.faculty_id'))
    dept_id: Mapped[Optional[int]] = mapped_column(ForeignKey('department.dept_id'))
    last_success_at: Mapped[Optional[str]] = mapped_column(Text)

    dept: Mapped[Optional['Department']] = relationship('Department', back_populates='board')
    faculty: Mapped[Optional['Faculty']] = relationship('Faculty', back_populates='board')
    user: Mapped[list['AppUser']] = relationship('AppUser', secondary='user_board', back_populates='board')
    crawl_run: Mapped[list['CrawlRun']] = relationship('CrawlRun', back_populates='board')
    notice_posting: Mapped[list['NoticePosting']] = relationship('NoticePosting', back_populates='board')


class DepartmentAlias(Base):
    __tablename__ = 'department_alias'

    dept_id: Mapped[int] = mapped_column(ForeignKey('department.dept_id'), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    dept: Mapped['Department'] = relationship('Department', back_populates='department_alias')


class Document(Base):
    __tablename__ = 'document'

    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_table: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[str] = mapped_column(Text, nullable=False)
    trust_level: Mapped[str] = mapped_column(Text, nullable=False)
    doc_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    published_at: Mapped[Optional[str]] = mapped_column(Text)
    dept_id: Mapped[Optional[int]] = mapped_column(ForeignKey('department.dept_id'))
    campus: Mapped[Optional[str]] = mapped_column(Text)

    dept: Mapped[Optional['Department']] = relationship('Department', back_populates='document')
    chunk: Mapped[list['Chunk']] = relationship('Chunk', back_populates='doc')


class NoticeTag(Base):
    __tablename__ = 'notice_tag'

    notice_id: Mapped[int] = mapped_column(ForeignKey('notice.notice_id'), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    faculty_id: Mapped[Optional[int]] = mapped_column(ForeignKey('faculty.faculty_id'))
    dept_id: Mapped[Optional[int]] = mapped_column(ForeignKey('department.dept_id'))

    dept: Mapped[Optional['Department']] = relationship('Department', back_populates='notice_tag')
    faculty: Mapped[Optional['Faculty']] = relationship('Faculty', back_populates='notice_tag')
    notice: Mapped['Notice'] = relationship('Notice', back_populates='notice_tag')


t_schedule_department = Table(
    'schedule_department', Base.metadata,
    Column('schedule_id', ForeignKey('schedule.schedule_id'), primary_key=True),
    Column('dept_id', ForeignKey('department.dept_id'), primary_key=True)
)


class CalendarExport(Base):
    __tablename__ = 'calendar_export'

    user_id: Mapped[int] = mapped_column(ForeignKey('app_user.user_id'), primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey('schedule.schedule_id'), primary_key=True)
    google_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    exported_at: Mapped[str] = mapped_column(Text, nullable=False)

    schedule: Mapped['Schedule'] = relationship('Schedule', back_populates='calendar_export')
    user: Mapped['AppUser'] = relationship('AppUser', back_populates='calendar_export')


class Chunk(Base):
    __tablename__ = 'chunk'

    doc_id: Mapped[int] = mapped_column(ForeignKey('document.doc_id'), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text_: Mapped[str] = mapped_column('text', Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_rule: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    doc: Mapped['Document'] = relationship('Document', back_populates='chunk')


class CrawlRun(Base):
    __tablename__ = 'crawl_run'

    board_id: Mapped[int] = mapped_column(ForeignKey('board.board_id'), nullable=False)
    cycle_started_at: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finished_at: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    board: Mapped['Board'] = relationship('Board', back_populates='crawl_run')


class GoogleConnection(AppUser):
    __tablename__ = 'google_connection'

    google_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    google_email_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('app_user.user_id'), primary_key=True)


class InterestKeyword(Base):
    __tablename__ = 'interest_keyword'

    user_id: Mapped[int] = mapped_column(ForeignKey('app_user.user_id'), nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_norm: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user: Mapped['AppUser'] = relationship('AppUser', back_populates='interest_keyword')


class LikePlace(Base):
    __tablename__ = 'like_place'

    user_id: Mapped[int] = mapped_column(ForeignKey('app_user.user_id'), primary_key=True)
    place_id: Mapped[str] = mapped_column(Text, primary_key=True)
    place_url: Mapped[str] = mapped_column(Text, nullable=False)
    campus: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"))
    memo: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped['AppUser'] = relationship('AppUser', back_populates='like_place')


class NoticePosting(Base):
    __tablename__ = 'notice_posting'

    notice_id: Mapped[int] = mapped_column(ForeignKey('notice.notice_id'), nullable=False)
    board_id: Mapped[int] = mapped_column(ForeignKey('board.board_id'), nullable=False)
    article_no: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False)
    posting_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    board: Mapped['Board'] = relationship('Board', back_populates='notice_posting')
    notice: Mapped['Notice'] = relationship('Notice', back_populates='notice_posting')


class Notification(Base):
    __tablename__ = 'notification'

    user_id: Mapped[int] = mapped_column(ForeignKey('app_user.user_id'), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    notif_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notice_id: Mapped[Optional[int]] = mapped_column(ForeignKey('notice.notice_id'))
    schedule_id: Mapped[Optional[int]] = mapped_column(ForeignKey('schedule.schedule_id'))
    matched_keywords: Mapped[Optional[str]] = mapped_column(Text)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    sent_at: Mapped[Optional[str]] = mapped_column(Text)

    notice: Mapped[Optional['Notice']] = relationship('Notice', back_populates='notification')
    schedule: Mapped[Optional['Schedule']] = relationship('Schedule', back_populates='notification')
    user: Mapped['AppUser'] = relationship('AppUser', back_populates='notification')


class Session(Base):
    __tablename__ = 'session'

    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('app_user.user_id'))
    title: Mapped[Optional[str]] = mapped_column(Text)
    expired_at: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[Optional['AppUser']] = relationship('AppUser', back_populates='session')
    message: Mapped[list['Message']] = relationship('Message', back_populates='session')


t_user_board = Table(
    'user_board', Base.metadata,
    Column('user_id', ForeignKey('app_user.user_id'), primary_key=True),
    Column('board_id', ForeignKey('board.board_id'), primary_key=True)
)


class Message(Base):
    __tablename__ = 'message'

    session_id: Mapped[str] = mapped_column(ForeignKey('session.session_id'), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[Optional[str]] = mapped_column(Text)

    session: Mapped['Session'] = relationship('Session', back_populates='message')
    retrieval: Mapped[list['Retrieval']] = relationship('Retrieval', back_populates='message')
    tool_call: Mapped[list['ToolCall']] = relationship('ToolCall', back_populates='message')
    user_memory: Mapped[list['UserMemory']] = relationship('UserMemory', back_populates='source_message')


class Retrieval(Base):
    __tablename__ = 'retrieval'

    message_id: Mapped[int] = mapped_column(ForeignKey('message.message_id'), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filter_json: Mapped[str] = mapped_column(Text, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    searched_at: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    index_id: Mapped[Optional[int]] = mapped_column(ForeignKey('index_config.index_id'))

    index: Mapped[Optional['IndexConfig']] = relationship('IndexConfig', back_populates='retrieval')
    message: Mapped['Message'] = relationship('Message', back_populates='retrieval')
    retrieval_hit: Mapped[list['RetrievalHit']] = relationship('RetrievalHit', back_populates='retrieval')


class ToolCall(Base):
    __tablename__ = 'tool_call'

    message_id: Mapped[int] = mapped_column(ForeignKey('message.message_id'), nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[int] = mapped_column(Integer, nullable=False)
    called_at: Mapped[str] = mapped_column(Text, nullable=False)
    call_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result_summary: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    message: Mapped['Message'] = relationship('Message', back_populates='tool_call')


class UserMemory(Base):
    __tablename__ = 'user_memory'

    user_id: Mapped[int] = mapped_column(ForeignKey('app_user.user_id'), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    memory_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey('message.message_id'))

    source_message: Mapped[Optional['Message']] = relationship('Message', back_populates='user_memory')
    user: Mapped['AppUser'] = relationship('AppUser', back_populates='user_memory')


class RetrievalHit(Base):
    __tablename__ = 'retrieval_hit'

    retrieval_id: Mapped[int] = mapped_column(ForeignKey('retrieval.retrieval_id'), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(REAL, nullable=False)
    adopted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))

    retrieval: Mapped['Retrieval'] = relationship('Retrieval', back_populates='retrieval_hit')
