"""api 패키지 진입점: 앱 설정과 오류 핸들러, 모든 Blueprint를 한 번에 등록한다."""
import os
from datetime import timedelta

from api.auth import settings as auth_cfg
from api.errors import register_error_handlers


def _configure_session(app) -> None:
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY가 설정되지 않았습니다 (세션 서명과 인증 코드 해시에 사용).")
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(days=auth_cfg.SESSION_LIFETIME_DAYS),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",   # 로컬 http 개발은 COOKIE_SECURE=0
    )


def register_api(app) -> None:
    from api.auth.catalog import bp as catalog_bp
    from api.auth.me import bp as me_bp
    from api.auth.routes import bp as auth_bp
    from api.chat import bp as chat_bp
    from api.map_places import bp as map_places_bp

    _configure_session(app)
    register_error_handlers(app)
    for bp in (auth_bp, me_bp, catalog_bp, chat_bp, map_places_bp):
        app.register_blueprint(bp)