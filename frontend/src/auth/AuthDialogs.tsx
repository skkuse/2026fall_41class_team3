import { useEffect, useRef, useState, type FormEvent } from "react";
import { ChevronLeft, Mail } from "lucide-react";
import { Button } from "../components/ui/button";
import { AppModal } from "../components/AppModal";
import { NativeSelect } from "../components/ui/native-select";
import { ApiError } from "../lib/http";
import {
  departments,
  getProfile,
  interests,
  saveProfile,
  sendCode,
  verifyCode,
  type CatalogItem,
  type Session,
  type User,
} from "./api";

const authDialog =
  "max-h-[calc(100dvh-2rem)] max-w-[min(430px,calc(100%-2rem))] gap-6 overflow-auto p-[clamp(24px,5vw,32px)] text-[#111] [&_[data-slot=dialog-description]]:m-0 [&_[data-slot=dialog-description]]:leading-normal [&_[data-slot=dialog-description]]:wrap-anywhere";
const authInput =
  "h-9 w-full min-w-0 rounded-md border border-solid border-input bg-white px-2.5 text-[0.875rem] text-[#111] [font-family:inherit] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring";
const fieldLabel = "text-[0.85rem] font-[650]";
const submitButton = "mt-1.5 min-h-[42px] rounded-full";
const codeAction = "min-h-[42px] min-w-0 rounded-full px-[5px]";

const domains = ["skku.edu", "g.skku.edu"];
const recoveryMessage =
  "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";

function secondsLeft(deadline: number, now: number) {
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

function countdown(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function LoginDialog({
  onClose,
  onVerified,
}: {
  onClose: () => void;
  onVerified: (session: Session) => void;
}) {
  const [step, setStep] = useState<"email" | "code">("email");
  const [studentId, setStudentId] = useState("");
  const [domain, setDomain] = useState(0);
  const [code, setCode] = useState("");
  const [expiresAt, setExpiresAt] = useState(0);
  const [resends, setResends] = useState<Record<string, number>>({});
  const [now, setNow] = useState(Date.now);
  const [blocked, setBlocked] = useState(false);
  const [pending, setPending] = useState<"send" | "verify">();
  const [inlineError, setInlineError] = useState("");
  const [notice, setNotice] = useState<{ message: string; close?: boolean }>();
  const activeRequest = useRef<AbortController | null>(null);
  const codeInput = useRef<HTMLInputElement>(null);
  const address = { student_id: studentId.trim(), domain };
  const addressKey = `${address.student_id.toLowerCase()}@${domains[domain]}`;
  const remaining = secondsLeft(expiresAt, now);
  const wait = secondsLeft(resends[addressKey] ?? 0, now);

  useEffect(() => () => activeRequest.current?.abort(), []);
  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(interval);
  }, []);
  useEffect(() => {
    if (step === "code") codeInput.current?.focus();
  }, [step]);

  function retryAfter(seconds: number) {
    const time = Date.now();
    setNow(time);
    setResends((deadlines) => ({
      ...deadlines,
      [addressKey]: time + seconds * 1000,
    }));
  }

  async function submit(
    event: { preventDefault: () => void },
    action: "send" | "verify",
  ) {
    event.preventDefault();
    if (activeRequest.current || !address.student_id) return;
    if (action === "send" && Date.now() < (resends[addressKey] ?? 0)) return;
    if (
      action === "verify" &&
      (code.length !== 6 || blocked || Date.now() >= expiresAt)
    )
      return;

    const controller = new AbortController();
    activeRequest.current = controller;
    setPending(action);
    setInlineError("");
    try {
      if (action === "send") {
        const response = await sendCode(address, controller.signal);
        if (controller.signal.aborted) return;
        retryAfter(response.resend_after);
        setExpiresAt(Date.now() + response.expires_in * 1000);
        setBlocked(false);
        setCode("");
        setStep("code");
        codeInput.current?.focus();
      } else {
        const session = await verifyCode(address, code, controller.signal);
        if (!controller.signal.aborted) onVerified(session);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      if (
        !(error instanceof ApiError) ||
        (error.status >= 500 && error.status !== 502)
      ) {
        setNotice({
          message: error instanceof ApiError ? error.message : recoveryMessage,
          close: true,
        });
      } else if (error.body.code === "INVALID_CODE") {
        setCode("");
        setInlineError("인증번호가 올바르지 않습니다.");
        requestAnimationFrame(() => codeInput.current?.focus());
      } else if (error.body.code === "RATE_LIMITED") {
        retryAfter(error.body.retry_after ?? 0);
        setNotice({ message: error.message });
      } else if (
        error.body.code === "TOO_MANY_ATTEMPTS" ||
        error.body.code === "CODE_EXPIRED"
      ) {
        setBlocked(true);
        setNotice({ message: error.message });
      } else if (error.status === 502) {
        setNotice({ message: error.message });
      } else {
        setInlineError(error.message);
      }
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
      if (!controller.signal.aborted) setPending(undefined);
    }
  }

  const resendLabel =
    wait > 0
      ? wait >= 60
        ? `${Math.ceil(wait / 60)}분 후`
        : `${wait}초 후`
      : "";
  const dismissNotice = () => {
    if (notice?.close) onClose();
    else setNotice(undefined);
  };

  return (
    <AppModal
      className={authDialog}
      title={step === "email" ? "교내 이메일로 로그인" : "인증번호 입력"}
      leadingAction={
        step === "code" && (
          <button
            type="button"
            className="grid size-10 cursor-pointer place-items-center border-0 bg-transparent p-0 text-[#252525] hover:text-neutral-500 focus-visible:rounded-sm focus-visible:outline-2 focus-visible:-outline-offset-3 focus-visible:outline-primary disabled:cursor-default disabled:opacity-45"
            aria-label="이메일 입력으로 돌아가기"
            disabled={Boolean(pending)}
            onClick={() => {
              setStep("email");
              setInlineError("");
              setCode("");
            }}
          >
            <ChevronLeft size={24} aria-hidden="true" />
          </button>
        )
      }
      description={
        step === "email"
          ? "성균관대학교 이메일로 인증번호를 받으세요."
          : `${addressKey}로 보낸 6자리 인증번호를 입력해 주세요.`
      }
      onClose={onClose}
    >
      <form
        className="grid gap-3"
        onSubmit={(event) =>
          void submit(event, step === "email" ? "send" : "verify")
        }
      >
        {step === "email" ? (
          <>
            <label className={fieldLabel} htmlFor="auth-student-id">
              교내 이메일
            </label>
            <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,138px)] items-center gap-2">
              <input
                className={authInput}
                id="auth-student-id"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="교내 ID"
                value={studentId}
                disabled={Boolean(pending)}
                onChange={(event) => {
                  setStudentId(event.target.value);
                  setInlineError("");
                }}
              />
              <span aria-hidden="true">@</span>
              <NativeSelect
                aria-label="이메일 도메인"
                value={domain}
                disabled={Boolean(pending)}
                onChange={(event) => {
                  setDomain(Number(event.target.value));
                  setInlineError("");
                }}
              >
                {domains.map((name, id) => (
                  <option key={name} value={id}>
                    {name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {inlineError && (
              <p className="m-0 text-[0.84rem] text-destructive" role="alert">
                {inlineError}
              </p>
            )}
            <Button
              type="submit"
              className={submitButton}
              disabled={!studentId.trim() || Boolean(pending) || wait > 0}
            >
              <Mail aria-hidden="true" />
              {pending
                ? "요청 중…"
                : resendLabel
                  ? `인증번호 요청 · ${resendLabel}`
                  : "인증번호 요청"}
            </Button>
          </>
        ) : (
          <>
            <label className={fieldLabel} htmlFor="auth-code">
              인증번호
            </label>
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
              <input
                className={`${authInput} tracking-[0.3em] tabular-nums`}
                ref={codeInput}
                id="auth-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                value={code}
                disabled={blocked || remaining === 0 || Boolean(pending)}
                onChange={(event) => {
                  setCode(
                    event.target.value.replace(/[^0-9]/g, "").slice(0, 6),
                  );
                  setInlineError("");
                }}
              />
              <span
                className="min-w-[3ch] text-[0.84rem] text-destructive tabular-nums"
                aria-label="남은 인증 시간"
              >
                {countdown(remaining)}
              </span>
            </div>
            {inlineError && (
              <p className="m-0 text-[0.84rem] text-destructive" role="alert">
                {inlineError}
              </p>
            )}
            {(blocked || remaining === 0) && (
              <p className="m-0 text-[0.84rem] text-destructive" role="status">
                인증번호를 다시 요청해 주세요.
              </p>
            )}
            <div className="mt-1.5 grid grid-cols-2 gap-2">
              <Button
                type="button"
                variant="outline"
                className={codeAction}
                disabled={wait > 0 || Boolean(pending)}
                onClick={(event) => void submit(event, "send")}
              >
                {pending === "send"
                  ? "요청 중…"
                  : resendLabel
                    ? `재전송 · ${resendLabel}`
                    : "인증번호 재전송"}
              </Button>
              <Button
                type="submit"
                className={codeAction}
                disabled={
                  code.length !== 6 ||
                  blocked ||
                  remaining === 0 ||
                  Boolean(pending)
                }
              >
                {pending === "verify" ? "확인 중…" : "인증 확인"}
              </Button>
            </div>
          </>
        )}
      </form>
      {notice && (
        <AppModal
          className={authDialog}
          title="인증 안내"
          description={notice.message}
          onClose={dismissNotice}
        >
          <Button onClick={dismissNotice}>확인</Button>
        </AppModal>
      )}
    </AppModal>
  );
}

export function ProfileDialog({
  mode,
  onClose,
  onSaved,
  onUnauthorized,
}: {
  mode: "onboarding" | "settings";
  onClose: () => void;
  onSaved: (user: User) => void;
  onUnauthorized: () => void;
}) {
  const [options, setOptions] = useState<{
    departments: CatalogItem[];
    interests: CatalogItem[];
  }>();
  const [department, setDepartment] = useState("");
  const [keywords, setKeywords] = useState<number[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [catalogError, setCatalogError] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      departments(controller.signal),
      interests(controller.signal),
      mode === "settings" ? getProfile(controller.signal) : null,
    ])
      .then(([departmentResponse, interestResponse, profile]) => {
        if (controller.signal.aborted) return;
        setOptions({
          departments: departmentResponse.items,
          interests: interestResponse.items,
        });
        if (profile) {
          setDepartment(
            profile.user.department_id == null
              ? ""
              : String(profile.user.department_id),
          );
          setKeywords(profile.interests);
        }
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) onUnauthorized();
        else setCatalogError(true);
      });
    return () => controller.abort();
  }, [attempt, mode, onUnauthorized]);
  useEffect(() => () => activeRequest.current?.abort(), []);

  function reload() {
    setOptions(undefined);
    setCatalogError(false);
    setAttempt((value) => value + 1);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!options || !department || activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setPending(true);
    setError("");
    try {
      const response = await saveProfile(
        Number(department),
        keywords,
        controller.signal,
      );
      if (!controller.signal.aborted) onSaved(response.user);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      else if (error instanceof ApiError && error.status === 422) {
        setError(error.message);
        setDepartment("");
        setKeywords([]);
        reload();
      } else
        setError(error instanceof ApiError ? error.message : recoveryMessage);
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return (
    <AppModal
      className={
        mode === "settings"
          ? `${authDialog} gap-7 p-[clamp(28px,7vw,36px)] [&_[data-slot=dialog-title]]:text-[1.3rem]`
          : authDialog
      }
      title={mode === "settings" ? "계정 설정" : "기본 정보 설정"}
      description="소속 학과와 관심 키워드를 선택해 주세요."
      onClose={() => {
        if (!activeRequest.current) onClose();
      }}
    >
      {catalogError ? (
        <div className="grid gap-3">
          <p className="m-0 text-[0.84rem] text-destructive" role="alert">
            설정 정보를 불러오지 못했습니다.
          </p>
          <Button variant="outline" onClick={reload}>
            다시 시도
          </Button>
        </div>
      ) : !options ? (
        <p role="status">선택 목록을 불러오는 중입니다.</p>
      ) : (
        <form
          className={mode === "settings" ? "grid gap-4" : "grid gap-3"}
          onSubmit={submit}
        >
          <label className={fieldLabel} htmlFor="auth-department">
            소속 학과
          </label>
          <NativeSelect
            id="auth-department"
            value={department}
            disabled={pending}
            onChange={(event) => setDepartment(event.target.value)}
          >
            <option value="">학과를 선택해 주세요</option>
            {options.departments.map(({ id, name }) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </NativeSelect>
          {options.interests.length > 0 && (
            <fieldset className="mx-0 my-1 min-w-0 border-0 p-0">
              <legend className={`${fieldLabel} mb-2 p-0`}>
                관심 키워드{" "}
                <span className="font-normal text-[#555]">(선택)</span>
              </legend>
              <div className="flex flex-wrap gap-1.5">
                {options.interests.map(({ id, name }) => {
                  const selected = keywords.includes(id);
                  return (
                    <Button
                      key={id}
                      type="button"
                      variant="outline"
                      size="sm"
                      className="transition-none enabled:hover:bg-[#ececec] enabled:hover:text-[#111] aria-pressed:border-[#111] aria-pressed:bg-[#111] aria-pressed:text-white aria-pressed:enabled:hover:border-[#3b3b3b] aria-pressed:enabled:hover:bg-[#3b3b3b] aria-pressed:enabled:hover:text-white"
                      aria-pressed={selected}
                      disabled={pending}
                      onClick={() =>
                        setKeywords((current) =>
                          selected
                            ? current.filter((keyword) => keyword !== id)
                            : [...current, id],
                        )
                      }
                    >
                      {name}
                    </Button>
                  );
                })}
              </div>
            </fieldset>
          )}
          <Button
            type="submit"
            className={submitButton}
            disabled={!department || pending}
          >
            {pending ? "저장 중…" : "저장"}
          </Button>
        </form>
      )}
      {error && (
        <p className="m-0 text-[0.84rem] text-destructive" role="alert">
          {error}
        </p>
      )}
    </AppModal>
  );
}
