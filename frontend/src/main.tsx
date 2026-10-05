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
} from "recharts";
import { Eye, EyeSlash, LayoutDashboard, Radio, Settings, Download, Search, ArrowUpRight, TriangleAlert, ChevronRight, RefreshCw, LogOut, ShieldCheck, CalendarDays, Activity, Check, Close, Bell, Menu , PlatformIcon } from "./icons";
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
  platform: string;
  author: string;
  content: string;
  url: string;
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
    sarcasm_detected?: boolean;
    sarcasm_confidence?: number;
    sarcasm_model_confidence?: number;
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
  timezone: string;
  sources: Source[];
  today: Rollup | null;
  trend: Rollup[];
  platform_totals: Rollup[];
  pending: number;
  threshold: number;
  partial: boolean;
  classifier: {
    status: string;
    model: string;
    threshold?: number;
    fallback_model?: string;
    fallback_configured?: boolean;
    sarcasm_model?: string;
    sarcasm_threshold?: number;
  };
  alerts: Alert[];
};
const names: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X / Twitter",
  youtube: "YouTube",
  news: "News",
};
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
    throw new Error(
      typeof e.detail === "string" ? e.detail : "Please check the form values",
    );
  }
  return response;
}
async function json(path: string, options: RequestInit = {}) {
  return (await api(path, options)).json();
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

function App() {
  const [session, setSession] = useState<{
      role: string;
      email: string;
    } | null>(null),
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
              <span>JanNetra</span>
            </div>
            <p>Political conversations, clearly understood.</p>
          </div>
          <h1>Log in to JanNetra</h1>
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
      logout={() => {
        bearer = "";
        setSession(null);
      }}
    />
  );
}

function Workspace({
  session,
  logout,
}: {
  session: { role: string; email: string };
  logout: () => void;
}) {
  const [view, setView] = useState("overview"),
    [platform, setPlatform] = useState(""),
    [data, setData] = useState<Overview | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0),
    [report, setReport] = useState(false),
    [detail, setDetail] = useState<Alert | null>(null),
    [mobile, setMobile] = useState(false),
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
    const finishLoading = beginLoading("Loading dashboard data…");
    setError("");
    json("/overview" + (platform ? "?platform=" + platform : ""))
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => active && setError(e.message))
      .finally(finishLoading);
    return () => {
      active = false;
      finishLoading();
    };
  }, [platform, revision, beginLoading]);
  useEffect(() => {
    const t = setInterval(() => setRevision((x) => x + 1), 60000);
    return () => clearInterval(t);
  }, []);
  async function refresh() {
    const finishLoading = beginLoading("Refreshing monitoring data…");
    setBusy(true);
    try {
      if (session.role === "admin") await json("/sync", { method: "POST" });
      setRevision((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      finishLoading();
    }
  }
  const active = data?.alerts.find((a) => a.date === data.date),
    selectedSource = data?.sources.find((s) => s.platform === platform),
    disconnected = selectedSource?.status === "disconnected";
  const navigate = (v: string) => {
    setView(v);
    setMobile(false);
  };
  const navigation = [
    ["overview", "Overview", LayoutDashboard],
    ["feed", "Conversation", Radio],
    ["alerts", "Alerts", Bell],
    ["settings", "Settings", Settings],
  ] as const;
  return (
    <GlobalLoadingContext.Provider value={beginLoading}>
    <div className="shell">
      {loadingTasks > 0 && <GlobalLoader message={loadingMessage} />}
      <header className={mobile ? "app-navbar open" : "app-navbar"}>
        <div className="navbar-inner">
          <div className="navbar-brand">
            <span className="navbar-logo"><Eye size={22} /></span>
            <strong>JanNetra</strong>
          </div>
          <button
            className="mobile-toggle"
            aria-label="Toggle navigation"
            aria-expanded={mobile}
            onClick={() => setMobile(!mobile)}
          >
            {mobile ? <Close /> : <Menu />}
          </button>
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
          <div className="navbar-account">
            <span className="avatar">{session.email[0].toUpperCase()}</span>
            <div>
              <strong>{session.role === "admin" ? "Administrator" : "Viewer"}</strong>
              <small>{session.email}</small>
            </div>
            <button title="Sign out" aria-label="Sign out" onClick={logout}>
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </header>
      <main className="workspace-main">
        <div className="content">
          <div className="page-heading">
            <div>
              <p className="eyebrow">BIHAR / SOCIAL INTELLIGENCE</p>
              <h1>
                {view === "overview"
                  ? "Sentiment overview"
                  : view === "feed"
                    ? "Conversation feed"
                    : view === "alerts"
                      ? "Alert centre"
                      : "Workspace settings"}
              </h1>
              <p>
                {view === "overview"
                  ? "The conversation at a glance. Every signal in context."
                  : view === "feed"
                    ? "Explore the posts behind the numbers."
                    : view === "alerts"
                      ? "Threshold breaches, evidence and notification status."
                      : "Manage the terms, sources and thresholds you monitor."}
              </p>
            </div>
            <div className="heading-actions">
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
              <button
                onClick={refresh}
                disabled={busy}
                aria-label="Refresh monitoring data"
              >
                <RefreshCw size={16} className={busy ? "spin" : ""} />
                {busy ? "Refreshing…" : "Refresh"}
              </button>
              <button className="btn btn-primary primary" onClick={() => setReport(true)}>
                <Download size={16} />
                Export report
              </button>
            </div>
          </div>
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
                {view === "settings" ? (
                  <SettingsPanel
                    admin={session.role === "admin"}
                    onSaved={() => setRevision((x) => x + 1)}
                  />
                ) : view === "alerts" ? (
                  <div className="panel alert-list">
                    <div className="panel-title">
                      <h2>Open alerts</h2>
                      <span>{data.alerts.length} reporting days</span>
                    </div>
                    {data.alerts.length ? (
                      data.alerts.map((a) => (
                        <button
                          className="alert-row"
                          key={a.date}
                          onClick={() => setDetail(a)}
                        >
                          <TriangleAlert />
                          <div>
                            <strong>
                              {dateLabel(a.date)} · Negative volume threshold
                              exceeded
                            </strong>
                            <span>
                              {num(a.negative_count)} negative posts · threshold{" "}
                              {num(a.threshold)} ·{" "}
                              {a.notified_channels.join(", ") ||
                                "Delivery pending / channels disabled"}
                            </span>
                          </div>
                          <ChevronRight />
                        </button>
                      ))
                    ) : (
                      <div className="empty">
                        <ShieldCheck />
                        No open threshold alerts.
                      </div>
                    )}
                  </div>
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
                            today ·{" "}
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
                        {dateLabel(data.date)}, {data.date.slice(0, 4)}
                      </span>
                    </div>
                    {disconnected ? (
                      <div className="panel empty">
                        <Radio size={32} />
                        <h2>{names[platform]} is not connected</h2>
                        <p>
                          Connect an owned/managed account or a compliant
                          social-listening provider in Settings.
                        </p>
                        <p>This platform is excluded from all totals.</p>
                        <button onClick={() => setView("settings")}>
                          Manage connection
                          <ChevronRight size={16} />
                        </button>
                      </div>
                    ) : (
                      <>
                        {view === "overview" && (
                          <>
                            <div className="stats">
                              <Stat
                                label="TOTAL CLASSIFIED"
                                value={
                                  data.today ? num(data.today.total_count) : "—"
                                }
                                note={
                                  data.today
                                    ? "Across connected sources"
                                    : "No classified data available"
                                }
                                icon={<Activity size={18} />}
                              />
                              <Stat
                                label="POSITIVE"
                                value={
                                  data.today
                                    ? num(data.today.positive_count)
                                    : "—"
                                }
                                note={
                                  data.today
                                    ? `${((data.today.positive_count / data.today.total_count) * 100).toFixed(1)}% of classified conversation`
                                    : "Awaiting data"
                                }
                                tone="positive"
                              />
                              <Stat
                                label="NEGATIVE"
                                value={
                                  data.today
                                    ? num(data.today.negative_count)
                                    : "—"
                                }
                                note={
                                  data.today
                                    ? `${((data.today.negative_count / data.today.total_count) * 100).toFixed(1)}% of classified conversation`
                                    : "Awaiting data"
                                }
                                tone="negative"
                              />
                              <Stat
                                label="MIXED"
                                value={
                                  data.today
                                    ? num(data.today.mixed_count || 0)
                                    : "â€”"
                                }
                                note={
                                  data.today
                                    ? `${(((data.today.mixed_count || 0) / data.today.total_count) * 100).toFixed(1)}% with both positive and negative stance`
                                    : "Awaiting data"
                                }
                                tone="mixed"
                              />
                              <Stat
                                label="NEGATIVITY INDEX"
                                value={
                                  data.today
                                    ? data.today.negativity_index.toFixed(1) +
                                      "%"
                                    : "—"
                                }
                                note="Negative ÷ classified posts"
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
                                  <h2>Today’s sentiment</h2>
                                  <span>Share of voice</span>
                                </div>
                                {data.today ? (
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
                                                  data.today![
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
                                          {num(data.today.total_count)}
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
                                                data.today![
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
                                    of 4 connected
                                  </span>
                                </div>
                                <div className="source-grid">
                                  {data.sources.map((s) => (
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
                                            : "source-state"
                                        }
                                      >
                                        {s.status === "unavailable"
                                          ? "Data unavailable"
                                          : s.source}
                                      </span>
                                      <small>
                                        {s.status === "disconnected"
                                          ? "Excluded from totals"
                                          : s.error ||
                                            "Includes classified mentions"}
                                      </small>
                                    </button>
                                  ))}
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
                                          setView("feed");
                                          window.dispatchEvent(
                                            new CustomEvent("filter-day", {
                                              detail: day,
                                            }),
                                          );
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
                        <Feed
                          platform={platform}
                          revision={revision}
                          defaultDay={data.date}
                          compact={view === "overview"}
                          onExpand={() => setView("feed")}
                        />
                      </>
                    )}
                  </>
                )}
              </>
            )
          )}
          <footer>
            <span>
              <Eye size={14} /> JanNetra ·{" "}
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
          <h3>Five most-engaged negative posts</h3>
          {detail.top_negative_posts.map((p) => (
            <div className="evidence" key={p._id}>
              <span>
                {names[p.platform]} · {num(p.engagement_score)} interactions
              </span>
              <p>{p.content}</p>
              {p.url && (
                <a href={p.url} target="_blank" rel="noreferrer">
                  View source ↗
                </a>
              )}
            </div>
          ))}
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

function Feed({
  platform,
  revision,
  defaultDay,
  compact,
  onExpand,
}: {
  platform: string;
  revision: number;
  defaultDay: string;
  compact: boolean;
  onExpand: () => void;
}) {
  const beginLoading = React.useContext(GlobalLoadingContext);
  const [q, setQ] = useState(""),
    [term, setTerm] = useState(""),
    [sentiment, setSentiment] = useState(""),
    [sort, setSort] = useState("engagement"),
    [day, setDay] = useState(defaultDay),
    [page, setPage] = useState(1),
    [posts, setPosts] = useState<{ items: Post[]; total: number } | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setTerm(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    const fn = (e: Event) => setDay((e as CustomEvent).detail);
    window.addEventListener("filter-day", fn);
    return () => window.removeEventListener("filter-day", fn);
  }, []);
  useEffect(() => setPage(1), [platform, term, sentiment, sort, day]);
  useEffect(() => {
    let active = true;
    const finishLoading = beginLoading("Loading conversations…");
    setError("");
    setLoading(true);
    const p = new URLSearchParams({ q: term, sort, page: String(page) });
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
  }, [platform, term, sentiment, sort, page, revision, day, beginLoading]);
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
          <option value="engagement">Most engaged</option>
          <option value="recency">Most recent</option>
        </select>
        {!compact && (
          <input className="form-control"
            type="date"
            aria-label="Filter date"
            value={day}
            onChange={(e) => setDay(e.target.value)}
          />
        )}
        {day && <button onClick={() => setDay("")}>Clear date</button>}
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
          {posts?.items.slice(0, compact ? 4 : 20).map((p) => (
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
                <p>{p.content}</p>
                {p.url && /^https:\/\//.test(p.url) && (
                  <a href={p.url} target="_blank" rel="noreferrer">
                    Open original
                    <ArrowUpRight size={12} />
                  </a>
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
                      {p.sentiment.sarcasm_detected
                        ? ` · Sarcasm ${Math.round((p.sentiment.sarcasm_confidence || 0) * 100)}%`
                        : ""}
                      {p.sentiment.review_required ? " · Review" : ""}
                    </small>
                  </>
                ) : (
                  <span className="muted">{p.classification_status === "awaiting_groq" ? "Awaiting Groq" : "Pending"}</span>
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
          ))}
        </div>
      )}
      {!compact && posts && (
        <div className="pagination">
          <span>
            Page {page} of {Math.max(1, Math.ceil(posts.total / 20))}
          </span>
          <button disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </button>
          <button
            disabled={page * 20 >= posts.total}
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
              `/export?period=${period}&format=${format}`,
            );
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement("a");
            a.href = url;
            a.download = `jannetra-${period}.${format}`;
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
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [credential, setCredential] = useState<any>(null);
  useEffect(() => {
    const finishLoading = beginLoading("Loading workspace settings…");
    json("/settings")
      .then((p) => {
        setPrefs(p);
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
    try {
      await json("/settings", {
        method: "PUT",
        body: JSON.stringify({
          threshold: Number(prefs.threshold),
          keywords: terms.split("\n").filter(Boolean),
          email: prefs.email,
          email_enabled: prefs.email_enabled,
          webhook_enabled: prefs.webhook_enabled,
          webhook_url: prefs.webhook_enabled ? prefs.webhook_url || "" : "",
        }),
      });
      setMessage(
        "Workspace settings saved. Threshold changes take effect on the next sync.",
      );
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
      finishLoading();
    }
  }
  return (
    <>
      <form onSubmit={save} className="settings-grid" autoComplete="off">
        <section className="panel settings-section">
          <div className="panel-title">
            <h2>Tracked terms</h2>
            <span>Hindi · English · Hinglish</span>
          </div>
          <p>
            One term per line. “PK” may include unrelated mentions; review
            low-confidence results.
          </p>
          <label>
            Keywords and hashtags
            <textarea className="form-control"
              rows={9}
              value={terms}
              onChange={(e) => setTerms(e.target.value)}
              disabled={!admin}
            />
          </label>
        </section>
        <section className="panel settings-section">
          <div className="panel-title">
            <h2>Alert rules & delivery</h2>
          </div>
          <label>
            Daily negative-post threshold
            <input className="form-control"
              type="number"
              min={1}
              max={10000000}
              value={prefs.threshold}
              onChange={(e) =>
                setPrefs({ ...prefs, threshold: e.target.value })
              }
              disabled={!admin}
            />
          </label>
          <p>
            An alert fires when the count is strictly greater than this
            threshold.
          </p>
          <label className="check-label">
            <input className="form-check-input"
              type="checkbox"
              checked={prefs.email_enabled}
              disabled={!admin}
              onChange={(e) =>
                setPrefs({ ...prefs, email_enabled: e.target.checked })
              }
            />
            Email notifications
          </label>
          <label>
            Recipient
            <input className="form-control"
              type="email"
              value={prefs.email}
              disabled={!admin}
              onChange={(e) => setPrefs({ ...prefs, email: e.target.value })}
              placeholder="analyst@example.org"
            />
          </label>
          <label className="check-label">
            <input className="form-check-input"
              type="checkbox"
              checked={prefs.webhook_enabled}
              disabled={!admin}
              onChange={(e) =>
                setPrefs({ ...prefs, webhook_enabled: e.target.checked })
              }
            />
            Webhook notifications
          </label>
          <label>
            HTTPS webhook URL
            <input className="form-control"
              type="password"
              value={prefs.webhook_url || ""}
              disabled={!admin}
              onChange={(e) =>
                setPrefs({ ...prefs, webhook_url: e.target.value })
              }
              placeholder="Leave blank to keep existing endpoint"
              autoComplete="new-password"
            />
          </label>
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
          {admin ? (
            <button className="btn btn-primary primary" disabled={saving}>
              {saving ? "Saving…" : "Save settings"}
            </button>
          ) : (
            <p>Viewer access · Ask an administrator to change settings.</p>
          )}
        </div>
      </form>
      <section className="panel settings-section connections">
        <div className="panel-title">
          <h2>API connections</h2>
          <span>Secrets are encrypted and never returned</span>
        </div>
        {Object.entries(names).map(
          ([key, name]) => {
            const src = prefs.sources.find((s: Source) => s.platform === key);
            const c = prefs.credentials.find((c: any) => c.platform === key);
            return (
              <div className="connection" key={key}>
                <div>
                  <strong>{name}</strong>
                  <p>
                    {key === "youtube"
                      ? "Official Data API v3 - quota-aware schedule"
                      : "Apify Actor - configured source monitoring"}
                  </p>
                </div>
                <span>
                  {src?.source ||
                    c?.status ||
                    "Not connected"}
                </span>
                <button
                  disabled={!admin}
                  onClick={() =>
                    setCredential({
                      platform: key,
                      mode: key === "youtube" ? "official" : "apify",
                      api_key: "",
                      actor_id: "",
                      input_template: "",
                      max_items: 200,
                    })
                  }
                >
                  Configure
                </button>
              </div>
            );
          },
        )}
      </section>
      <section className="panel settings-section connections">
        <div className="panel-title"><h2>Sentiment classifier</h2><span>Sentiment + sarcasm + Groq fallback</span></div>
        <strong>{prefs.model}</strong>
        <p>Status: {prefs.classifier?.status || "pending"}</p>
        <p>Sarcasm detector: {prefs.classifier?.sarcasm_model || "ashish5193/sarcasm_model"}</p>
        <p>YouTube uses video titles only. Local sentiment, language, entity and sarcasm signals produce target-wise sentiment. Only combined confidence below {Math.round((prefs.classifier?.threshold ?? 0.60) * 100)}% is sent to Groq. Confidence is not a guarantee of accuracy.</p>
        <p>Groq fallback: {prefs.classifier?.fallback_configured ? `configured (${prefs.classifier?.fallback_model || "server model"})` : "key missing - low-confidence items remain pending"}. Models and threshold are configured through the server environment.</p>
        {prefs.classifier?.error && <p className="error">{prefs.classifier.error}</p>}
      </section>
      {credential && (
        <Modal
          title={"Configure " + (names[credential.platform] || "Platform")}
          close={() => setCredential(null)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const finishLoading = beginLoading("Saving API connection…");
              setError("");
              try {
                await json("/credentials", {
                  method: "PUT",
                  body: JSON.stringify(credential),
                });
                setCredential(null);
                onSaved();
                setMessage("Connection saved. Run Refresh to verify access.");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                finishLoading();
              }
            }}
          >
            <label>
              {credential.platform === "youtube" ? "YouTube API key" : "Apify API token"}
              <input className="form-control"
                type="password"
                autoComplete="new-password"
                required
                minLength={10}
                value={credential.api_key}
                onChange={(e) =>
                  setCredential({ ...credential, api_key: e.target.value })
                }
              />
            </label>
            {credential.mode === "apify" && (
              <details>
                <summary>Advanced Actor override (optional)</summary>
                <p>Leave these blank to use JanNetra's tested default Actor and input for this source.</p>
                <label>
                  Apify Actor ID
                  <input className="form-control"
                    placeholder="Default selected automatically"
                    value={credential.actor_id}
                    onChange={(e) => setCredential({ ...credential, actor_id: e.target.value })}
                  />
                </label>
                <label>
                  Actor input JSON template
                  <textarea className="form-control" rows={6}
                    placeholder="Default input selected automatically"
                    value={credential.input_template}
                    onChange={(e) => setCredential({ ...credential, input_template: e.target.value })}
                  />
                  <small>Placeholders: {'{{keywords_json}}'}, {'{{query}}'}, {'{{since_iso}}'}, {'{{max_items}}'}</small>
                </label>
                <label>
                  Maximum items per run
                  <input className="form-control" type="number" min={1} max={1000}
                    value={credential.max_items}
                    onChange={(e) => setCredential({ ...credential, max_items: Number(e.target.value) })}
                  />
                </label>
              </details>
            )}
            {error && <p className="error">{error}</p>}
            <button className="btn btn-primary primary">Save encrypted credential</button>
          </form>
        </Modal>
      )}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
