"""로그인 관련 상수. 값은 팀이 확정하기 전의 제안값이다."""

# 인증 코드
CODE_LENGTH = 6              # 숫자 코드 자리수
CODE_TTL_SEC = 180           # 코드 유효 시간 (3분)
MAX_ATTEMPTS = 5             # 코드 확인 최대 시도 횟수

# 발송 제한
RESEND_COOLDOWN_SEC = 10     # 같은 이메일로 재발송할 수 있는 최소 간격
SEND_LIMIT_PER_WINDOW = 5    # 이메일 하나가 한 구간 안에 받을 수 있는 코드 수
SEND_WINDOW_SEC = 3600       # 발송 횟수를 세는 구간 길이 (1시간)

# 교내 이메일 도메인. FE는 이 코드(0, 1)만 보내고 서버가 "{교내 ID}@{도메인}"으로 조립한다.
# 표에 없는 코드는 거절하므로 이 표가 곧 도메인 검사다.
EMAIL_DOMAINS = {0: "skku.edu", 1: "g.skku.edu"}

# 교내 ID(메일 주소의 @ 앞부분) 형식. 소문자로 바꾼 뒤 검사한다. '+'와 '@'는 허용하지 않는다.
# 실제 교내 ID 형식에 맞춰 수정할 것 (현재는 가정값).
STUDENT_ID_PATTERN = r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?"

# 세션 쿠키 유효 기간 (일). app.config["PERMANENT_SESSION_LIFETIME"]에 연결한다.
SESSION_LIFETIME_DAYS = 7
