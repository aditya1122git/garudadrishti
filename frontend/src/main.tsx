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
import { Eye, LayoutDashboard, Radio, Settings, Download, Search, ArrowUpRight, TriangleAlert, ChevronRight, RefreshCw, LogOut, ShieldCheck, CalendarDays, Activity, Check, Close, Bell, Menu , PlatformIcon } from "./icons";
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
  } | null;
  demo: boolean;
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
  demo: boolean;
  date: string;
  timezone: string;
  sources: Source[];
  today: Rollup | null;
  trend: Rollup[];
  platform_totals: Rollup[];
  pending: number;
  threshold: number;
  partial: boolean;
  classifier: { status: string; model: string };
  alerts: Alert[];
};
const names: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X / Twitter",
  youtube: "YouTube",
};
const colors = { positive: "#2f9278", negative: "#ce514e", neutral: "#a0adbb" };
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

function App() {
  const [session, setSession] = useState<{
      role: string;
      email: string;
    } | null>(null),
    [demo, setDemo] = useState(false),
    [error, setError] = useState(""),
    [loginBusy, setLoginBusy] = useState(false);
  useEffect(() => {
    fetch("/api/auth/mode")
      .then((r) => r.json())
      .then((r) => setDemo(r.demo))
      .catch(() =>
        setError("JanNetra cannot reach the server. Please try again."),
      );
  }, []);
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
        <div className="login-story">
          <div className="brand">
            <Eye /> JanNetra<span>जननेत्र</span>
          </div>
          <div>
            <p className="eyebrow">SOCIAL SENTIMENT WATCHTOWER</p>
            <h1>
              Listen closely.
              <br />
              See the whole picture.
            </h1>
            <p>One workspace for the conversations shaping Bihar.</p>
            <div className="login-rule" />
            <span>JAN SURAAJ PARTY &nbsp; / &nbsp; PRASHANT KISHORE</span>
          </div>
          <small>Responsible monitoring · Aggregate public conversation</small>
        </div>
        <form className="login-form" onSubmit={login}>
          <ShieldCheck size={32} />
          <h2>Welcome to your watchtower</h2>
          <p>Sign in to the analyst workspace.</p>
          {demo && (
            <div className="demo-note">
              <strong>Demonstration workspace</strong>
              <br />
              Synthetic posts. No live monitoring or notifications.
              <br />
              <small>Demo password: JanNetra-Demo-2026!</small>
            </div>
          )}
          <label>
            Email
            <input className="form-control"
              name="email"
              type="email"
              required
              defaultValue={demo ? "admin@jannetra.local" : ""}
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <input className="form-control"
              name="password"
              type="password"
              required
              defaultValue={demo ? "JanNetra-Demo-2026!" : ""}
              autoComplete="current-password"
            />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="btn btn-primary primary" disabled={loginBusy}>
            {loginBusy ? "Signing in…" : "Enter workspace"}
            <ChevronRight size={17} />
          </button>
          <small>Access is logged. Sessions expire after 60 minutes.</small>
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
    [mobile, setMobile] = useState(false);
  useEffect(() => {
    let active = true;
    setError("");
    json("/overview" + (platform ? "?platform=" + platform : ""))
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [platform, revision]);
  useEffect(() => {
    const t = setInterval(() => setRevision((x) => x + 1), 60000);
    return () => clearInterval(t);
  }, []);
  async function refresh() {
    setBusy(true);
    try {
      if (session.role === "admin") await json("/sync", { method: "POST" });
      setRevision((x) => x + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const active = data?.alerts.find((a) => a.date === data.date),
    selectedSource = data?.sources.find((s) => s.platform === platform),
    disconnected = selectedSource?.status === "disconnected";
  const navigate = (v: string) => {
    setView(v);
    setMobile(false);
  };
  return (
    <div className="shell">
      <aside className={mobile ? "sidebar open" : "sidebar"}>
        <div className="brand">
          <Eye size={28} />
          <div>
            JanNetra<small>THE SENTIMENT WATCHTOWER</small>
          </div>
        </div>
        <div className="workspace-tag">
          <span className="square">B</span>
          <div>
            Bihar intelligence<small>Political monitoring workspace</small>
          </div>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {[
            ["overview", "Overview", LayoutDashboard],
            ["feed", "Conversation feed", Radio],
            ["alerts", "Alert centre", Bell],
            ["settings", "Settings", Settings],
          ].map(([key, label, Icon]) => (
            <button
              key={String(key)}
              className={view === key ? "active" : ""}
              onClick={() => navigate(String(key))}
            >
              {React.createElement(Icon as typeof Eye, { size: 18 })}
              <span>{String(label)}</span>
              {key === "alerts" && !!data?.alerts.length && (
                <b>{data.alerts.length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-monitor">
          <p className="nav-label">TRACKING FOCUS</p>
          <strong>Jan Suraaj Party</strong>
          <span>Prashant Kishore · PK</span>
          <span>Hindi · English · Hinglish</span>
          <div className="side-rule" />
          <ShieldCheck size={17} />
          <span> Official APIs & compliant providers</span>
        </div>
        <div className="sidebar-bottom">
          {data?.demo && <span className="demo-pill">DEMO WORKSPACE</span>}
          <div className="user">
            <span className="avatar">{session.email[0].toUpperCase()}</span>
            <div>
              {session.role === "admin" ? "Administrator" : "Viewer"}
              <small>{session.email}</small>
            </div>
            <button title="Sign out" aria-label="Sign out" onClick={logout}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            <button
              className="mobile-toggle"
              aria-label="Open navigation"
              onClick={() => setMobile(!mobile)}
            >
              <Menu />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {view === "feed"
                ? "Conversation feed"
                : view === "alerts"
                  ? "Alert centre"
                  : view === "settings"
                    ? "Settings"
                    : "Overview"}
            </strong>
          </div>
          <span className="timezone">
            <span className="status-dot" />{" "}
            {data?.demo ? "Demo data" : "Monitoring workspace"} <i /> IST ·
            Asia/Kolkata
          </span>
        </header>
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
          {data?.demo && (
            <div className="demo-strip">
              <span className="demo-pill">DEMO</span> All posts and sentiment
              labels are synthetic. External notifications are disabled.
              <span className="demo-scope">X + YouTube sample data</span>
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
                    demo={data.demo}
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
                              {data.demo
                                ? "Demo — delivery disabled"
                                : a.notified_channels.join(", ") ||
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
                    {(data.partial ||
                      data.pending > 0 ||
                      ["unavailable", "disconnected"].includes(
                        data.classifier.status,
                      )) && (
                      <div className="warning">
                        {data.partial
                          ? "Some sources are unavailable. Figures are partial and may be stale. "
                          : ""}
                        {data.pending > 0
                          ? `${num(data.pending)} posts await classification. `
                          : ""}
                        {["unavailable", "disconnected"].includes(
                          data.classifier.status,
                        )
                          ? "Sentiment engine unavailable."
                          : ""}
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
                                    of 4 connected{data.demo ? " in demo" : ""}
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
              {data?.demo
                ? "Synthetic demonstration"
                : "Public conversation monitoring"}
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
            {data?.demo
              ? "Demo alert. No external notification was sent."
              : `Delivered: ${detail.notified_channels.join(", ") || "None"}`}
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
  compact,
  onExpand,
}: {
  platform: string;
  revision: number;
  compact: boolean;
  onExpand: () => void;
}) {
  const [q, setQ] = useState(""),
    [term, setTerm] = useState(""),
    [sentiment, setSentiment] = useState(""),
    [sort, setSort] = useState("engagement"),
    [day, setDay] = useState(""),
    [page, setPage] = useState(1),
    [posts, setPosts] = useState<{ items: Post[]; total: number } | null>(null),
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
    setError("");
    const p = new URLSearchParams({ q: term, sort, page: String(page) });
    if (platform) p.set("platform", platform);
    if (sentiment) p.set("sentiment", sentiment);
    if (day) p.set("day", day);
    json("/posts?" + p)
      .then((p) => active && setPosts(p))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [platform, term, sentiment, sort, page, revision, day]);
  return (
    <section className="panel feed">
      <div className="panel-title">
        <div>
          <h2>{compact ? "Conversation watch" : "Recent posts"}</h2>
          <p>
            {posts ? num(posts.total) + " matching posts" : "Loading posts…"}
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
                    {p.demo ? " · Sample" : ""}
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
                      {p.sentiment.confidence < 0.7 ? " · Review" : ""}
                    </small>
                  </>
                ) : (
                  <span className="muted">Pending</span>
                )}
              </div>
              <div>
                <strong>{num(p.engagement_score)}</strong>
                <small>
                  {num(p.engagement.likes)} likes · {num(p.engagement.comments)}{" "}
                  replies
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
  demo,
  onSaved,
}: {
  admin: boolean;
  demo: boolean;
  onSaved: () => void;
}) {
  const [prefs, setPrefs] = useState<any>(null),
    [terms, setTerms] = useState(""),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [credential, setCredential] = useState<any>(null);
  useEffect(() => {
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
      .catch((e) => setError(e.message));
  }, []);
  if (!prefs)
    return <div className="panel empty">{error || "Loading settings…"}</div>;
  async function save(e: React.FormEvent) {
    e.preventDefault();
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
          {demo && (
            <p className="warning">
              Demo mode never sends email or webhook notifications.
            </p>
          )}
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
                    {key === "facebook" || key === "instagram"
                        ? "Owned/managed Graph API or a compliant paid provider"
                        : key === "x"
                          ? "Requires paid public-search access"
                          : "Official Data API v3 · quota-aware schedule"}
                  </p>
                </div>
                <span>
                  {src?.source ||
                    c?.status ||
                    "Not connected"}
                </span>
                <button
                  disabled={!admin || demo}
                  onClick={() =>
                    setCredential({
                      platform: key,
                      mode: "official",
                      api_key: "",
                      account_id: "",
                      endpoint: "",
                      replacements: "",
                    })
                  }
                >
                  Configure
                </button>
              </div>
            );
          },
        )}
        {demo && (
          <p className="muted">
            Credential entry is disabled in demo mode. Switch to live mode
            before connecting real accounts.
          </p>
        )}
      </section>
      <section className="panel settings-section connections">
        <div className="panel-title"><h2>Sentiment classifier</h2><span>Hugging Face · Local inference</span></div>
        <strong>{prefs.model}</strong>
        <p>Status: {demo ? "Demo labels (model not run)" : prefs.classifier?.status || "pending"}</p>
        <p>Post text stays on this server. The model classifies overall tone, not stance toward a particular person. Review Hinglish, sarcasm and low-confidence results.</p>
        <p>Model and device are configured through the server environment. No classifier API key is required for the default public model.</p>
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
              setError("");
              try {
                await json("/credentials", {
                  method: "PUT",
                  body: JSON.stringify({
                    ...credential,
                    replacement_tokens: credential.replacements
                      .split("\n")
                      .filter(Boolean),
                  }),
                });
                setCredential(null);
                onSaved();
                setMessage("Connection saved. Run Refresh to verify access.");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            {["facebook", "instagram"].includes(credential.platform) && (
              <label>
                Connection mode
                <select className="form-select"
                  value={credential.mode}
                  onChange={(e) =>
                    setCredential({ ...credential, mode: e.target.value })
                  }
                >
                  <option value="official">
                    Official Graph API · owned/managed
                  </option>
                  <option value="aggregator">
                    Compliant third-party aggregator
                  </option>
                </select>
              </label>
            )}
            <label>
              API key / access token
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
            {["facebook", "instagram"].includes(credential.platform) &&
              credential.mode === "official" && (
                <label>
                  Owned/managed account ID
                  <input className="form-control"
                    required
                    value={credential.account_id}
                    onChange={(e) =>
                      setCredential({
                        ...credential,
                        account_id: e.target.value,
                      })
                    }
                  />
                </label>
              )}
            {credential.mode === "aggregator" && (
              <label>
                Provider adapter HTTPS endpoint
                <input className="form-control"
                  type="url"
                  required
                  value={credential.endpoint}
                  onChange={(e) =>
                    setCredential({ ...credential, endpoint: e.target.value })
                  }
                />
              </label>
            )}
            {credential.platform === "x" && (
              <label>
                Replacement tokens (one per line)
                <textarea className="form-control"
                  value={credential.replacements}
                  onChange={(e) =>
                    setCredential({
                      ...credential,
                      replacements: e.target.value,
                    })
                  }
                />
              </label>
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
