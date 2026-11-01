import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  LabelList,
} from "recharts";
import { Eye, EyeSlash, LayoutDashboard, Radio, Settings, Download, Search, ArrowUpRight, TriangleAlert, ChevronRight, LogOut, CalendarDays, Activity, Check, Close, Bell, Menu, Star, PlatformIcon } from "./icons";
// @ts-ignore: CSS is handled by the bundler and has no TypeScript declarations.
import "bootstrap/dist/css/bootstrap.min.css";
// @ts-ignore: CSS is handled by the bundler and has no TypeScript declarations.
import "./style.css";

type Source = {
  platform: string;
  source: string;
  status: string;
  last_synced_at: string | null;
  error?: string;
};
type Session = { role: string; email: string; name: string };
type Rollup = {
  date: string;
  platform?: string;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  mixed_count: number;
  total_count: number;
  negativity_index: number;
};
type Post = {
  _id: string;
  external_id: string;
  platform: string;
  author: string;
  content: string;
  url: string;
  media_url?: string;
  media_type?: string;
  thumbnail_url?: string;
  published_at: string;
  engagement: {
    likes: number;
    comments: number;
    shares: number;
    views: number;
  };
  engagement_score: number;
  sentiment: {
    label: string;
    confidence: number;
    reason: string;
    model_used: string;
    language?: "hi" | "en" | "hinglish";
    targets?: string[];
    review_required?: boolean;
  } | null;
  classification_status?: string;
};
type Alert = {
  date: string;
  negative_count: number;
  threshold: number;
  top_negative_posts: Post[];
  platform_breakdown: Record<string, number>;
  notified_channels: string[];
  notification_errors?: Record<string, string>;
};
type Overview = {
  date: string;
  selected_date?: string;
  timezone: string;
  sources: Source[];
  today: Rollup | null;
  selected?: Rollup | null;
  trend: Rollup[];
  platform_totals: Rollup[];
  news_channel_totals?: {
    channel: string;
    positive_count: number;
    negative_count: number;
    historical_count: number;
    historical_top_ten: boolean;
  }[];
  top_topics?: {
    topic: string;
    count: number;
    positive_count: number;
    negative_count: number;
    neutral_count: number;
    mixed_count: number;
  }[];
  top_x_voices?: {
    author: string;
    username: string;
    avatar_url: string;
    post_count: number;
    engagement: number;
    positive_count: number;
    negative_count: number;
    neutral_count: number;
    mixed_count: number;
  }[];
  active_project?: string;
  monitoring_projects?: { id: string; label: string; keywords: string[] }[];
  pending: number;
  threshold: number;
  partial: boolean;
  sync_running?: boolean;
  schedule?: {
    enabled: boolean;
    frequent: SyncScheduleItem | null;
    social: SyncScheduleItem | null;
  };
  classifier: {
    status: string;
    model: string;
    threshold?: number;
    fallback_model?: string;
    fallback_configured?: boolean;
  };
  alerts: Alert[];
};
type SyncScheduleItem = {
  label: string;
  interval_seconds: number;
  next_run_at: string | null;
};
const newsChannelDomains: Record<string, string> = {
  News18: "news18.com",
  "Zee Bihar": "zeenews.india.com",
  "ABP Bihar": "abplive.com",
  "News State": "newsstate.com",
  "Sahara Samay": "saharasamay.com",
  "Bihar Tak": "aajtak.in",
  "First Bihar": "firstbihar.com",
  "Live Cities": "livecities.news",
  News4Nation: "news4nation.com",
  "Hindustani Media": "hindustanimedia.in",
  "Dainik Jagran Bihar": "jagran.com",
  "TV9 Bihar/Jharkhand": "tv9hindi.com",
  "Dainik Bhaskar Bihar": "bhaskar.com",
  "Prabhat Khabar": "prabhatkhabar.com",
  "Live Hindustan Bihar": "livehindustan.com",
  "ETV Bharat Bihar": "etvbharat.com",
  "Navbharat Times Bihar": "navbharattimes.indiatimes.com",
  "Aaj Tak": "aajtak.in",
  "India Today": "indiatoday.in",
  "NDTV India": "ndtv.in",
  "Republic Bharat": "republicbharat.com",
  "CNN-News18": "news18.com",
  News24: "news24online.com",
  Bharat24: "bharat24live.com",
  "DD News": "newsonair.gov.in",
  ANI: "aninews.in",
  PTI: "ptinews.com",
  "Amar Ujala": "amarujala.com",
  Jansatta: "jansatta.com",
  "Oneindia Hindi": "hindi.oneindia.com",
  "Punjab Kesari": "punjabkesari.in",
  "Times of India": "timesofindia.indiatimes.com",
  "Hindustan Times": "hindustantimes.com",
  "Indian Express": "indianexpress.com",
  "The Hindu": "thehindu.com",
  "Economic Times": "economictimes.indiatimes.com",
  "Kashish News": "kashishnews.com",
};
const newsChannelLogo = (channel: string) =>
  `https://www.google.com/s2/favicons?domain=${encodeURIComponent(newsChannelDomains[channel] || channel)}&sz=64`;

function NewsChannelTick({ x = 0, y = 0, payload }: {
  x?: number;
  y?: number;
  payload?: { value?: string };
}) {
  const channel = String(payload?.value || "");
  return (
    <g transform={`translate(${x},${y})`}>
      <image href={newsChannelLogo(channel)} x={-11} y={8} width={22} height={22}
        preserveAspectRatio="xMidYMid meet" />
      <text x={0} y={43} dy={0} textAnchor="end" transform="rotate(-38 0 43)"
        fill="#526273" fontSize={10} fontWeight={700}>
        {channel}
      </text>
    </g>
  );
}
const names: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X / Twitter",
  youtube: "YouTube",
  news: "News",
  reddit: "Reddit",
};

function sourceStatus(source: Source) {
  if (source.status === "disconnected") {
    return { label: "Not connected", detail: "Stored posts remain in totals" };
  }

  if (source.status === "unavailable") {
    const error = source.error || "";
    const exhausted = /exhaust|quota|credit|limit|usage|fund|payment/i.test(error);
    return {
      label: exhausted ? "Exhausted" : "Data unavailable",
      detail: error || "The source is temporarily unavailable",
    };
  }

  return { label: "Connected", detail: "Includes classified mentions" };
}
const colors = {
  positive: "#2f9278",
  negative: "#ce514e",
  neutral: "#a0adbb",
  mixed: "#c68732",
};
const num = (n: number) => n.toLocaleString("en-IN");
const dateLabel = (d: string) =>
  new Date(d + "T12:00:00").toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
let bearer = "";
async function api(path: string, options: RequestInit = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      ...(options.body instanceof URLSearchParams
        ? {}
        : { "Content-Type": "application/json" }),
      Authorization: "Bearer " + bearer,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const e = await response
      .json()
      .catch(() => ({ detail: "Service unavailable" }));
    const validationMessage = Array.isArray(e.detail)
      ? e.detail
          .map((item: any) => {
            const field = Array.isArray(item?.loc)
              ? item.loc.filter((part: unknown) => part !== "body").join(" → ")
              : "";
            return `${field ? `${field}: ` : ""}${item?.msg || "Invalid value"}`;
          })
          .join(" · ")
      : "";
    throw new Error(
      typeof e.detail === "string"
        ? e.detail
        : validationMessage || "Please check the form values",
    );
  }
  return response;
}
async function json(path: string, options: RequestInit = {}) {
  return (await api(path, options)).json();
}

async function overviewJson(path: string) {
  let lastError: unknown;
  for (const delay of [0, 800, 1800]) {
    if (delay) await new Promise((resolve) => window.setTimeout(resolve, delay));
    try {
      return await json(path);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

const GlobalLoadingContext = React.createContext<
  (message?: string) => () => void
>(() => () => undefined);

function GlobalLoader({ message }: { message: string }) {
  return (
    <div className="global-loader" role="status" aria-live="polite" aria-label={message}>
      <div className="global-loader-card">
        <span className="global-loader-spinner" aria-hidden="true" />
        <strong>{message}</strong>
        <span className="global-loader-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </div>
    </div>
  );
}

function SyncScheduleProgress({ schedule }: { schedule: NonNullable<Overview["schedule"]> }) {
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const items = [schedule.frequent, schedule.social].filter(Boolean) as SyncScheduleItem[];
  function timing(item: SyncScheduleItem) {
    if (!item.next_run_at) return { progress: 0, copy: "Schedule unavailable", seconds: 0 };
    const remaining = Math.max(0, Math.ceil((new Date(item.next_run_at).getTime() - clock) / 1000));
    const progress = Math.max(0, Math.min(100, (1 - remaining / item.interval_seconds) * 100));
    if (remaining <= 0) return { progress: 100, copy: "Starting now", seconds: 0 };
    const hours = Math.floor(remaining / 3600);
    const minutes = Math.floor((remaining % 3600) / 60);
    const seconds = remaining % 60;
    const copy = hours
      ? `Next in ${hours}h ${minutes}m`
      : `Next in ${minutes}m ${String(seconds).padStart(2, "0")}s`;
    return { progress, copy, seconds: remaining };
  }

  return (
    <section className="sync-schedule" aria-label="Automatic data collection schedule">
      {items.map((item) => {
        const state = timing(item);
        return (
          <div className="sync-schedule-item" key={item.label}>
            <div className="sync-schedule-track" role="progressbar" aria-label={`${item.label} next automatic fetch`}
              aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(state.progress)}>
              <i style={{ width: `${state.progress}%` }} />
            </div>
          </div>
        );
      })}
    </section>
  );
}

function App() {
  const [session, setSession] = useState<Session | null>(null),
    [error, setError] = useState(""),
    [showPassword, setShowPassword] = useState(false),
    [loginBusy, setLoginBusy] = useState(false);
  async function login(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoginBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const result = await json("/auth/token", {
        method: "POST",
        body: new URLSearchParams({
          username: String(data.get("email")),
          password: String(data.get("password")),
        }),
      });
      bearer = result.access_token;
      setSession(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoginBusy(false);
    }
  }
  if (!session)
    return (
      <div className="login">
        <form className="login-form" onSubmit={login}>
          <div className="login-intro">
            <div className="login-logo">
              <Eye />
              <span>GarudaDrishti</span>
            </div>
            <p>Political conversations, clearly understood.</p>
          </div>
          <h1>Log in to GarudaDrishti</h1>
          <input className="form-control"
            aria-label="Email address"
            placeholder="Email address"
            name="email"
            type="email"
            required
            autoComplete="username"
          />
          <div className="password-field">
            <input className="form-control"
              aria-label="Password"
              placeholder="Password"
              name="password"
              type={showPassword ? "text" : "password"}
              required
              autoComplete="current-password"
            />
            <button
              type="button"
              className="password-toggle"
              aria-label={showPassword ? "Hide password" : "Show password"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((visible) => !visible)}
            >
              {showPassword ? <EyeSlash size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="btn btn-primary primary" disabled={loginBusy}>
            {loginBusy ? "Signing in..." : "Log in"}
          </button>
        </form>
      </div>
    );
  return (
    <Workspace
      session={session}
      onSessionChange={setSession}
      logout={() => {
        bearer = "";
        setSession(null);
      }}
    />
  );
}

function Workspace({
  session,
  onSessionChange,
  logout,
}: {
  session: Session;
  onSessionChange: (session: Session) => void;
  logout: () => void;
}) {
  const [view, setView] = useState("overview"),
    [platform, setPlatform] = useState(""),
    [data, setData] = useState<Overview | null>(null),
    [error, setError] = useState(""),
    [revision, setRevision] = useState(0),
    [report, setReport] = useState(false),
    [detail, setDetail] = useState<Alert | null>(null),
    [mobile, setMobile] = useState(false),
    [collapsed, setCollapsed] = useState(false),
    [selectedDay, setSelectedDay] = useState(""),
    [loadingTasks, setLoadingTasks] = useState(0),
    [loadingMessage, setLoadingMessage] = useState("Loading…");
  const beginLoading = React.useCallback((message = "Loading…") => {
    let finished = false;
    setLoadingMessage(message);
    setLoadingTasks((count) => count + 1);
    return () => {
      if (finished) return;
      finished = true;
      setLoadingTasks((count) => Math.max(0, count - 1));
    };
  }, []);
  useEffect(() => {
    let active = true;
    // Initial load uses the global overlay. Refresh/status polling stays in-place
    // so a background sync never blocks the dashboard every five seconds.
    const finishLoading = data ? () => undefined : beginLoading("Loading dashboard data…");
    setError("");
    const params = new URLSearchParams();
    if (platform) params.set("platform", platform);
    if (selectedDay) params.set("day", selectedDay);
    overviewJson("/overview" + (params.size ? "?" + params : ""))
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => active && setError(e.message))
      .finally(finishLoading);
    return () => {
      active = false;
      finishLoading();
    };
  }, [platform, selectedDay, revision, beginLoading]);
  useEffect(() => {
    const refreshDashboard = () => setRevision((x) => x + 1);
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") refreshDashboard();
    };
    const timer = window.setInterval(refreshDashboard, 30000);
    window.addEventListener("focus", refreshDashboard);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refreshDashboard);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);
  useEffect(() => {
    if (!data?.sync_running) return;
    const t = window.setInterval(() => setRevision((x) => x + 1), 5000);
    return () => window.clearInterval(t);
  }, [data?.sync_running]);
  const displayedDay = selectedDay || data?.date || "",
    isHistoricalDay = Boolean(data && displayedDay !== data.date),
    summary = isHistoricalDay ? data?.selected ?? null : data?.today ?? null,
    active = data?.alerts.find((a) => a.date === displayedDay),
    selectedSource = data?.sources.find((s) => s.platform === platform),
    disconnected = selectedSource?.status === "disconnected";
  const navigate = (v: string) => {
    if (v === "alerts") {
      setSelectedDay("");
      setPlatform("");
    }
    setView(v);
    setMobile(false);
  };
  const changeProject = async (projectId: string) => {
    if (session.role !== "admin" || projectId === data?.active_project) return;
    const finishLoading = beginLoading("Switching monitoring projectâ€¦");
    setError("");
    try {
      await json("/project", {
        method: "PUT",
        body: JSON.stringify({ active_project: projectId }),
      });
      setData((current) => current ? { ...current, active_project: projectId } : current);
      setPlatform("");
      setSelectedDay("");
      setRevision((value) => value + 1);
      setMobile(false);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      finishLoading();
    }
  };
  const navigation = [
    ["overview", "Overview", LayoutDashboard],
    ["analytics", "Analytics", Activity],
    ["feed", "Conversation", Radio],
    ["voices", "Voices", Star],
    ["alerts", "Alerts", Bell],
    ["settings", "Settings", Settings],
  ] as const;
  return (
    <GlobalLoadingContext.Provider value={beginLoading}>
    <div className="shell">
      {loadingTasks > 0 && <GlobalLoader message={loadingMessage} />}
      <aside className={`workspace-sidebar${mobile ? " open" : ""}${collapsed ? " collapsed" : ""}`}>
        <div className="sidebar-brand-row">
          <button
            type="button"
            className="sidebar-brand"
            aria-label="Go to Overview"
            onClick={() => navigate("overview")}
          >
            <span className="sidebar-logo"><Eye size={22} /></span>
            <span><strong>GarudaDrishti</strong><small>SOCIAL INTELLIGENCE</small></span>
          </button>
          <button
            className="sidebar-collapse"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setCollapsed((value) => !value)}
          >
            <ChevronRight size={17} />
          </button>
          <button
            className="sidebar-close"
            aria-label="Close navigation"
            onClick={() => setMobile(false)}
          >
            <Close size={19} />
          </button>
        </div>
        <div className="sidebar-project">
          <span>PROJECT</span>
          <select value={data?.active_project || ""}
            disabled={session.role !== "admin" || !data}
            onChange={(event) => changeProject(event.target.value)}
            aria-label="Select monitoring project">
            {(data?.monitoring_projects || []).map((project) => (
              <option key={project.id} value={project.id}>{project.label}</option>
            ))}
          </select>
        </div>
        <span className="sidebar-section-label">WORKSPACE</span>
        <nav aria-label="Workspace navigation">
          {navigation.map(([key, label, Icon]) => (
            <button
              key={key}
              className={view === key ? "active" : ""}
              onClick={() => navigate(key)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {key === "alerts" && !!data?.alerts.length && (
                <b>{data.alerts.length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-account">
            <button
              className="sidebar-profile-button"
              title="Open profile"
              aria-label="Open profile"
              onClick={() => navigate("profile")}
            >
              <span className="avatar">{(session.name || session.email)[0].toUpperCase()}</span>
              <span className="sidebar-account-copy">
                <strong>{session.name || (session.role === "admin" ? "Administrator" : "Viewer")}</strong>
                <small>{session.email}</small>
              </span>
            </button>
            <button className="sidebar-logout" title="Sign out" aria-label="Sign out" onClick={logout}>
              <LogOut size={18} />
            </button>
        </div>
      </aside>
      {mobile && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobile(false)} />}
      <main className="workspace-main">
        <button className="sidebar-mobile-toggle" aria-label="Open navigation" onClick={() => setMobile(true)}>
          <Menu size={21} />
        </button>
        <div className="content">
          <div className="page-heading">
            <div>
              <p className="eyebrow">CM SOCIAL INTELLIGENCE</p>
              <h1>
                {view === "overview"
                  ? "Live overview"
                  : view === "analytics"
                    ? "Analytics"
                  : view === "voices"
                    ? "Voices"
                  : view === "feed"
                    ? "Conversation feed"
                    : view === "alerts"
                      ? "Alert centre"
                      : view === "profile"
                        ? session.role === "admin" ? "Administrator profile" : "User profile"
                        : "Workspace settings"}
              </h1>
              <p>
                {view === "overview"
                  ? "The conversation at a glance. Every signal in context."
                  : view === "analytics"
                    ? "Sentiment trends, distribution and source intelligence."
                  : view === "voices"
                    ? "Performance and sentiment of monitored X accounts."
                  : view === "feed"
                    ? "Explore the posts behind the numbers."
                    : view === "alerts"
                      ? "Daily negative posts and the rolling seven-day trend."
                      : view === "profile"
                        ? "Update your account details and password."
                        : "Manage the terms and sources you monitor."}
              </p>
            </div>
            {(view === "overview" || view === "analytics" || view === "feed") && <div className="heading-actions">
              {!isHistoricalDay && (
                <div
                  className={`classification-progress ${!data || data.pending ? "active" : "complete"}`}
                  aria-label={!data ? "Classification status is loading" : data.pending ? `${num(data.pending)} posts remaining for classification` : "Classification is up to date"}
                >
                  <div className="classification-progress-copy">
                    <span>Classification</span>
                    <strong>{!data ? "Loading" : data.pending ? `${num(data.pending)} remaining` : "Up to date"}</strong>
                  </div>
                  <div className="classification-progress-track" aria-hidden="true">
                    <i />
                  </div>
                </div>
              )}
              <button className="btn btn-primary primary" onClick={() => setReport(true)}>
                <Download size={16} />
                Export report
              </button>
            </div>}
          </div>
          {(view === "overview" || view === "feed") && !isHistoricalDay && data?.schedule?.enabled && (
            <SyncScheduleProgress schedule={data.schedule} />
          )}
          {error && (
            <div className="error" role="alert">
              {error}{" "}
              <button onClick={() => setRevision((x) => x + 1)}>Retry</button>
            </div>
          )}
          {!data && !error ? (
            <div className="empty">Loading the watchtower…</div>
          ) : (
            data && (
              <>
                {view === "profile" ? (
                  <ProfilePanel session={session} onSaved={onSessionChange} />
                ) : view === "settings" ? (
                  <SettingsPanel
                    admin={session.role === "admin"}
                    onSaved={() => setRevision((x) => x + 1)}
                  />
                ) : view === "alerts" ? (
                  <AlertCentre
                    day={displayedDay}
                    today={data.date}
                    trend={data.trend}
                    onDayChange={(day) => setSelectedDay(day === data.date ? "" : day)}
                  />
                ) : view === "voices" ? (
                  <VoicesPage revision={revision} />
                ) : (
                  <>
                    {active && (
                      <div className="alert-banner">
                        <div className="alert-symbol">
                          <TriangleAlert size={22} />
                        </div>
                        <div>
                          <strong>
                            Negative conversation crossed your daily threshold
                          </strong>
                          <p>
                            <b>{num(active.negative_count)} negative posts</b>{" "}
                            on {dateLabel(displayedDay)} ·{" "}
                            {num(active.negative_count - active.threshold)}{" "}
                            above the {num(active.threshold)}-post threshold
                          </p>
                        </div>
                        <button onClick={() => setDetail(active)}>
                          Review alert
                          <ArrowUpRight size={16} />
                        </button>
                      </div>
                    )}
                    <div className="platform-tabs">
                      <div>
                        {[["", "All platforms"], ...Object.entries(names)].map(
                          ([key, name]) => (
                            <button
                              key={key}
                              className={platform === key ? "selected" : ""}
                              onClick={() => setPlatform(key)}
                            >
                              {name}
                              {key && (
                                <span
                                  className={
                                    "tiny-dot " +
                                    (data.sources.find(
                                      (s) => s.platform === key,
                                    )?.status === "disconnected"
                                      ? "off"
                                      : "")
                                  }
                                />
                              )}
                            </button>
                          ),
                        )}
                      </div>
                      <span>
                        <CalendarDays size={15} />
                        {dateLabel(displayedDay)}, {displayedDay.slice(0, 4)}
                      </span>
                    </div>
                    {disconnected && !summary && !isHistoricalDay ? (
                      <div className="panel empty">
                        <Radio size={32} />
                        <h2>{names[platform]} is not connected</h2>
                        <p>
                          Connect an owned/managed account or a compliant
                          social-listening provider in Settings.
                        </p>
                        <p>Stored posts remain available; new posts will not be fetched.</p>
                        <button onClick={() => setView("settings")}>
                          Manage connection
                          <ChevronRight size={16} />
                        </button>
                      </div>
                    ) : (
                      <>
                        {view === "analytics" && (
                          <>
                            <div className="stats">
                              <Stat
                                label="TOTAL CLASSIFIED"
                                value={
                                  summary ? num(summary.total_count) : "—"
                                }
                                note={
                                  summary
                                    ? `Across enabled sources · ${dateLabel(displayedDay)}`
                                    : "No classified data available"
                                }
                                tone="total"
                                icon={<Activity size={18} />}
                              />
                              <Stat
                                label="POSITIVE"
                                value={
                                  summary
                                    ? num(summary.positive_count)
                                    : "—"
                                }
                                note={
                                  summary
                                    ? `${((summary.positive_count / summary.total_count) * 100).toFixed(1)}% of classified conversation`
                                    : "Awaiting data"
                                }
                                tone="positive"
                              />
                              <Stat
                                label="NEGATIVE"
                                value={
                                  summary
                                    ? num(summary.negative_count)
                                    : "—"
                                }
                                note={
                                  summary
                                    ? `${((summary.negative_count / summary.total_count) * 100).toFixed(1)}% of classified conversation`
                                    : "Awaiting data"
                                }
                                tone="negative"
                              />
                              <Stat
                                label="MIXED"
                                value={
                                  summary
                                    ? num(summary.mixed_count || 0)
                                    : "â€”"
                                }
                                note={
                                  summary
                                    ? `${(((summary.mixed_count || 0) / summary.total_count) * 100).toFixed(1)}% with both positive and negative stance`
                                    : "Awaiting data"
                                }
                                tone="mixed"
                              />
                              <Stat
                                label="NEGATIVITY INDEX"
                                value={
                                  summary
                                    ? summary.negativity_index.toFixed(1) +
                                      "%"
                                    : "—"
                                }
                                note="Negative ÷ classified posts"
                                tone="index"
                                icon={<Eye size={18} />}
                              />
                            </div>
                            <div className="chart-grid">
                              <section className="panel trend-panel">
                                <div className="panel-title">
                                  <div>
                                    <h2>Conversation pulse</h2>
                                    <p>Daily sentiment · last 30 days</p>
                                  </div>
                                  <div className="legend">
                                    {Object.entries(colors).map(([l, c]) => (
                                      <span key={l}>
                                        <i style={{ background: c }} />
                                        {l}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                                <div className="trend-chart">
                                  <ResponsiveContainer
                                    width="100%"
                                    height="100%"
                                  >
                                    <AreaChart
                                      data={data.trend}
                                      margin={{
                                        left: -23,
                                        right: 12,
                                        top: 12,
                                        bottom: 0,
                                      }}
                                    >
                                      <defs>
                                        {Object.entries(colors).map(
                                          ([l, c]) => (
                                            <linearGradient
                                              key={l}
                                              id={l}
                                              x1="0"
                                              y1="0"
                                              x2="0"
                                              y2="1"
                                            >
                                              <stop
                                                offset="0%"
                                                stopColor={c}
                                                stopOpacity={0.19}
                                              />
                                              <stop
                                                offset="100%"
                                                stopColor={c}
                                                stopOpacity={0.01}
                                              />
                                            </linearGradient>
                                          ),
                                        )}
                                      </defs>
                                      <CartesianGrid
                                        vertical={false}
                                        stroke="#e9edf1"
                                        strokeDasharray="3 3"
                                      />
                                      <XAxis
                                        dataKey="date"
                                        tickFormatter={dateLabel}
                                        minTickGap={32}
                                        tickLine={false}
                                        axisLine={false}
                                        tick={{ fontSize: 12, fill: "#718096" }}
                                      />
                                      <YAxis
                                        tickLine={false}
                                        axisLine={false}
                                        tick={{ fontSize: 12, fill: "#718096" }}
                                      />
                                      <Tooltip
                                        labelFormatter={(d) =>
                                          dateLabel(String(d))
                                        }
                                        contentStyle={{
                                          borderRadius: 6,
                                          borderColor: "#dfe5eb",
                                        }}
                                      />
                                      {Object.entries(colors).map(([l, c]) => (
                                        <Area
                                          key={l}
                                          type="monotone"
                                          dataKey={l + "_count"}
                                          name={l}
                                          stroke={c}
                                          strokeWidth={2.3}
                                          fill={`url(#${l})`}
                                          isAnimationActive={false}
                                        />
                                      ))}
                                    </AreaChart>
                                  </ResponsiveContainer>
                                </div>
                              </section>
                              <section className="panel mix-panel">
                                <div className="panel-title">
                                  <h2>{isHistoricalDay ? `${dateLabel(displayedDay)} sentiment` : "Today’s sentiment"}</h2>
                                  <span>Share of voice</span>
                                </div>
                                {summary ? (
                                  <>
                                    <div className="donut">
                                      <ResponsiveContainer
                                        width="100%"
                                        height={190}
                                      >
                                        <PieChart>
                                          <Pie
                                            data={Object.keys(colors).map(
                                              (l) => ({
                                                name: l,
                                                value:
                                                  summary![
                                                    (l +
                                                      "_count") as keyof Rollup
                                                  ],
                                              }),
                                            )}
                                            dataKey="value"
                                            innerRadius={64}
                                            outerRadius={82}
                                            paddingAngle={3}
                                            stroke="none"
                                            isAnimationActive={false}
                                          >
                                            {Object.values(colors).map((c) => (
                                              <Cell key={c} fill={c} />
                                            ))}
                                          </Pie>
                                          <Tooltip />
                                        </PieChart>
                                      </ResponsiveContainer>
                                      <div className="donut-label">
                                        <strong>
                                          {num(summary.total_count)}
                                        </strong>
                                        <span>classified posts</span>
                                      </div>
                                    </div>
                                    <div className="mix-legend">
                                      {Object.entries(colors).map(([l, c]) => (
                                        <div key={l}>
                                          <span>
                                            <i style={{ background: c }} />
                                            {l}
                                          </span>
                                          <b>
                                            {num(
                                              Number(
                                                summary![
                                                  (l + "_count") as keyof Rollup
                                                ],
                                              ),
                                            )}
                                          </b>
                                        </div>
                                      ))}
                                    </div>
                                  </>
                                ) : (
                                  <div className="empty">
                                    No classified data available
                                  </div>
                                )}
                              </section>
                            </div>
                            <NewsChannelChart
                              rows={data.news_channel_totals || []}
                              day={displayedDay}
                            />
                            <div className="secondary-grid">
                              <section className="panel">
                                <div className="panel-title">
                                  <h2>Source coverage</h2>
                                  <span>
                                    {
                                      data.sources.filter(
                                        (s) => s.status !== "disconnected",
                                      ).length
                                    }{" "}
                                    of {data.sources.length} connected
                                  </span>
                                </div>
                                <div className="source-grid">
                                  {data.sources.map((s) => {
                                    const state = sourceStatus(s);
                                    return (
                                      <button
                                        key={s.platform}
                                        className="source-item"
                                        onClick={() => setPlatform(s.platform)}
                                      >
                                        <span
                                          className={
                                            "platform-mark " + s.platform
                                          }
                                        >
                                          <PlatformIcon platform={s.platform} />
                                        </span>
                                        <strong>{names[s.platform]}</strong>
                                        <span
                                          className={
                                            s.status === "disconnected"
                                              ? "muted"
                                              : s.status === "unavailable"
                                                ? "source-error"
                                                : "source-state"
                                          }
                                        >
                                          {state.label}
                                        </span>
                                        <small>{state.detail}</small>
                                      </button>
                                    );
                                  })}
                                </div>
                              </section>
                              <section className="panel heat-panel">
                                <div className="panel-title">
                                  <h2>Negativity calendar</h2>
                                  <span>30 days</span>
                                </div>
                                <div className="heatmap">
                                  {Array.from({ length: 30 }, (_, i) => {
                                    const dt = new Date(
                                      data.date + "T12:00:00",
                                    );
                                    dt.setDate(dt.getDate() - 29 + i);
                                    const day = dt.toISOString().slice(0, 10);
                                    const row = data.trend.find(
                                      (r) => r.date === day,
                                    );
                                    return (
                                      <button
                                        key={day}
                                        title={`${dateLabel(day)}: ${row ? row.negativity_index + "% negative" : "No data"}`}
                                        style={{
                                          background: row
                                            ? `rgba(192,63,62,${0.1 + row.negativity_index / 100})`
                                            : "#eef1f4",
                                        }}
                                        onClick={() => {
                                          setSelectedDay(day === data.date ? "" : day);
                                        }}
                                      >
                                        {dt.getDate()}
                                      </button>
                                    );
                                  })}
                                </div>
                                <div className="heat-key">
                                  <span>Less negative</span>
                                  <i />
                                  <i />
                                  <i />
                                  <i />
                                  <span>More negative</span>
                                </div>
                              </section>
                            </div>
                          </>
                        )}
                        {view === "overview" && (
                          <SummaryStats
                            summary={summary}
                            displayedDay={displayedDay}
                            compact
                          />
                        )}
                        {(view === "overview" || view === "feed") && <div className={view === "overview" ? "conversation-monitor-grid" : undefined}>
                          <Feed
                            platform={platform}
                            revision={revision}
                            defaultDay={data.date}
                            day={displayedDay}
                            onDayChange={(day) => setSelectedDay(day === data.date ? "" : day)}
                            compact={view === "overview"}
                            onExpand={() => setView("feed")}
                          />
                          {view === "overview" && (
                            <ConversationInsights
                              topics={data.top_topics || []}
                              voices={data.top_x_voices || []}
                            />
                          )}
                        </div>}
                      </>
                    )}
                  </>
                )}
              </>
            )
          )}
          <footer>
            <span>
              <Eye size={14} /> GarudaDrishti ·{" "}
              Public conversation monitoring
            </span>
            <span>
              Sentiment is a model estimate, not a measure of voting intent.
            </span>
          </footer>
        </div>
      </main>
      {report && <ReportModal close={() => setReport(false)} />}{" "}
      {detail && (
        <Modal
          title={"Threshold alert · " + dateLabel(detail.date)}
          close={() => setDetail(null)}
        >
          <div className="alert-summary">
            <TriangleAlert />
            <strong>{num(detail.negative_count)} negative posts</strong>
            <span>Threshold: {num(detail.threshold)}</span>
          </div>
          <p>
            {Object.entries(detail.platform_breakdown)
              .map(([p, n]) => names[p] + ": " + num(n))
              .join(" · ")}
          </p>
          <AlertNegativePosts day={detail.date} />
          <p className="muted">
            {`Delivered: ${detail.notified_channels.join(", ") || "None"}`}
          </p>
          {detail.notification_errors && (
            <p className="error">
              Some notifications failed and are scheduled for retry.
            </p>
          )}
          {session.role === "admin" && (
            <button
              className="btn btn-primary primary"
              onClick={async () => {
                try {
                  await json("/alerts/" + detail.date + "/resolve", {
                    method: "POST",
                  });
                  setDetail(null);
                  setRevision((x) => x + 1);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <Check size={16} />
              Resolve alert
            </button>
          )}
        </Modal>
      )}
    </div>
    </GlobalLoadingContext.Provider>
  );
}

function Stat({
  label,
  value,
  note,
  tone = "",
  icon,
}: {
  label: string;
  value: string;
  note: string;
  tone?: string;
  icon?: React.ReactNode;
}) {
  return (
    <section className={"stat " + tone}>
      <div>
        <span>{label}</span>
        {icon || <i />}
      </div>
      <strong>{value}</strong>
      <p>{note}</p>
    </section>
  );
}

function SummaryStats({
  summary,
  displayedDay,
  compact = false,
}: {
  summary: Rollup | null | undefined;
  displayedDay: string;
  compact?: boolean;
}) {
  const total = summary?.total_count || 0;
  const percentage = (value: number) =>
    total ? `${((value / total) * 100).toFixed(1)}%` : "0.0%";

  return (
    <div className={`stats${compact ? " compact-stats" : ""}`}>
      <Stat
        label="TOTAL CLASSIFIED"
        value={summary ? num(summary.total_count) : "—"}
        note={
          summary
            ? `Across enabled sources · ${dateLabel(displayedDay)}`
            : "No classified data available"
        }
        tone="total"
        icon={<Activity size={18} />}
      />
      <Stat
        label="POSITIVE"
        value={summary ? num(summary.positive_count) : "—"}
        note={summary ? `${percentage(summary.positive_count)} of classified conversation` : "Awaiting data"}
        tone="positive"
      />
      <Stat
        label="NEGATIVE"
        value={summary ? num(summary.negative_count) : "—"}
        note={summary ? `${percentage(summary.negative_count)} of classified conversation` : "Awaiting data"}
        tone="negative"
      />
      <Stat
        label="MIXED"
        value={summary ? num(summary.mixed_count || 0) : "—"}
        note={summary ? `${percentage(summary.mixed_count || 0)} with both positive and negative stance` : "Awaiting data"}
        tone="mixed"
      />
      <Stat
        label="NEGATIVITY INDEX"
        value={summary ? `${summary.negativity_index.toFixed(1)}%` : "—"}
        note="Negative ÷ classified posts"
        tone="index"
        icon={<Eye size={18} />}
      />
    </div>
  );
}

function ConversationInsights({
  topics,
  voices,
}: {
  topics: NonNullable<Overview["top_topics"]>;
  voices: NonNullable<Overview["top_x_voices"]>;
}) {
  return (
    <aside className="conversation-insights" aria-label="Conversation insights">
      <section className="panel insight-card topics-card">
        <div className="panel-title">
          <h2>Top Topics</h2>
          <span>{topics.reduce((sum, topic) => sum + topic.count, 0)} mentions</span>
        </div>
        <div className="topic-list">
          {topics.length ? topics.map((topic) => {
            const classified = topic.positive_count + topic.negative_count + topic.neutral_count + topic.mixed_count;
            const segments = [
              { label: "positive", value: topic.positive_count },
              { label: "neutral", value: topic.neutral_count },
              { label: "mixed", value: topic.mixed_count },
              { label: "negative", value: topic.negative_count },
            ];
            return (
              <div className="topic-item" key={topic.topic}>
                <div><strong>{topic.topic}</strong><b>{num(topic.count)}</b></div>
                <div className="topic-sentiment-bar" aria-label={`${topic.topic}: ${topic.count} mentions`}>
                  {segments.map(({ label, value }) => {
                    return value > 0 ? <i key={label} className={label}
                      style={{ width: `${classified ? value / classified * 100 : 0}%` }} /> : null;
                  })}
                </div>
              </div>
            );
          }) : <div className="insight-empty">No topic signals for this date.</div>}
        </div>
      </section>

      <section className="panel insight-card voices-card">
        <div className="panel-title">
          <h2>Top X Voices</h2>
          <span>By posts & engagement</span>
        </div>
        <div className="voice-list">
          {voices.length ? voices.map((voice) => {
            const sentimentCounts = {
              positive: voice.positive_count,
              negative: voice.negative_count,
              neutral: voice.neutral_count,
              mixed: voice.mixed_count,
            };
            const dominant = Object.entries(sentimentCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "neutral";
            return (
              <div className="voice-item" key={voice.username || voice.author}>
                <span className="voice-avatar">
                  {voice.avatar_url ? (
                    <img src={voice.avatar_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
                  ) : (voice.author.trim().charAt(0).toUpperCase() || "X")}
                </span>
                <div>
                  <strong>{voice.author}</strong>
                  <small>{voice.username ? `@${voice.username}` : "X / Twitter"}</small>
                </div>
                <div className="voice-score">
                  <span className={`voice-dot ${dominant}`} />
                  <b>{num(voice.post_count)}</b>
                  <small>{num(voice.engagement)} interactions</small>
                </div>
              </div>
            );
          }) : <div className="insight-empty">No X voices for this date.</div>}
        </div>
      </section>
    </aside>
  );
}

type VoiceRow = {
  username: string;
  author: string;
  avatar_url: string;
  post_count: number;
  reach: number;
  engagement: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  mixed_count: number;
};

function VoicesPage({ revision }: { revision: number }) {
  const beginLoading = React.useContext(GlobalLoadingContext);
  const [rows, setRows] = useState<VoiceRow[]>([]);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("reach");
  const [days, setDays] = useState(7);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [activityFilter, setActivityFilter] = useState("all");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const finishLoading = beginLoading("Loading monitored voicesâ€¦");
    setError("");
    json(`/voices?days=${days}`)
      .then((result) => active && setRows(result.items || []))
      .catch((reason) => active && setError(reason.message))
      .finally(finishLoading);
    return () => { active = false; finishLoading(); };
  }, [days, revision, beginLoading]);
  const newsHandles = new Set([
    "ani", "live_cities", "aajtak", "news18bihar", "ani_hindinews", "ians_india",
    "indianexpress", "zeebiharnews", "tv9bharatvarsh", "ianskhabar", "purneatimes",
    "bharat24liv",
  ]);
  const governmentHandles = new Set([
    "policebhagalpur", "dmabhagalpur", "dmbhagalpur", "naugachiapolice", "biharss1",
  ]);
  const categoryFor = (username: string) => {
    const key = username.toLowerCase();
    if (newsHandles.has(key)) return "news";
    if (governmentHandles.has(key)) return "government";
    return "politics";
  };
  const normalizedQuery = query.trim().replace(/^@/, "").toLowerCase();
  const visible = rows
    .filter((voice) => {
      const matchesSearch = !normalizedQuery ||
        `${voice.author} ${voice.username}`.toLowerCase().includes(normalizedQuery);
      const category = categoryFor(voice.username);
      const matchesCategory = categoryFilter === "all" || category === categoryFilter;
      const matchesActivity = activityFilter === "all" ||
        (activityFilter === "active" ? voice.post_count > 0 : voice.post_count === 0);
      return matchesSearch && matchesCategory && matchesActivity;
    })
    .sort((a, b) => {
      if (mode === "negative") return b.negative_count - a.negative_count || b.post_count - a.post_count;
      if (mode === "support") return b.positive_count - a.positive_count || b.post_count - a.post_count;
      if (mode === "engagement") return b.engagement - a.engagement || b.reach - a.reach;
      return b.reach - a.reach || b.post_count - a.post_count;
    });
  return (
    <section className="panel voices-page">
      <div className="voices-toolbar">
        <div className="voices-tabs">
          {[["reach", "Top by Reach"], ["negative", "Negative Voices"],
            ["support", "Support Voices"], ["engagement", "Engagement Score"]].map(([key, label]) => (
            <button key={key} className={mode === key ? "active" : ""} onClick={() => setMode(key)}>{label}</button>
          ))}
        </div>
        <span>{rows.length} monitored accounts</span>
      </div>
      <div className="voices-filters">
        <label className="search"><Search size={17} /><input className="form-control" value={query}
          onChange={(event) => setQuery(event.target.value)} placeholder="Search by account, name or @username…"
          aria-label="Search monitored X accounts" /></label>
        <select className="form-select" value={categoryFilter}
          onChange={(event) => setCategoryFilter(event.target.value)} aria-label="Filter voice category">
          <option value="all">All categories</option>
          <option value="news">News &amp; Media</option>
          <option value="government">Government</option>
          <option value="politics">Politics &amp; Public Affairs</option>
        </select>
        <select className="form-select" value={activityFilter}
          onChange={(event) => setActivityFilter(event.target.value)} aria-label="Filter voice activity">
          <option value="all">All activity</option>
          <option value="active">Has posts</option>
          <option value="inactive">No posts</option>
        </select>
        <select className="form-select" value={days} onChange={(event) => setDays(Number(event.target.value))}>
          <option value={1}>Last 24 hours</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
        </select>
        {(query || categoryFilter !== "all" || activityFilter !== "all") && (
          <button className="voices-clear" type="button" onClick={() => {
            setQuery("");
            setCategoryFilter("all");
            setActivityFilter("all");
          }}>Clear</button>
        )}
      </div>
      {error ? <p className="error">{error}</p> : <div className="voices-table">
        <div className="voices-table-head">
          <span>#</span><span>ACCOUNT</span><span>TYPE</span><span>MENTIONS</span>
          <span>REACH</span><span>ENGAGEMENT</span><span>SENTIMENT MIX</span>
        </div>
        {visible.map((voice, index) => {
          const total = voice.positive_count + voice.negative_count + voice.neutral_count + voice.mixed_count;
          const positive = total ? voice.positive_count / total * 100 : 0;
          const negative = total ? voice.negative_count / total * 100 : 0;
          const neutral = Math.max(0, 100 - positive - negative);
          const categoryKey = categoryFor(voice.username);
          const category = categoryKey === "news" ? "News & Media" : categoryKey === "government"
            ? "Government" : "Politics & Public Affairs";
          const avatar = voice.avatar_url || `https://unavatar.io/twitter/${encodeURIComponent(voice.username)}`;
          return <div className="voices-table-row" key={voice.username}>
            <span className="voice-rank">{index + 1}</span>
            <div className="voice-account">
              <span className="voice-page-avatar">{voice.username[0]?.toUpperCase()}
                <img src={avatar} alt="" loading="lazy" referrerPolicy="no-referrer"
                  onError={(event) => { event.currentTarget.style.display = "none"; }} />
              </span>
              <div><strong>@{voice.username}</strong><small>{voice.author}</small></div>
            </div>
            <span className={`voice-category ${categoryKey}`}>{category}</span>
            <b>{num(voice.post_count)}</b><span>{num(voice.reach)}</span><span>{num(voice.engagement)}</span>
            <div className="voice-sentiment-mix">
              <small>{Math.round(positive)}% pos Â· {Math.round(negative)}% neg</small>
              <div><i style={{ width: `${positive}%` }} /><i style={{ width: `${negative}%` }} />
                <i style={{ width: `${neutral}%` }} /></div>
            </div>
          </div>;
        })}
        {!visible.length && (
          <div className="voices-empty">No monitored accounts match these filters.</div>
        )}
      </div>}
    </section>
  );
}

function NewsChannelChart({
  rows,
  day,
}: {
  rows: {
    channel: string;
    positive_count: number;
    negative_count: number;
    historical_count: number;
    historical_top_ten: boolean;
  }[];
  day: string;
}) {
  const positiveTotal = rows.reduce((sum, row) => sum + row.positive_count, 0);
  const negativeTotal = rows.reduce((sum, row) => sum + row.negative_count, 0);
  const chartWidth = Math.max(1280, rows.length * 82);

  return (
    <section className="panel news-channel-panel">
      <div className="panel-title">
        <div>
          <h2>News Channel Coverage</h2>
          <p>{dateLabel(day)}</p>
        </div>
        <div className="news-chart-metrics">
          <span className="positive"><i /><b>{num(positiveTotal)}</b> positive</span>
          <span className="negative"><i /><b>{num(negativeTotal)}</b> negative</span>
        </div>
      </div>
      <div className="news-channel-scroll">
        <div className="news-channel-chart" style={{ width: chartWidth }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ left: -22, right: 12, top: 12, bottom: 76 }}>
              <defs>
                <linearGradient id="newsBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#48a98d" />
                  <stop offset="100%" stopColor="#277b67" />
                </linearGradient>
                <linearGradient id="newsNegativeBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e2645f" />
                  <stop offset="100%" stopColor="#bd3735" />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="#eee4dc" strokeDasharray="4 5" />
              <XAxis dataKey="channel" interval={0} tickLine={false}
                axisLine={false} tick={<NewsChannelTick />} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false}
                tick={{ fontSize: 12, fill: "#718096" }} />
              <Tooltip formatter={(value, name) => [num(Number(value)), name]}
                cursor={{ fill: "rgba(255,111,15,0.06)", radius: 8 }}
                contentStyle={{ borderRadius: 8, borderColor: "#eadfd6" }} />
              <Bar dataKey="positive_count" name="Positive" stackId="sentiment"
                fill="url(#newsBarGradient)" radius={[3, 3, 3, 3]}
                maxBarSize={48} isAnimationActive={false}>
                <LabelList dataKey="positive_count" position="center" fill="#fff" fontSize={10}
                  fontWeight={700} formatter={(value: number) => value > 0 ? num(value) : ""} />
              </Bar>
              <Bar dataKey="negative_count" name="Negative" stackId="sentiment"
                fill="url(#newsNegativeBarGradient)" radius={[8, 8, 3, 3]}
                maxBarSize={48} isAnimationActive={false}>
                <LabelList dataKey="negative_count" position="center" fill="#fff" fontSize={10}
                  fontWeight={700} formatter={(value: number) => value > 0 ? num(value) : ""} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}

function AlertCentre({
  day,
  today,
  trend,
  onDayChange,
}: {
  day: string;
  today: string;
  trend: Rollup[];
  onDayChange: (day: string) => void;
}) {
  const lastSevenDays = Array.from({ length: 7 }, (_, index) => {
    const current = new Date(today + "T12:00:00");
    current.setDate(current.getDate() - 6 + index);
    const date = current.toISOString().slice(0, 10);
    const rollup = trend.find((row) => row.date === date);
    return { date, negative_count: rollup?.negative_count || 0 };
  });
  const sevenDayTotal = lastSevenDays.reduce((total, row) => total + row.negative_count, 0);
  const peakDay = lastSevenDays.reduce(
    (peak, row) => row.negative_count > peak.negative_count ? row : peak,
    lastSevenDays[0],
  );

  return (
    <div className="alert-centre-content">
      <section className="panel alert-trend-panel">
        <div className="panel-title">
          <div>
            <h2>Negative posts · last 7 days</h2>
            <p>Rolling daily volume through {dateLabel(today)}</p>
          </div>
          <div className="alert-chart-metrics">
            <span><b>{num(sevenDayTotal)}</b> total</span>
            <span><b>{num(peakDay.negative_count)}</b> peak · {dateLabel(peakDay.date)}</span>
          </div>
        </div>
        <div className="alert-bar-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={lastSevenDays} margin={{ left: -24, right: 12, top: 12, bottom: 0 }}>
              <defs>
                <linearGradient id="alertBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e35b56" />
                  <stop offset="100%" stopColor="#bd3735" />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="#eadfdd" strokeDasharray="4 5" />
              <XAxis dataKey="date" tickFormatter={dateLabel} tickLine={false} axisLine={false}
                tick={{ fontSize: 12, fill: "#718096" }} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false}
                tick={{ fontSize: 12, fill: "#718096" }} />
              <Tooltip labelFormatter={(value) => dateLabel(String(value))}
                formatter={(value) => [num(Number(value)), "Negative posts"]}
                cursor={{ fill: "rgba(206,81,78,0.06)", radius: 8 }}
                contentStyle={{ borderRadius: 6, borderColor: "#dfe5eb" }} />
              <Bar dataKey="negative_count" name="Negative posts" fill="url(#alertBarGradient)"
                radius={[9, 9, 3, 3]} maxBarSize={64} isAnimationActive={false}>
                <LabelList dataKey="negative_count" position="center" fill="#fff" fontSize={12}
                  fontWeight={700} formatter={(value: number) => value > 0 ? num(value) : ""} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel alert-negative-list">
        <div className="panel-title alert-date-filter">
          <div>
            <h2>Negative posts</h2>
          </div>
          <div className="alert-calendar-only">
            <input className="form-control" type="date" aria-label="Filter alert posts by date"
              value={day} max={today} onChange={(event) => onDayChange(event.target.value)} />
          </div>
        </div>
        <AlertNegativePosts key={day} day={day} />
      </section>
    </div>
  );
}

function PostPreview({ post }: { post: Post }) {
  const youtubeThumbnail = post.platform === "youtube" && post.external_id
    ? `https://i.ytimg.com/vi/${encodeURIComponent(post.external_id)}/hqdefault.jpg`
    : "";
  const thumbnail = post.thumbnail_url || youtubeThumbnail || (post.media_type === "image" ? post.media_url : "");
  const playableVideo = post.media_type === "video" && post.media_url && !thumbnail;
  if (!thumbnail && !playableVideo) return null;
  const media = thumbnail ? (
    <img src={thumbnail} alt="" loading="lazy" referrerPolicy="no-referrer"
      onError={(event) => { event.currentTarget.parentElement?.classList.add("media-error"); }} />
  ) : (
    <video src={post.media_url} controls preload="metadata" />
  );
  return post.url && /^https:\/\//.test(post.url) ? (
    <a className="post-media-preview" href={post.url} target="_blank" rel="noreferrer">
      {media}
      {post.media_type === "video" && <span>Video</span>}
    </a>
  ) : (
    <div className="post-media-preview">
      {media}
      {post.media_type === "video" && <span>Video</span>}
    </div>
  );
}

function PostInlineMeta({ post }: { post: Post }) {
  const label = post.sentiment?.label;
  return (
    <div className="post-inline-meta">
      {label ? (
        <span className={`sentiment ${label}`} title={post.sentiment?.reason}>
          {label}<b>{Math.round((post.sentiment?.confidence || 0) * 100)}%</b>
        </span>
      ) : (
        <span className="sentiment pending">
          {post.classification_status === "awaiting_gemini" ? "Awaiting Gemini" : "Pending"}
        </span>
      )}
      <span><Activity size={13} />{num(post.engagement_score)} interactions</span>
      <span><CalendarDays size={13} />
        {new Date(post.published_at).toLocaleString("en-IN", {
          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
          timeZone: "Asia/Kolkata",
        })}
      </span>
    </div>
  );
}

function AlertNegativePosts({ day }: { day: string }) {
  const [page, setPage] = useState(1);
  const [posts, setPosts] = useState<{ items: Post[]; total: number } | null>(null);
  const [error, setError] = useState("");
  const [expandedPosts, setExpandedPosts] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    let active = true;
    setError("");
    setPosts(null);
    json(`/posts?sentiment=negative&day=${encodeURIComponent(day)}&sort=engagement&page=${page}`)
      .then((result) => active && setPosts(result))
      .catch((reason) => active && setError(reason.message));
    return () => {
      active = false;
    };
  }, [day, page]);

  useEffect(() => setPage(1), [day]);
  useEffect(() => setExpandedPosts(new Set()), [day, page]);

  if (error) return <p className="error">{error}</p>;
  if (!posts) return <div className="empty">Loading negative posts…</div>;
  if (!posts.items.length) return <div className="empty">No negative posts found for this day.</div>;

  return (
    <>
      <div className="alert-post-count">
        <strong>{num(posts.total)}</strong> negative posts on {dateLabel(day)}
      </div>
      <div className="post-table alert-post-table">
        <div className="table-heading">
          <span>CONVERSATION</span>
          <span>SENTIMENT</span>
          <span>INTERACTIONS</span>
          <span>POSTED · IST</span>
        </div>
        {posts.items.map((post) => {
          const contentExpandable = post.content.length > 300 || post.content.split(/\r?\n/).length > 3;
          const contentExpanded = expandedPosts.has(post._id);
          return (
            <article className="post-row" key={post._id}>
              <div>
                <div className="post-author">
                  <span className={"mini-platform " + post.platform}>
                    <PlatformIcon platform={post.platform} />
                  </span>
                  <b>{post.author}</b>
                  <span>{names[post.platform]}</span>
                </div>
                <PostInlineMeta post={post} />
                <PostPreview post={post} />
                <p className={contentExpandable && !contentExpanded ? "post-content compact" : "post-content"}>
                  {post.content}
                </p>
                {(contentExpandable || (post.url && /^https:\/\//.test(post.url))) && (
                  <div className="post-actions">
                    {post.url && /^https:\/\//.test(post.url) && (
                      <a href={post.url} target="_blank" rel="noreferrer">
                        Open original <ArrowUpRight size={12} />
                      </a>
                    )}
                    {contentExpandable && (
                      <button type="button" className="post-more" aria-expanded={contentExpanded}
                        onClick={() => setExpandedPosts((current) => {
                          const next = new Set(current);
                          if (next.has(post._id)) next.delete(post._id);
                          else next.add(post._id);
                          return next;
                        })}>
                        {contentExpanded ? "Show less" : "More"}
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div>
                <span className="sentiment negative">Negative</span>
                {post.sentiment && <small>{Math.round(post.sentiment.confidence * 100)}% confidence</small>}
              </div>
              <div>
                <strong>{num(post.engagement_score)}</strong>
                <small>
                  {num(post.engagement.likes)} likes / {post.platform === "youtube"
                    ? `${num(post.engagement.views)} views`
                    : `${num(post.engagement.comments)} replies`}
                </small>
              </div>
              <div>
                {new Date(post.published_at).toLocaleDateString("en-IN", {
                  day: "numeric", month: "short", timeZone: "Asia/Kolkata",
                })}
                <small>
                  {new Date(post.published_at).toLocaleTimeString("en-IN", {
                    hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
                  })}
                </small>
              </div>
            </article>
          );
        })}
      </div>
      {posts.total > 20 && (
        <div className="pagination">
          <span>Page {page} of {Math.ceil(posts.total / 20)}</span>
          <button disabled={page === 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
          <button disabled={page * 20 >= posts.total} onClick={() => setPage((value) => value + 1)}>Next</button>
        </div>
      )}
    </>
  );
}

function Feed({
  platform,
  revision,
  defaultDay,
  day,
  onDayChange,
  compact,
  onExpand,
}: {
  platform: string;
  revision: number;
  defaultDay: string;
  day: string;
  onDayChange: (day: string) => void;
  compact: boolean;
  onExpand: () => void;
}) {
  const beginLoading = React.useContext(GlobalLoadingContext);
  const [q, setQ] = useState(""),
    [term, setTerm] = useState(""),
    [sentiment, setSentiment] = useState(""),
    [sort, setSort] = useState("recency"),
    [page, setPage] = useState(1),
    [posts, setPosts] = useState<{ items: Post[]; total: number } | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [expandedPosts, setExpandedPosts] = useState<Set<string>>(
    () => new Set(),
  );
  const pageSize = compact ? 4 : 20;
  useEffect(() => {
    const t = setTimeout(() => setTerm(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setPage(1), [platform, term, sentiment, sort, day]);
  useEffect(
    () => setExpandedPosts(new Set()),
    [platform, term, sentiment, sort, page, day],
  );
  useEffect(() => {
    let active = true;
    const finishLoading = beginLoading("Loading conversations…");
    setError("");
    setLoading(true);
    const p = new URLSearchParams({
      q: term,
      sort,
      page: String(page),
      page_size: String(pageSize),
    });
    if (platform) p.set("platform", platform);
    if (sentiment) p.set("sentiment", sentiment);
    if (day) p.set("day", day);
    json("/posts?" + p)
      .then((p) => active && setPosts(p))
      .catch((e) => active && setError(e.message))
      .finally(() => {
        if (active) setLoading(false);
        finishLoading();
      });
    return () => {
      active = false;
      finishLoading();
    };
  }, [platform, term, sentiment, sort, page, revision, day, beginLoading, pageSize]);
  return (
    <section className="panel feed">
      <div className="panel-title">
        <div>
          <h2>{compact ? "Conversation watch" : "Recent posts"}</h2>
          <p>
            {loading
              ? "Loading conversations…"
              : posts
                ? num(posts.total) + " matching posts"
                : "Posts unavailable"}
          </p>
        </div>
        {compact && (
          <button className="text-button" onClick={onExpand}>
            View all posts
            <ArrowUpRight size={15} />
          </button>
        )}
      </div>
      <div className="feed-controls">
        <label className="search">
          <Search size={17} />
          <input className="form-control"
            aria-label="Search posts"
            placeholder="Search conversations…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <select className="form-select"
          aria-label="Filter sentiment"
          value={sentiment}
          onChange={(e) => setSentiment(e.target.value)}
        >
          <option value="">All sentiments</option>
          <option value="positive">Positive</option>
          <option value="negative">Negative</option>
          <option value="neutral">Neutral</option>
          <option value="mixed">Mixed</option>
        </select>
        <select className="form-select"
          aria-label="Sort posts"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="recency">Most recent</option>
          <option value="engagement">Most engaged</option>
        </select>
        {!compact && (
          <input className="form-control"
            type="date"
            aria-label="Filter date"
            value={day}
            max={defaultDay}
            onChange={(e) => onDayChange(e.target.value)}
          />
        )}
        {day !== defaultDay && (
          <button onClick={() => onDayChange(defaultDay)}>Clear date</button>
        )}
      </div>
      {error ? (
        <p className="error">{error}</p>
      ) : posts?.items.length === 0 ? (
        <div className="empty">No conversations match these filters.</div>
      ) : (
        <div className="post-table">
          <div className="table-heading">
            <span>CONVERSATION</span>
            <span>SENTIMENT</span>
            <span>INTERACTIONS</span>
            <span>POSTED · IST</span>
          </div>
          {posts?.items.map((p) => {
            const contentExpandable =
              p.content.length > 300 || p.content.split(/\r?\n/).length > 3;
            const contentExpanded = expandedPosts.has(p._id);
            return (
            <article className="post-row" key={p._id}>
              <div>
                <div className="post-author">
                  <span className={"mini-platform " + p.platform}>
                    <PlatformIcon platform={p.platform} />
                  </span>
                  <b>{p.author}</b>
                  <span>
                    {names[p.platform]}
                  </span>
                </div>
                <PostInlineMeta post={p} />
                <PostPreview post={p} />
                <p
                  className={
                    contentExpandable && !contentExpanded
                      ? "post-content compact"
                      : contentExpandable
                        ? "post-content"
                        : undefined
                  }
                >
                  {p.content}
                </p>
                {(contentExpandable ||
                  (p.url && /^https:\/\//.test(p.url))) && (
                  <div className="post-actions">
                    {p.url && /^https:\/\//.test(p.url) && (
                      <a href={p.url} target="_blank" rel="noreferrer">
                        Open original
                        <ArrowUpRight size={12} />
                      </a>
                    )}
                    {contentExpandable && (
                      <button
                        type="button"
                        className="post-more"
                        aria-expanded={contentExpanded}
                        onClick={() =>
                          setExpandedPosts((current) => {
                            const next = new Set(current);
                            if (next.has(p._id)) next.delete(p._id);
                            else next.add(p._id);
                            return next;
                          })
                        }
                      >
                        {contentExpanded ? "Show less" : "More"}
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div>
                {p.sentiment ? (
                  <>
                    <span className={"sentiment " + p.sentiment.label}>
                      {p.sentiment.label}
                    </span>
                    <small title={p.sentiment.reason}>
                      {Math.round(p.sentiment.confidence * 100)}% confidence
                      {p.sentiment.review_required ? " · Review" : ""}
                    </small>
                  </>
                ) : (
                  <span className="muted">{p.classification_status === "awaiting_gemini" ? "Awaiting Gemini" : "Pending"}</span>
                )}
              </div>
              <div>
                <strong>{num(p.engagement_score)}</strong>
                <small>
                  {num(p.engagement.likes)} likes / {p.platform === "youtube"
                    ? `${num(p.engagement.views)} views`
                    : `${num(p.engagement.comments)} replies`}
                </small>
              </div>
              <div>
                {new Date(p.published_at).toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  timeZone: "Asia/Kolkata",
                })}
                <small>
                  {new Date(p.published_at).toLocaleTimeString("en-IN", {
                    hour: "2-digit",
                    minute: "2-digit",
                    timeZone: "Asia/Kolkata",
                  })}
                </small>
              </div>
            </article>
            );
          })}
        </div>
      )}
      {posts && posts.total > pageSize && (
        <div className="pagination">
          <span>
            Page {page} of {Math.max(1, Math.ceil(posts.total / pageSize))}
          </span>
          <button disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </button>
          <button
            disabled={page * pageSize >= posts.total}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      )}
    </section>
  );
}

function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  const ref = React.useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={close}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="jn-modal">
        <div className="modal-heading">
          <h2>{title}</h2>
          <button aria-label="Close dialog" onClick={close}>
            <Close size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
function ReportModal({ close }: { close: () => void }) {
  const beginLoading = React.useContext(GlobalLoadingContext);
  const [period, setPeriod] = useState("daily"),
    [format, setFormat] = useState("pdf"),
    [sentiment, setSentiment] = useState("all"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Modal title="Export sentiment report" close={close}>
      <p>
        Reports include classified totals, negativity index, and source
        coverage. Reporting days use Asia/Kolkata.
      </p>
      <label>
        Period
        <select className="form-select" value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="daily">Today</option>
          <option value="weekly">Last 7 days</option>
          <option value="monthly">Last 30 days</option>
        </select>
      </label>
      <label>
        Sentiment
        <select className="form-select" value={sentiment} onChange={(e) => setSentiment(e.target.value)}>
          <option value="all">All sentiments</option>
          <option value="positive">Positive</option>
          <option value="negative">Negative</option>
          <option value="mixed">Mixed</option>
          <option value="neutral">Neutral</option>
        </select>
      </label>
      <label>
        File format
        <select className="form-select" value={format} onChange={(e) => setFormat(e.target.value)}>
          <option value="pdf">PDF report</option>
          <option value="csv">CSV spreadsheet</option>
        </select>
      </label>
      {error && <p className="error">{error}</p>}
      <button
        className="btn btn-primary primary"
        disabled={busy}
        onClick={async () => {
          const finishLoading = beginLoading("Preparing your report…");
          setBusy(true);
          try {
            const response = await api(
              `/export?period=${period}&format=${format}&sentiment=${sentiment}`,
            );
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement("a");
            a.href = url;
            a.download = `garudadrishti-${period}-${sentiment}.${format}`;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            close();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
            finishLoading();
          }
        }}
      >
        <Download size={16} />
        {busy ? "Preparing…" : "Download report"}
      </button>
    </Modal>
  );
}

function ProfilePanel({
  session,
  onSaved,
}: {
  session: Session;
  onSaved: (session: Session) => void;
}) {
  const beginLoading = React.useContext(GlobalLoadingContext);
  const [profile, setProfile] = useState({ name: session.name, email: session.email });
  const [savedProfile, setSavedProfile] = useState({ name: session.name, email: session.email });
  const [editing, setEditing] = useState(false);
  const [confirmation, setConfirmation] = useState<"profile" | "password" | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [visiblePasswords, setVisiblePasswords] = useState({ current: false, next: false, confirm: false });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const finishLoading = beginLoading("Loading your profile?");
    json("/profile")
      .then((value) => {
        const loaded = { name: value.name, email: value.email };
        setProfile(loaded);
        setSavedProfile(loaded);
      })
      .catch((e) => setError(e.message))
      .finally(finishLoading);
    return finishLoading;
  }, [beginLoading]);

  function clearSecurityForm() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setVisiblePasswords({ current: false, next: false, confirm: false });
  }

  async function confirmSave(mode: "profile" | "password") {
    setError("");
    setMessage("");
    if (mode === "password") {
      if (newPassword !== confirmPassword) {
        setError("New password and confirmation do not match.");
        return;
      }
      if (newPassword.length < 8 || newPassword.length > 14) {
        setError("New password must contain 8 to 14 characters.");
        return;
      }
    }
    const finishLoading = beginLoading(mode === "profile" ? "Updating your profile?" : "Changing your password?");
    setSaving(true);
    try {
      const target = mode === "profile" ? profile : savedProfile;
      const result = await json("/profile", {
        method: "PUT",
        body: JSON.stringify({
          name: target.name,
          email: target.email,
          current_password: currentPassword,
          new_password: mode === "password" ? newPassword : "",
        }),
      });
      if (mode === "profile") {
        const saved = { name: result.name, email: result.email };
        setProfile(saved);
        setSavedProfile(saved);
        onSaved({ role: result.role, ...saved });
        setEditing(false);
        setMessage("Profile updated successfully.");
      } else {
        setMessage("Password changed successfully.");
      }
      setConfirmation(null);
      clearSecurityForm();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
      finishLoading();
    }
  }

  function PasswordInput({
    fieldKey,
    label,
    value,
    setValue,
    autoComplete,
  }: {
    fieldKey: "current" | "next" | "confirm";
    label: string;
    value: string;
    setValue: (value: string) => void;
    autoComplete: string;
  }) {
    return (
      <label>
        {label}
        <span className="profile-password-field">
          <input className="form-control" type={visiblePasswords[fieldKey] ? "text" : "password"}
            required minLength={fieldKey === "current" ? 1 : 8}
            maxLength={fieldKey === "current" ? 72 : 14}
            autoComplete={autoComplete} value={value}
            onChange={(e) => setValue(e.target.value)} />
          <button type="button" aria-label={`${visiblePasswords[fieldKey] ? "Hide" : "Show"} ${label.toLowerCase()}`}
            onClick={() => setVisiblePasswords((state) => ({ ...state, [fieldKey]: !state[fieldKey] }))}>
            {visiblePasswords[fieldKey] ? <EyeSlash size={17} /> : <Eye size={17} />}
          </button>
        </span>
      </label>
    );
  }

  return (
    <section className="panel profile-panel">
      <div className="profile-header">
        <span className="profile-avatar">{(profile.name || profile.email)[0]?.toUpperCase()}</span>
        <div>
          <h2>{savedProfile.name || "Administrator"}</h2>
          <p>{session.role === "admin" ? "Administrator account" : "Viewer account"}</p>
        </div>
        {!editing && !confirmation && (
          <div className="profile-header-actions">
            <button type="button" className="btn btn-outline-primary profile-edit-button" onClick={() => {
              setEditing(true);
              setMessage("");
              setError("");
            }}>Edit profile</button>
            <button type="button" className="btn profile-password-button" onClick={() => {
              clearSecurityForm();
              setConfirmation("password");
              setMessage("");
              setError("");
            }}>Change password</button>
          </div>
        )}
      </div>

      <div className="profile-fields">
        <label>
          Full name
          <input className="form-control" minLength={2} maxLength={80} required
            disabled={!editing || confirmation !== null} value={profile.name}
            onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
        </label>
        <label>
          Email address
          <input className="form-control" type="email" required autoComplete="email"
            disabled={!editing || confirmation !== null} value={profile.email}
            onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
        </label>
      </div>

      {editing && !confirmation && (
        <div className="profile-actions">
          <button type="button" className="btn btn-light" onClick={() => {
            setProfile(savedProfile);
            setEditing(false);
            setError("");
          }}>Cancel</button>
          <button type="button" className="btn btn-primary primary" onClick={() => {
            if (profile.name.trim().length < 2 || !profile.email.includes("@")) {
              setError("Enter a valid name and email address.");
              return;
            }
            clearSecurityForm();
            setConfirmation("profile");
            setError("");
          }}>Save profile</button>
        </div>
      )}

      {confirmation === "profile" && (
        <div className="profile-confirmation-box">
          <div><strong>Confirm profile changes</strong><p>Enter your current password before updating your name or email.</p></div>
          <PasswordInput fieldKey="current" label="Current password" value={currentPassword}
            setValue={setCurrentPassword} autoComplete="current-password" />
          <div className="profile-actions">
            <button type="button" className="btn btn-light" disabled={saving} onClick={() => {
              setConfirmation(null);
              clearSecurityForm();
              setError("");
            }}>Cancel</button>
            <button type="button" className="btn btn-primary primary" disabled={saving || !currentPassword}
              onClick={() => confirmSave("profile")}>{saving ? "Confirming?" : "Confirm"}</button>
          </div>
        </div>
      )}

      {confirmation === "password" && (
        <div className="profile-confirmation-box password-change-box">
          <div><strong>Change password</strong><p>Use 8 to 14 characters for the new password.</p></div>
          <div className="profile-fields profile-passwords">
            <PasswordInput fieldKey="current" label="Current password" value={currentPassword}
              setValue={setCurrentPassword} autoComplete="current-password" />
            <PasswordInput fieldKey="next" label="New password" value={newPassword}
              setValue={setNewPassword} autoComplete="new-password" />
            <PasswordInput fieldKey="confirm" label="Confirm new password" value={confirmPassword}
              setValue={setConfirmPassword} autoComplete="new-password" />
          </div>
          <div className="profile-actions">
            <button type="button" className="btn btn-light" disabled={saving} onClick={() => {
              setConfirmation(null);
              clearSecurityForm();
              setError("");
            }}>Cancel</button>
            <button type="button" className="btn btn-primary primary"
              disabled={saving || !currentPassword || newPassword.length < 8 || newPassword.length > 14 || newPassword !== confirmPassword}
              onClick={() => confirmSave("password")}>{saving ? "Saving?" : "Save password"}</button>
          </div>
        </div>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {message && <p className="success" role="status"><Check size={16} />{message}</p>}
    </section>
  );
}

function SettingsPanel({
  admin,
  onSaved,
}: {
  admin: boolean;
  onSaved: () => void;
}) {
  const beginLoading = React.useContext(GlobalLoadingContext);
  const [prefs, setPrefs] = useState<any>(null),
    [terms, setTerms] = useState(""),
    [xUsernames, setXUsernames] = useState(""),
    [activeProject, setActiveProject] = useState(""),
    [startHour, setStartHour] = useState(6),
    [endHour, setEndHour] = useState(22),
    [editing, setEditing] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  useEffect(() => {
    const finishLoading = beginLoading("Loading workspace settings…");
    json("/settings")
      .then((p) => {
        setPrefs(p);
        setStartHour(p.automation_start_hour ?? 6);
        setEndHour(p.automation_end_hour ?? 22);
        setXUsernames((p.x_usernames || []).join("\n"));
        setActiveProject(p.active_project || p.monitoring_projects?.[0]?.id || "");
        setTerms(
          p.keywords
            .filter((k: any) => k.is_active)
            .map((k: any) => k.keyword)
            .join("\n"),
        );
      })
      .catch((e) => setError(e.message))
      .finally(finishLoading);
    return finishLoading;
  }, [beginLoading]);
  if (!prefs)
    return <div className="panel empty">{error || "Loading settings…"}</div>;
  async function save(e: React.FormEvent) {
    e.preventDefault();
    const finishLoading = beginLoading("Saving workspace settings…");
    setSaving(true);
    setError("");
    setMessage("");
    const normalizedTerms = Array.from(new Map(
      terms
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean)
        .map((value) => [value.toLocaleLowerCase("en-IN"), value]),
    ).values());
    const normalizedUsernames = Array.from(new Set(
      xUsernames
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean),
    ));
    if (!normalizedTerms.length) {
      setError("Add at least one keyword or hashtag.");
      setSaving(false);
      finishLoading();
      return;
    }
    try {
      await json("/settings", {
        method: "PUT",
        body: JSON.stringify({
          keywords: normalizedTerms,
          x_usernames: normalizedUsernames,
          active_project: activeProject,
          automation_start_hour: startHour,
          automation_end_hour: endHour,
        }),
      });
      setPrefs({
        ...prefs,
        automation_start_hour: startHour,
        automation_end_hour: endHour,
        keywords: normalizedTerms.map((keyword) => ({ keyword, is_active: true })),
        x_usernames: normalizedUsernames,
        active_project: activeProject,
      });
      setTerms(normalizedTerms.join("\n"));
      setXUsernames(normalizedUsernames.join("\n"));
      setEditing(false);
      setMessage("Settings saved. The automatic schedule has been updated.");
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
      finishLoading();
    }
  }
  const selectedProject = (prefs.monitoring_projects || []).find(
    (project: any) => project.id === activeProject,
  );
  return (
    <>
      <form onSubmit={save} className="settings-grid" autoComplete="off">
        <section className="panel settings-section tracked-terms-section">
          <div className="panel-title">
            <div><h2>Monitoring settings</h2><span>Hindi · English · Hinglish</span></div>
            {admin && !editing && <button type="button" className="btn btn-outline-primary"
              onClick={() => { setEditing(true); setMessage(""); setError(""); }}>Edit settings</button>}
          </div>

          <div className="monitoring-project-editor">
            <label>
              Monitoring project
              <select className="form-select" value={activeProject}
                disabled={!admin || !editing}
                onChange={(e) => setActiveProject(e.target.value)}>
                {(prefs.monitoring_projects || []).map((project: any) => (
                  <option key={project.id} value={project.id}>{project.label}</option>
                ))}
              </select>
              <small>The selected project&apos;s additional keywords are combined with the existing keywords below for every source.</small>
            </label>
            {selectedProject && (
              <div className="project-keyword-preview">
                <strong>{selectedProject.keywords.length} additional keywords</strong>
                <p>{selectedProject.keywords.join(" · ")}</p>
              </div>
            )}
          </div>

          <label>
            Keywords and hashtags
            <textarea className="form-control"
              rows={9}
              value={terms}
              onChange={(e) => setTerms(e.target.value)}
              disabled={!admin || !editing}
            />
          </label>
          <label>
            X / Twitter accounts to monitor
            <textarea className="form-control x-account-input"
              rows={4}
              placeholder={"samrat4bjp\nBJP4Bihar\nusername"}
              value={xUsernames}
              onChange={(e) => setXUsernames(e.target.value)}
              disabled={!admin || !editing}
            />
            <small>One username per line. The account’s own posts are fetched even when they do not contain a tracked keyword.</small>
          </label>
          <div className="schedule-editor">
            <div>
              <strong>Active automation window</strong>
              <p>YouTube and Google News run every 15 minutes. Other social sources run every 3 hours.</p>
            </div>
            <label>
              Start time
              <select className="form-select" value={startHour}
                disabled={!admin || !editing} onChange={(e) => setStartHour(Number(e.target.value))}>
                {Array.from({ length: 23 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, "0")}:00</option>)}
              </select>
            </label>
            <label>
              End time
              <select className="form-select" value={endHour}
                disabled={!admin || !editing} onChange={(e) => setEndHour(Number(e.target.value))}>
                {Array.from({ length: 23 }, (_, index) => index + 1).map((hour) => <option key={hour} value={hour}>{String(hour).padStart(2, "0")}:00</option>)}
              </select>
            </label>
            <small>Timezone: {prefs.timezone || "Asia/Kolkata"}</small>
          </div>
        </section>
        <div className="settings-save">
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {message && (
            <p className="success" role="status">
              <Check size={16} />
              {message}
            </p>
          )}
          {admin && editing ? (<>
            <button type="button" className="btn btn-light" disabled={saving} onClick={() => {
              setTerms(prefs.keywords.filter((k: any) => k.is_active).map((k: any) => k.keyword).join("\n"));
              setXUsernames((prefs.x_usernames || []).join("\n"));
              setActiveProject(prefs.active_project || prefs.monitoring_projects?.[0]?.id || "");
              setStartHour(prefs.automation_start_hour ?? 6);
              setEndHour(prefs.automation_end_hour ?? 22);
              setEditing(false);
              setError("");
            }}>Cancel</button>
            <button className="btn btn-primary primary" disabled={saving || startHour >= endHour}>
              {saving ? "Saving…" : "Save settings"}
            </button>
          </>) : !admin ? (
            <p>Viewer access · Ask an administrator to change settings.</p>
          ) : null}
        </div>
      </form>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
