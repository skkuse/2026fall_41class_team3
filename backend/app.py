"""백엔드 서버 진입점. 모든 라우트(api/)를 한 Flask 앱에 묶어서 띄운다.

실행 (backend/ 에서, 가상환경을 켠 상태):
    flask --app app run --debug --port 5000
"""
import os
from dotenv import load_dotenv
load_dotenv()   # .env 파일의 값을 환경변수(os.environ)로 전환

from flask import Flask  # noqa: E402
from api import register_api  # noqa: E402
# 아래 import 경로는 backend/ 폴더에서 서버를 실행하는 기준 (api, services 와 같은 방식).
from db import get_engine, init_db  # noqa: E402


def create_app() -> Flask:
    app = Flask(__name__)

    # --- 설정 -------------------------------------------------------------
    # SECRET_KEY: 세션 쿠키 서명과 인증 코드 해시 용. 없으면 register_api 시작 단계에서 오류 발생
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "")

    # 개발 전용: 이 id의 사용자로 로그인한 것처럼 동작 (debug 모드에서만 적용). 평소에는 공란
    fake_user_id = os.environ.get("DEV_FAKE_USER_ID")
    if fake_user_id:
        app.config["DEV_FAKE_USER_ID"] = int(fake_user_id)

    # --- DB 초기화 ----------------------------------------------------------
    # 빈 DB면 schema.sql을 실행해 테이블을 만들고, 이미 있으면 그대로 둔다.
    # 파일 위치는 .env의 DB_PATH (backend/ 에서 실행하므로 ../data/app.db 는 저장소 루트의 data/app.db).
    # 초기 데이터(학과, 관심사 등)는 서버와 별개로 처음 한 번만 생성 (저장소 루트에서):
    #     python -m backend.db.seed_data
    init_db(get_engine())

    # --- [미확정] 에이전트 준비 ----------------------------------------------
    # 에이전트(LangChain, OpenAI)를 서버 시작 때 한 번 만들어 둘 거라면 여기서 초기화한다.
    # 요청마다 만드는 구조라면 필요 없다. 필요한 것: OPENAI_API_KEY 등 .env 키, 초기화 함수.

    # --- 라우트 등록 --------------------------------------------------------
    # 세션 설정, 오류 핸들러, 모든 Blueprint(auth, me, catalog, chat, 이후 map 등)를 등록한다.
    register_api(app)

    return app


app = create_app()