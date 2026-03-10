"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────
interface Incident {
  id: string;
  errorType: string;
  file: string;
  status: "Live" | "Resolved" | "Analyzing";
  time: string;
  severity: "critical" | "high" | "medium" | "low";
  autoFix?: boolean;
  stackTrace?: string;
}

interface DeployData {
  test_passed: boolean;
  docker_unavailable: boolean;
  git_pushed: boolean;
  branch: string;
  commit_message: string;
  details: string;
}

interface ReportData {
  title: string;
  severity: string;
  summary: string;
  root_cause: string;
  proposed_fix: string;
  risk_assessment: string;
  next_steps: string[];
  references: string[];
}

interface AgentEvent {
  id: string;
  agent: string;
  message: string;
  timestamp: string;
  avatar: string;
  diff?: string;
  result?: string;
  status?: "loading" | "success" | "error";
  tool?: string;
  cardType?: "deploy" | "report";
  deployData?: DeployData;
  reportData?: ReportData;
}

// ── Deploy Result Card ──────────────────────────────────────────────────────
function DeployCard({ data, expanded, onToggle }: { data: DeployData; expanded: boolean; onToggle: () => void }) {
  return (
    <div className="mt-3">
      <button
        onClick={onToggle}
        className="w-full text-left flex items-center gap-2 p-3 bg-white/4 hover:bg-white/6 border border-white/8 hover:border-white/15 rounded-xl transition-all duration-200"
      >
        <span className="text-base">{data.git_pushed ? "🚀" : data.docker_unavailable ? "⚠️" : "❌"}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-white">Deploy Summary</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${data.test_passed ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
              }`}>{data.test_passed ? "Tests ✓" : "Tests ✗"}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${data.git_pushed ? "bg-blue-500/20 text-blue-400" : "bg-gray-500/20 text-gray-400"
              }`}>{data.git_pushed ? "Git Pushed ✓" : "Git Push ✗"}</span>
            {data.docker_unavailable && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400">Docker N/A</span>
            )}
          </div>
          {data.git_pushed && (
            <p className="text-[10px] text-gray-500 font-mono mt-0.5 truncate">{data.branch}</p>
          )}
        </div>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round"
          className={`shrink-0 text-gray-500 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {expanded && (
        <div className="mt-2 bg-[#0a0a0c] rounded-xl border border-white/8 overflow-hidden">
          {data.git_pushed && (
            <div className="px-4 py-3 border-b border-white/5">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Commit</p>
              <p className="text-xs text-gray-300 font-mono">{data.commit_message}</p>
              <p className="text-[10px] text-blue-400 font-mono mt-1">{data.branch}</p>
            </div>
          )}
          <div className="px-4 py-3">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Details</p>
            <pre className="text-[11px] font-mono text-gray-400 whitespace-pre-wrap break-all leading-relaxed max-h-48 overflow-y-auto">{data.details}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Report Result Card ──────────────────────────────────────────────────────
const SEV_COLOR: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  low: "bg-blue-500/20 text-blue-400 border-blue-500/30",
};

function ReportCard({ data, expanded, onToggle }: { data: ReportData; expanded: boolean; onToggle: () => void }) {
  return (
    <div className="mt-3">
      <button
        onClick={onToggle}
        className="w-full text-left flex items-center gap-2 p-3 bg-white/4 hover:bg-white/6 border border-white/8 hover:border-white/15 rounded-xl transition-all duration-200"
      >
        <span className="text-base">📋</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-white truncate">{data.title}</span>
            <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded-full border font-medium capitalize ${SEV_COLOR[data.severity] || SEV_COLOR.medium
              }`}>{data.severity}</span>
          </div>
          <p className="text-[10px] text-gray-500 mt-0.5 truncate">{data.summary}</p>
        </div>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round"
          className={`shrink-0 text-gray-500 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {expanded && (
        <div className="mt-2 bg-[#0a0a0c] rounded-xl border border-white/8 overflow-hidden divide-y divide-white/5">
          <div className="px-4 py-3">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Summary</p>
            <p className="text-xs text-gray-300 leading-relaxed">{data.summary}</p>
          </div>
          <div className="px-4 py-3">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Root Cause</p>
            <p className="text-xs text-gray-300 leading-relaxed">{data.root_cause}</p>
          </div>
          <div className="px-4 py-3">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Proposed Fix</p>
            <pre className="text-[11px] font-mono text-green-300 whitespace-pre-wrap break-all leading-relaxed">{data.proposed_fix}</pre>
          </div>
          <div className="px-4 py-3">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Risk Assessment</p>
            <p className="text-xs text-yellow-300 leading-relaxed">{data.risk_assessment}</p>
          </div>
          {data.next_steps?.length > 0 && (
            <div className="px-4 py-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Next Steps</p>
              <ol className="space-y-1">
                {data.next_steps.map((step, i) => (
                  <li key={i} className="text-xs text-gray-300 flex gap-2">
                    <span className="text-blue-400 font-mono shrink-0">{i + 1}.</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {data.references?.length > 0 && (
            <div className="px-4 py-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">References</p>
              <div className="space-y-1">
                {data.references.map((ref, i) => (
                  <a key={i} href={ref} target="_blank" rel="noopener noreferrer"
                    className="block text-[11px] text-blue-400 hover:text-blue-300 font-mono truncate hover:underline transition-colors">
                    {ref}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ── Static incident history ────────────────────────────────────────────────
const INCIDENT_HISTORY: Incident[] = [
  {
    id: "INC-1050",
    errorType: "ZeroDivisionError: division by zero",
    file: "src/utils/calculator.py",
    status: "Live",
    time: "Just now",
    severity: "low",
    autoFix: true,
    stackTrace: `Traceback (most recent call last):
  File "tests/test_calculator.py", line 10, in test_divide_zero
    divide(10, 0)
  File "src/utils/calculator.py", line 4, in divide
    return a / b
ZeroDivisionError: division by zero`
  },
  {
    id: "INC-1049",
    errorType: "BadRequestError: Empty user message content",
    file: "src/utils/litellm-chatbot.py",
    status: "Live",
    time: "Just now",
    severity: "medium",
    autoFix: true,
    stackTrace: `Traceback (most recent call last):
  File "src/utils/litellm-chatbot.py", line 26, in <module>
    chat()
  File "src/utils/litellm-chatbot.py", line 20, in chat
    response = completion(
  File "C:/Users/PC/.venv/lib/site-packages/litellm/main.py", line 1842, in completion
    raise BadRequestError(
litellm.exceptions.BadRequestError: litellm.BadRequestError:
VertexAI: 400 Request contains an invalid argument.
  messages[1].parts[0].text: must be non-empty string.
  Got: user message content = ''`,
  },
  {
    id: "INC-1048",
    errorType: "KeyError: 'discount_pct'",
    file: "src/utils/invoice_generator.py",
    status: "Resolved",
    time: "8m ago",
    severity: "high",
    autoFix: true,
  },
  {
    id: "INC-1047",
    errorType: "TypeError: can't multiply sequence by non-int of type 'float'",
    file: "src/utils/order_processor.py",
    status: "Resolved",
    time: "12m ago",
    severity: "high",
    autoFix: true,
  },
  {
    id: "INC-1046",
    errorType: "KeyError: 'tags'",
    file: "src/utils/data_processor.py",
    status: "Live",
    time: "Just now",
    severity: "critical",
    autoFix: true,
    stackTrace: `Traceback(most recent call last):
      File "src/utils/data_processor.py", line 228, in<module>
    run_sample_pipeline()
  File "src/utils/data_processor.py", line 225, in run_sample_pipeline
    pipeline.process_batch(sample_data)
  File "src/utils/data_processor.py", line 192, in process_batch
    t_event = self.transformer.transform_analytics_event(event)
  File "src/utils/data_processor.py", line 140, in transform_analytics_event
    metadata = self._extract_metadata_deep(raw_event)
  File "src/utils/data_processor.py", line 170, in _extract_metadata_deep
    primary_tag = meta['tags'][0] if meta['tags'] else 'untagged'
KeyError: 'tags'`,
  },
  {
    id: "INC-1045",
    errorType: 'ZeroDivisionError: division by zero',
    file: "src/utils/math_helper.py",
    status: "Live",
    time: "Just now",
    severity: "medium",
    autoFix: true,
    stackTrace: `Traceback(most recent call last):
      File "src/utils/math_helper.py", line 8, in<module>
    calculate_average([])
  File "src/utils/math_helper.py", line 5, in calculate_average
    return total / len(numbers)
           ~~~~~~^ ~~~~~~~~~~~~~
  ZeroDivisionError: division by zero`,
  },
  {
    id: "INC-1044",
    errorType: 'TypeError: can only concatenate str to str',
    file: "src/utils/logger_util.py",
    status: "Live",
    time: "Just now",
    severity: "high",
    autoFix: true,
    stackTrace: `Traceback(most recent call last):
  File "src/utils/logger_util.py", line 7, in <module>
    log_event("user_login", 1)
    File "src/utils/logger_util.py", line 4, in log_event
    print("LOG: Processing " + event_name + " with priority " + priority)
    TypeError: can only concatenate str (not "int") to str`,
  },
  {
    id: "INC-1043",
    errorType: "KeyError: 'email'",
    file: "src/utils/user_loader.py",
    status: "Resolved",
    time: "5m ago",
    severity: "high",
    autoFix: true,
    stackTrace: `Traceback (most recent call last):
    File "main.py", line 22, in batch_load_profiles
    return [load_user_profile(r) for r in records]
    File "src/utils/user_loader.py", line 21, in load_user_profile
    email = record["email"]
    KeyError: 'email'`,
  },
  {
    id: "INC-1042",
    errorType: "ValueError: math domain error",
    file: "src/utils/math_helpers.py",
    status: "Resolved",
    time: "1h ago",
    severity: "high",
  },
  { id: "INC-1041", errorType: "KeyError: 'database_url'", file: "src/utils/data_parser.py", status: "Resolved", time: "3h ago", severity: "medium" },
  { id: "INC-1040", errorType: "ConnectionRefusedError: Redis", file: "src/worker.py", status: "Resolved", time: "6h ago", severity: "critical" },
  { id: "INC-1039", errorType: "UnboundLocalError: local variable", file: "src/utils/processor.py", status: "Resolved", time: "1d ago", severity: "medium" },
];

const AVATAR_MAP: Record<string, string> = {
  error_analyzer: "🪲",
  research_agent: "🔍",
  fix_suggester: "💡",
  auto_fixer: "🤖",
  reporter: "📝",
  system: "⚙️",
  orchestrator: "🧠",
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-yellow-500",
  low: "bg-blue-400",
};

const getTimestamp = () => {
  if (typeof window === "undefined") return "";
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
};

// ── Icons ──────────────────────────────────────────────────────────────────
const BugIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m8 2 1.88 1.88" /><path d="M14.12 3.88 16 2" /><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1" /><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6" /><path d="M12 20v-9" /><path d="M6.53 9C4.6 8.8 3 7.1 3 5" /><path d="M6 13H2" /><path d="M3 21c0-2.1 1.7-3.9 3.8-4" /><path d="M20.97 5c-2 2.1-3.6 3.8-5.53 4" /><path d="M22 13h-4" /><path d="M17.2 17c2.1.1 3.8 1.9 3.8 4" /></svg>
);

const CheckIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
);

const ShieldIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
);

// ── Component ──────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [incidents, setIncidents] = useState<Incident[]>(INCIDENT_HISTORY);
  const [activeIncident, setActiveIncident] = useState<Incident>(INCIDENT_HISTORY[0]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [alertVisible, setAlertVisible] = useState(false);
  const [autoTriggering, setAutoTriggering] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const streamRef = useRef<HTMLDivElement>(null);

  const toggleExpand = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  // Auto-scroll
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [events]);

  // ── WebSocket connection ─────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;
    const ws = new WebSocket(`ws://localhost:8000/ws/events/${sessionId}`);

    ws.onopen = () => {
      addEvent({
        id: `sys-open`,
        agent: "System",
        message: "Connected to live event stream.",
        avatar: "🟢",
        status: "success",
      });
    };

    ws.onmessage = (msg) => {
      const payload = JSON.parse(msg.data);
      const { type, data } = payload;

      if (type === "agent_started") {
        addEvent({
          id: `agent-start-${Date.now()}`,
          agent: data.agent || "Agent",
          message: "Online — reasoning...",
          avatar: AVATAR_MAP[data.agent] || AVATAR_MAP["orchestrator"],
        });
      } else if (type === "orchestrator_stage") {
        addEvent({
          id: `stage-${Date.now()}`,
          agent: "Orchestrator",
          message: `[${(data.stage as string).toUpperCase()}] ${data.message}`,
          avatar: AVATAR_MAP["orchestrator"],
        });
      } else if (type === "orchestrator_complete") {
        addEvent({
          id: `complete-${Date.now()}`,
          agent: "Orchestrator",
          message: data.message,
          avatar: "🎉",
          status: "success",
        });
        setIsRunning(false);
        // Mark incident as resolved in the sidebar
        setIncidents(prev => prev.map(inc =>
          inc.id === activeIncident.id ? { ...inc, status: "Resolved" } : inc
        ));
        setTimeout(() => ws.close(), 500);
      } else if (type === "agent_status") {
        addEvent({
          id: `status-${Date.now()}`,
          agent: data.agent || "Agent",
          message: data.message || "Complete",
          avatar: AVATAR_MAP[data.agent] || AVATAR_MAP["orchestrator"],
          status: data.status === "error" ? "error" : undefined,
        });
        return;
      } else if (type === "tool_trigger") {
        addEvent({
          id: `tool-${data.tool}-${Date.now()}`,
          agent: data.agent || "Agent",
          message: `▶ Running \`${data.tool}\`...`,
          avatar: AVATAR_MAP[data.agent] || AVATAR_MAP["orchestrator"],
          status: "loading",
          tool: data.tool,
        });
      } else if (type === "tool_result") {
        // Try to pretty-print JSON results for readability
        let prettyResult = data.result || "";
        try {
          const parsed = JSON.parse(data.result || "");
          prettyResult = JSON.stringify(parsed, null, 2);
        } catch { /* not JSON, keep raw */ }

        setEvents(prev => {
          // Find the LAST event that matches this tool and is still loading
          let targetIndex = -1;
          for (let i = prev.length - 1; i >= 0; i--) {
            if (prev[i].tool === data.tool && prev[i].status === "loading") {
              targetIndex = i;
              break;
            }
          }

          if (targetIndex !== -1) {
            const next = [...prev];
            next[targetIndex] = {
              ...next[targetIndex],
              status: "success" as const,
              message: `✓ \`${data.tool}\` completed`,
              result: prettyResult,
              diff: (data.result?.includes("@@") || data.result?.includes("---"))
                ? data.result
                : next[targetIndex].diff,
            };
            return next;
          }

          // Fallback: add as new if no matching trigger found
          return [...prev, {
            id: `tool-result-${data.tool}-${Date.now()}`,
            agent: data.agent || "Agent",
            message: `✓ \`${data.tool}\` done`,
            avatar: AVATAR_MAP[data.agent] || AVATAR_MAP["orchestrator"],
            timestamp: getTimestamp(),
            status: "success" as const,
            tool: data.tool,
            result: prettyResult,
          }];
        });
        return; // skip the normal addEvent below
      } else if (type === "deploy_result") {
        addEvent({
          id: `deploy-${Date.now()}`,
          agent: "Orchestrator",
          message: data.git_pushed ? "🚀 Deploy complete" : "⚠️ Deploy skipped",
          avatar: "🔧",
          status: "success",
          cardType: "deploy",
          deployData: data as DeployData,
        });
        return;
      } else if (type === "report_result") {
        addEvent({
          id: `report-${Date.now()}`,
          agent: "Reporter",
          message: `📋 ${data.title}`,
          avatar: AVATAR_MAP["reporter"] || "📝",
          status: "success",
          cardType: "report",
          reportData: data as ReportData,
        });
        return;
      }
    };

    ws.onerror = () => {
      addEvent({
        id: `err-${Date.now()}`,
        agent: "System",
        message: "WebSocket error. Is the backend running on :8000?",
        avatar: "🔴",
        status: "error",
      });
      setIsRunning(false);
    };

    ws.onclose = () => console.log("WS closed");
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const addEvent = useCallback((partial: Omit<AgentEvent, "timestamp">) => {
    setEvents(prev => {
      // Deduplicate by id (e.g., stage-analyzing appears only once)
      if (prev.some(e => e.id === partial.id)) {
        return prev.map(e => e.id === partial.id ? { ...e, ...partial, timestamp: e.timestamp } : e);
      }
      return [...prev, { ...partial, timestamp: getTimestamp() }];
    });
  }, []);

  // ── Auto-trigger on mount: show alert, then start the first Live incident ─
  useEffect(() => {
    const liveIncident = INCIDENT_HISTORY.find(i => i.status === "Live");
    if (!liveIncident) return;

    // Show alert banner after short delay
    const alertTimer = setTimeout(() => setAlertVisible(true), 800);

    // Auto-start the pipeline after banner shows
    const triggerTimer = setTimeout(() => {
      setAutoTriggering(true);
      setAlertVisible(false);
      setTimeout(() => {
        setAutoTriggering(false);
        triggerAnalysis(liveIncident);
      }, 600);
    }, 3500);

    return () => {
      clearTimeout(alertTimer);
      clearTimeout(triggerTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Core analysis trigger ─────────────────────────────────────────────────
  const triggerAnalysis = async (incident: Incident) => {
    if (isRunning) return;
    setActiveIncident(incident);
    setIsRunning(true);
    setEvents([]);
    setSessionId(null);

    // Mark sidebar entry as Analyzing
    setIncidents(prev => prev.map(i =>
      i.id === incident.id ? { ...i, status: "Analyzing" } : i
    ));

    const newSid = crypto.randomUUID();
    await new Promise(r => setTimeout(r, 300));
    setSessionId(newSid);
    await new Promise(r => setTimeout(r, 200));

    try {
      const res = await fetch("http://localhost:8000/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          error_output: incident.stackTrace ||
            `Error in ${incident.file}: ${incident.errorType}`,
          project_name: incident.id,
          session_id_override: newSid,
          auto_apply_fix: incident.autoFix ?? false,
        }),
      });
      const data = await res.json();
      addEvent({
        id: `final-report`,
        agent: "Reporter",
        message: `📄 ${data.title || "Analysis complete."}`,
        avatar: AVATAR_MAP["reporter"],
        status: "success",
      });
    } catch (e) {
      addEvent({
        id: `api-err`,
        agent: "System",
        message: `API Error: ${String(e)}`,
        avatar: "🔴",
        status: "error",
      });
    }
    setIsRunning(false);
  };

  const handleIncidentClick = (inc: Incident) => {
    if (!isRunning) triggerAnalysis(inc);
  };

  return (
    <div className="flex h-screen w-full bg-[#050505] text-[#e0e0e0] font-sans overflow-hidden relative">

      {/* Background blobs */}
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-900/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[40%] h-[50%] rounded-full bg-purple-900/15 blur-[120px] pointer-events-none" />

      {/* ── Auto-detect alert banner ─────────────────────────────────────── */}
      {alertVisible && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-top-4 fade-in duration-500">
          <div className="flex items-center gap-3 px-5 py-3 bg-orange-500/15 border border-orange-500/40 rounded-2xl backdrop-blur-xl shadow-2xl shadow-orange-900/20">
            <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
            <span className="text-sm font-semibold text-orange-300">New error detected</span>
            <span className="text-xs text-gray-400 font-mono">src/utils/user_loader.py · KeyError: &apos;email&apos;</span>
            <div className="ml-3 flex items-center gap-1.5 text-xs text-blue-300">
              <div className="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin" />
              Auto-dispatching agents...
            </div>
          </div>
        </div>
      )}

      {/* ── LEFT SIDEBAR ─────────────────────────────────────────────────── */}
      <aside className="w-80 h-full border-r border-white/8 flex flex-col z-10 shrink-0 bg-black/30 backdrop-blur-md">

        {/* Logo */}
        <div className="p-5 border-b border-white/5 flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-xl border border-blue-500/20">
            <BugIcon />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-tight">Bug Detective</h1>
            <p className="text-[10px] text-gray-500 uppercase tracking-widest">Autonomous Monitor</p>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            <span className="text-[10px] text-green-500 font-mono">LIVE</span>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 divide-x divide-white/5 border-b border-white/5">
          {[
            { label: "Total", value: incidents.length },
            { label: "Live", value: incidents.filter(i => i.status === "Live" || i.status === "Analyzing").length },
            { label: "Fixed", value: incidents.filter(i => i.status === "Resolved").length },
          ].map(s => (
            <div key={s.label} className="py-3 text-center">
              <p className="text-lg font-bold text-white">{s.value}</p>
              <p className="text-[10px] text-gray-500 uppercase tracking-wider">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Incident list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
          <h2 className="text-[10px] uppercase tracking-widest text-gray-600 font-semibold px-1 pt-1 mb-3">Incident Log</h2>
          {incidents.map(inc => {
            const isActive = activeIncident.id === inc.id;
            const isAnalyzing = inc.status === "Analyzing";
            return (
              <button
                key={inc.id}
                onClick={() => handleIncidentClick(inc)}
                disabled={isRunning}
                className={`w-full text-left p-3 rounded-xl border transition-all duration-300 ${isActive
                  ? "bg-white/5 border-blue-500/40 shadow-[0_0_20px_rgba(59,130,246,0.08)]"
                  : "border-transparent hover:bg-white/4 hover:border-white/8"
                  }`}
              >
                <div className="flex items-start gap-2.5">
                  <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${isAnalyzing ? "bg-blue-400 animate-pulse" :
                    inc.status === "Live" ? "bg-red-500 animate-pulse" :
                      "bg-green-500"
                    }`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="text-[10px] font-mono text-gray-500">{inc.id}</span>
                      <span className="text-[10px] text-gray-600">{inc.time}</span>
                    </div>
                    <p className="text-xs text-gray-300 truncate leading-snug">{inc.errorType}</p>
                    <p className="text-[10px] text-gray-600 mt-0.5 truncate font-mono">{inc.file}</p>
                    <div className="flex items-center gap-1.5 mt-2">
                      <span className={`w-[5px] h-[5px] rounded-full ${SEVERITY_COLOR[inc.severity]}`} />
                      <span className="text-[10px] text-gray-600 capitalize">{inc.severity}</span>
                      {inc.autoFix && (
                        <span className="text-[10px] text-purple-400 ml-1">⚡ AutoFix</span>
                      )}
                      {inc.status === "Resolved" && (
                        <span className="ml-auto text-[10px] text-green-500 flex items-center gap-0.5"><CheckIcon /> Fixed</span>
                      )}
                      {inc.status === "Live" && !isActive && (
                        <span className="ml-auto text-[10px] text-orange-400">● New</span>
                      )}
                      {isAnalyzing && (
                        <span className="ml-auto text-[10px] text-blue-400 flex items-center gap-1">
                          <div className="w-2.5 h-2.5 border border-blue-400 border-t-transparent rounded-full animate-spin" />
                          Running
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/5 flex items-center gap-2 text-gray-600">
          <ShieldIcon />
          <span className="text-[10px]">Auto-remediation enabled</span>
        </div>
      </aside>

      {/* ── MAIN PANEL ───────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col h-full overflow-hidden z-10 relative">

        {/* Incident header */}
        <div className="px-6 py-4 border-b border-white/5 bg-black/20 backdrop-blur-sm flex items-center gap-4 shrink-0">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider ${activeIncident.severity === "critical" ? "bg-red-500/20 text-red-400" :
                activeIncident.severity === "high" ? "bg-orange-500/20 text-orange-400" :
                  activeIncident.severity === "medium" ? "bg-yellow-500/20 text-yellow-400" :
                    "bg-blue-500/20 text-blue-400"
                }`}>{activeIncident.severity}</span>
              <span className="text-xs font-mono text-gray-500">{activeIncident.id}</span>
              {activeIncident.autoFix && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400 border border-purple-500/30">
                  ⚡ Auto-Remediation
                </span>
              )}
            </div>
            <h2 className="text-sm font-semibold text-white truncate">{activeIncident.errorType}</h2>
            <p className="text-[10px] font-mono text-gray-500 mt-0.5">{activeIncident.file}</p>
          </div>
          <div className="shrink-0">
            {isRunning ? (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-blue-400">Agents Working</span>
              </div>
            ) : incidents.find(i => i.id === activeIncident.id)?.status === "Resolved" ? (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500/10 border border-green-500/30 rounded-lg">
                <CheckIcon /><span className="text-xs text-green-400">Resolved</span>
              </div>
            ) : null}
          </div>
        </div>

        {/* Stream */}
        <section className="flex-1 p-6 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-4 shrink-0">
            <span className={`w-2 h-2 rounded-full ${isRunning ? "bg-blue-400 animate-pulse" : "bg-gray-700"}`} />
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Agent Activity Stream</h3>
            {autoTriggering && (
              <span className="ml-2 text-xs text-orange-400 animate-pulse">Auto-triggering...</span>
            )}
          </div>

          <div ref={streamRef} className="flex-1 overflow-y-auto space-y-4 pr-2 custom-scrollbar pb-6">
            {events.length === 0 && !isRunning && (
              <div className="flex flex-col items-center justify-center h-full text-center text-gray-700">
                <div className="text-4xl mb-4 opacity-40">📡</div>
                <p className="text-sm">Waiting for incident selection...</p>
              </div>
            )}

            {events.map((ev, index) => (
              <div
                key={ev.id}
                className="flex gap-3.5 animate-in fade-in slide-in-from-bottom-3 duration-400 fill-mode-both"
              >
                {/* Avatar + connector */}
                <div className="flex flex-col items-center shrink-0">
                  <div className="w-9 h-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-lg">
                    {ev.avatar}
                  </div>
                  {index !== events.length - 1 && (
                    <div className="w-px flex-1 bg-gradient-to-b from-white/8 to-transparent mt-2" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 pt-0.5 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-blue-300">{ev.agent}</span>
                    <span className="text-[10px] text-gray-600 font-mono">{ev.timestamp}</span>
                  </div>

                  <div className="bg-[#111]/80 backdrop-blur rounded-xl rounded-tl-none p-3.5 border border-white/5">
                    <p className="text-sm text-gray-200 leading-relaxed break-words">{ev.message}</p>

                    {ev.diff && (
                      <div className="mt-3 bg-[#0a0a0c] rounded-lg border border-white/8 p-3 overflow-x-auto font-mono text-xs">
                        <pre>
                          {ev.diff.split('\n').map((line, i) => (
                            <div key={i} className={`py-px ${line.startsWith('+') ? 'text-green-400 bg-green-500/10' : line.startsWith('-') ? 'text-red-400 bg-red-500/10' : 'text-gray-500'}`}>
                              {line || '\u00A0'}
                            </div>
                          ))}
                        </pre>
                      </div>
                    )}

                    {/* Deploy Result Card */}
                    {ev.cardType === "deploy" && ev.deployData && (
                      <DeployCard
                        data={ev.deployData}
                        expanded={expandedIds.has(ev.id)}
                        onToggle={() => toggleExpand(ev.id)}
                      />
                    )}

                    {/* Report Result Card */}
                    {ev.cardType === "report" && ev.reportData && (
                      <ReportCard
                        data={ev.reportData}
                        expanded={expandedIds.has(ev.id)}
                        onToggle={() => toggleExpand(ev.id)}
                      />
                    )}

                    {/* Status badge — animated transition */}
                    {ev.status === 'loading' && (
                      <div className="mt-3 inline-flex items-center gap-1.5 text-[10px] text-blue-400 bg-blue-500/8 px-2.5 py-1.5 rounded-lg border border-blue-500/20">
                        <div className="w-2.5 h-2.5 border border-blue-400 border-t-transparent rounded-full animate-spin" />
                        {ev.tool ? `Running ${ev.tool}` : "Processing..."}
                      </div>
                    )}
                    {ev.status === 'success' && (
                      <div className="mt-3 flex items-center gap-2 flex-wrap">
                        <div className="inline-flex items-center gap-1.5 text-[10px] text-green-400 bg-green-500/8 px-2.5 py-1.5 rounded-lg border border-green-500/20">
                          <CheckIcon />
                          {ev.tool ? `${ev.tool} done` : "Complete"}
                        </div>
                        {ev.result && (
                          <button
                            onClick={() => toggleExpand(ev.id)}
                            className="inline-flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 bg-white/4 hover:bg-white/8 px-2.5 py-1.5 rounded-lg border border-white/8 hover:border-white/15 transition-all duration-200"
                          >
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={`transition-transform duration-200 ${expandedIds.has(ev.id) ? "rotate-180" : ""}`}>
                              <polyline points="6 9 12 15 18 9" />
                            </svg>
                            {expandedIds.has(ev.id) ? "Hide result" : "Show result"}
                          </button>
                        )}
                      </div>
                    )}
                    {/* Expandable result body */}
                    {ev.result && expandedIds.has(ev.id) && (
                      <div className="mt-3 bg-[#0a0a0c] rounded-lg border border-white/8 overflow-hidden">
                        <div className="flex items-center justify-between px-3 py-2 border-b border-white/5">
                          <span className="text-[10px] text-gray-500 font-mono uppercase tracking-wider">Tool Output · {ev.tool}</span>
                          <span className="text-[10px] text-gray-600">{ev.result.length} chars</span>
                        </div>
                        <pre className="p-3 text-[11px] font-mono text-gray-400 overflow-x-auto max-h-64 overflow-y-auto leading-relaxed whitespace-pre-wrap break-all">{ev.result}</pre>
                      </div>
                    )}

                    {ev.status === 'error' && (
                      <div className="mt-3 inline-flex items-center gap-1.5 text-[10px] text-red-400 bg-red-500/8 px-2.5 py-1.5 rounded-lg border border-red-500/20">
                        ⚠️ Error
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
