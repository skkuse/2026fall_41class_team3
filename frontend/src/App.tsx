import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { AppModal } from "./components/AppModal";
import { Button } from "./components/ui/button";
import { Info, UserRoundCog } from "lucide-react";
import { LoginDialog, ProfileDialog } from "./auth/AuthDialogs";
import { departments, getSession, logout, type Session } from "./auth/api";
import { ApiError } from "./lib/http";
import { calendarPreview, softwareDepartment } from "./calendar/previewData";
import { getCalendarReturn, returnKey } from "./calendar/googleReturn";

const CalendarPage = lazy(() => import("./calendar/CalendarPage"));

const loginButton =
  "min-w-[76px] cursor-pointer rounded-[5px] border-0 bg-[#18212d] px-3.5 py-2 text-[12px] text-white transition-colors duration-150 hover:bg-[#2b394a] disabled:opacity-60 max-[600px]:min-w-[66px]";
const tabIcon =
  "size-[18px] shrink-0 fill-none stroke-current [stroke-width:1.7] [stroke-linecap:round] [stroke-linejoin:round]";

type Tab = "chat" | "map" | "calendar";

const tabs: { id: Tab; label: string }[] = [
  { id: "chat", label: "채팅" },
  { id: "map", label: "학교 주변 지도" },
  { id: "calendar", label: "학과 일정" },
];

function TabIcon({ tab }: { tab: Tab }) {
  if (tab === "chat") {
    return (
      <svg className={tabIcon} viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 5.75A2.75 2.75 0 0 1 7.75 3h8.5A2.75 2.75 0 0 1 19 5.75v7.5A2.75 2.75 0 0 1 16.25 16H11l-4.5 3v-3.2A2.75 2.75 0 0 1 5 13.25z" />
        <path d="M8.5 8.5h7M8.5 11.5h4" />
      </svg>
    );
  }

  if (tab === "map") {
    return (
      <svg className={tabIcon} viewBox="0 0 24 24" aria-hidden="true">
        <path d="m3.5 6 5-2 7 2 5-2v14l-5 2-7-2-5 2z" />
        <path d="M8.5 4v14M15.5 6v14" />
        <path d="M12 9.5a2 2 0 1 0-4 0c0 1.5 2 3.5 2 3.5s2-2 2-3.5Z" />
      </svg>
    );
  }

  return (
    <svg className={tabIcon} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M8 3v4M16 3v4M4 10h16M8 14h2M14 14h2M8 17h2" />
    </svg>
  );
}

function App() {
  const [restored] = useState(getCalendarReturn);
  const [googleStatus] = useState(() =>
    new URLSearchParams(window.location.search).get("google_calendar"),
  );
  const [activeTab, setActiveTab] = useState<Tab>(
    restored || googleStatus ? "calendar" : "chat",
  );
  const [calendarVisited, setCalendarVisited] = useState(
    activeTab === "calendar",
  );
  const [session, setSession] = useState<Session>();
  const [dialog, setDialog] = useState<
    "login" | "onboarding" | "settings" | "logout"
  >();
  const [accountName, setAccountName] = useState<{
    id: number;
    name: string;
  }>();
  const [loggingOut, setLoggingOut] = useState(false);
  const [accountError, setAccountError] = useState("");
  const user = session?.user;
  const departmentId = user?.department_id;

  useEffect(() => {
    const controller = new AbortController();
    getSession(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setSession(data);
        if (data.user && data.needs_onboarding) setDialog("onboarding");
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setSession({ user: null, needs_onboarding: false });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (departmentId == null) return;
    const controller = new AbortController();
    departments(controller.signal)
      .then(({ items }) => {
        const department = items.find(({ id }) => id === departmentId);
        if (department && !controller.signal.aborted)
          setAccountName(department);
      })
      .catch(() => {
        /* The session remains usable without the department name. */
      });
    return () => controller.abort();
  }, [departmentId]);

  const requireLogin = useCallback(() => {
    setSession({ user: null, needs_onboarding: false });
    setDialog("login");
  }, []);

  async function signOut() {
    if (loggingOut) return;
    setLoggingOut(true);
    setAccountError("");
    try {
      await logout();
      setSession({ user: null, needs_onboarding: false });
      setDialog(undefined);
      setActiveTab("chat");
    } catch (error) {
      setAccountError(
        error instanceof ApiError
          ? error.message
          : "로그아웃에 실패했습니다. 다시 시도해 주세요.",
      );
    } finally {
      setLoggingOut(false);
    }
  }

  useEffect(() => {
    if (restored) sessionStorage.removeItem(returnKey);
    if (googleStatus) {
      const url = new URL(window.location.href);
      url.searchParams.delete("google_calendar");
      window.history.replaceState(window.history.state, "", url);
    }
  }, [restored, googleStatus]);

  const googleNotice =
    googleStatus === "connected"
      ? "Google 계정이 연결되었습니다. 일정 상세에서 추가 버튼을 다시 눌러 주세요."
      : googleStatus === "denied"
        ? "Google 계정 연결이 취소되었습니다."
        : googleStatus
          ? "Google 계정을 연결하지 못했습니다."
          : restored
            ? "일정 상세에서 다시 추가해 Google 계정 연결 상태를 확인해 주세요."
            : "";
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-white pt-16 max-[600px]:pt-[58px]">
      <header className="fixed inset-x-0 top-0 z-30 flex h-16 items-center justify-between bg-white/90 px-[34px] backdrop-blur-sm max-[600px]:h-[58px] max-[600px]:px-[18px]">
        <a
          className="inline-flex items-center gap-[9px] text-[14px] font-[650] tracking-[0.035em] text-[#3a4541] no-underline"
          href="/"
          aria-label="SKKU MATE 홈"
        >
          <span className="text-[13px] text-[#53625d]" aria-hidden="true">
            ◆
          </span>
          <span>SKKU MATE</span>
        </a>
        <div className="flex min-w-0 items-center gap-2.5">
          {user ? (
            <>
              <div className="grid min-w-0 gap-[3px] text-right text-[12px] [&>span]:truncate [&>strong]:truncate">
                <strong>{user.email}</strong>
                {departmentId == null ? (
                  <span>학과 미설정</span>
                ) : (
                  accountName?.id === departmentId && (
                    <span>{accountName.name}</span>
                  )
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="bg-transparent text-[#18212d] hover:bg-icon-hover hover:text-neutral-700"
                aria-label="계정 설정"
                disabled={loggingOut}
                onClick={() => setDialog("settings")}
              >
                <UserRoundCog className="size-5" aria-hidden="true" />
              </Button>
              <button
                className={loginButton}
                type="button"
                disabled={loggingOut}
                onClick={() => {
                  setAccountError("");
                  setDialog("logout");
                }}
              >
                Logout
              </button>
            </>
          ) : (
            <button
              className={loginButton}
              type="button"
              disabled={!session}
              onClick={() => setDialog("login")}
            >
              Login
            </button>
          )}
        </div>
      </header>

      <div className="flex min-h-[calc(100vh-64px)] flex-1 max-[600px]:min-h-[calc(100vh-58px)]">
        <aside
          className={`shrink-0 bg-[#5b9982] bg-[radial-gradient(rgba(255,255,255,0.12)_0.65px,transparent_0.65px)] bg-size-[4px_4px] py-[18px] transition-[width,flex-basis] duration-[180ms] max-[600px]:w-[62px] max-[600px]:px-[7px] max-[600px]:py-3.5 ${isCollapsed ? "w-[68px] px-[9px]" : "w-[190px] px-3"}`}
          aria-label="주 메뉴"
        >
          <button
            className={`mb-3 flex h-9 w-full cursor-pointer items-center rounded-[5px] border-0 bg-transparent text-[18px] text-[#183b31] hover:bg-white/12 max-[600px]:justify-center max-[600px]:px-0 ${isCollapsed ? "justify-center px-0" : "justify-end px-3"}`}
            type="button"
            aria-label={isCollapsed ? "메뉴 펼치기" : "메뉴 접기"}
            aria-expanded={!isCollapsed}
            onClick={() => setIsCollapsed((collapsed) => !collapsed)}
          >
            <span aria-hidden="true">{isCollapsed ? "»" : "«"}</span>
          </button>

          <nav className="flex flex-col gap-[7px]">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                className={`flex min-h-[42px] w-full cursor-pointer items-center gap-3 overflow-hidden rounded-md border-0 text-left text-[13px] whitespace-nowrap transition-colors duration-[140ms] max-[600px]:justify-center max-[600px]:px-0 ${isCollapsed ? "justify-center px-0" : "px-3"} ${activeTab === tab.id ? "bg-white text-[#34443e] shadow-[0_2px_6px_rgba(22,56,44,0.12)]" : "bg-transparent text-white hover:bg-white/16"}`}
                type="button"
                aria-label={tab.label}
                aria-current={activeTab === tab.id ? "page" : undefined}
                title={isCollapsed ? tab.label : undefined}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id === "calendar") setCalendarVisited(true);
                }}
              >
                <TabIcon tab={tab.id} />
                <span
                  className={
                    isCollapsed ? "hidden" : "truncate max-[600px]:hidden"
                  }
                >
                  {tab.label}
                </span>
              </button>
            ))}
          </nav>
        </aside>

        <main
          className="min-w-0 flex-1 bg-white"
          aria-label={`${tabs.find((tab) => tab.id === activeTab)?.label} 화면`}
        >
          {calendarVisited && (
            <div hidden={activeTab !== "calendar"}>
              {!session && !calendarPreview && !restored ? (
                <p
                  className="my-3 rounded-md border border-solid border-calendar-border bg-white px-3 py-2.5 text-[0.84rem] text-[#252525]"
                  role="status"
                >
                  로그인 상태를 확인하는 중입니다.
                </p>
              ) : (
                <Suspense
                  fallback={<p role="status">달력을 불러오는 중입니다.</p>}
                >
                  <CalendarPage
                    defaultId={
                      calendarPreview
                        ? softwareDepartment.departmentId
                        : (user?.department_id ?? null)
                    }
                    visible={activeTab === "calendar"}
                    restored={restored}
                    googleNotice={googleNotice}
                    onLogin={requireLogin}
                  />
                </Suspense>
              )}
            </div>
          )}
        </main>
      </div>
      {dialog === "logout" && user && (
        <AppModal
          title="로그아웃하시겠어요?"
          headerIcon={
            <Info
              className="mb-2 size-9 text-primary"
              strokeWidth={1.75}
              aria-hidden="true"
            />
          }
          description="로그아웃하면 다음 로그인 시 교내 이메일 인증이 필요해요."
          className="max-w-[min(420px,calc(100%-2rem))] gap-7 rounded-2xl p-[clamp(24px,6vw,32px)] text-[#111] [&_[data-slot=dialog-description]]:m-0"
          showCloseButton={false}
          onClose={() => {
            if (!loggingOut) setDialog(undefined);
          }}
        >
          {accountError && (
            <p className="m-0 text-sm text-destructive" role="alert">
              {accountError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={loggingOut}
              className="bg-transparent text-neutral-600 hover:bg-icon-hover hover:text-neutral-800"
              onClick={() => setDialog(undefined)}
            >
              취소
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={loggingOut}
              className="bg-transparent font-semibold text-primary hover:bg-icon-hover hover:text-primary"
              onClick={() => void signOut()}
            >
              {loggingOut ? "로그아웃 중…" : "로그아웃"}
            </Button>
          </div>
        </AppModal>
      )}
      {dialog === "login" && (
        <LoginDialog
          onClose={() => setDialog(undefined)}
          onVerified={(data) => {
            setSession(data);
            setDialog(data.needs_onboarding ? "onboarding" : undefined);
          }}
        />
      )}
      {(dialog === "settings" || dialog === "onboarding") && user && (
        <ProfileDialog
          mode={dialog}
          onClose={() => setDialog(undefined)}
          onUnauthorized={requireLogin}
          onSaved={(user) => {
            setSession({ user, needs_onboarding: false });
            setDialog(undefined);
          }}
        />
      )}
    </div>
  );
}

export default App;
