import { Activity, AlertTriangle, CheckCircle2, Circle, Sparkles, X } from "lucide-react";
import type { AIGradingPipelineStatus, FinalGradingResult } from "../api/types";
import { formatNumber } from "../utils/format";

type AIGradingModalProps = {
  open: boolean;
  pipeline: AIGradingPipelineStatus | null;
  error?: string | null;
  debugMode: boolean;
  isRunning: boolean;
  onRetry: () => void;
  onClose: () => void;
};

type TimelineStep = {
  phase: "Phase A" | "Phase B";
  key: string;
  label: string;
  threshold: number;
};

const timeline: TimelineStep[] = [
  { phase: "Phase A", key: "preprocessing", label: "Image preprocessing", threshold: 18 },
  { phase: "Phase A", key: "centering", label: "Centering analysis", threshold: 28 },
  { phase: "Phase A", key: "visual_condition", label: "Visual condition analysis", threshold: 37 },
  { phase: "Phase B", key: "phase_a_completed", label: "Phase A completed", threshold: 58 },
  { phase: "Phase B", key: "surface_inspection", label: "Surface inspection", threshold: 64 },
  { phase: "Phase B", key: "defect_analysis", label: "Defect analysis", threshold: 74 },
  { phase: "Phase B", key: "final_grade", label: "Final grade calculation", threshold: 92 },
];

function stepState(step: TimelineStep, progress: number, currentStep: string, completed: boolean, error: boolean) {
  if (completed || progress >= step.threshold + 10) return "done";
  if (error && currentStep === step.key) return "error";
  if (currentStep === step.key || Math.abs(progress - step.threshold) <= 8) return "active";
  return "pending";
}

function displayGrade(value?: number | string | null): string {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "number") return formatNumber(value);
  return value;
}

function finalResult(pipeline: AIGradingPipelineStatus | null): FinalGradingResult | null {
  return pipeline?.final_result ?? pipeline?.phase_b_result ?? null;
}

function ProgressRing({ progress, complete, error }: { progress: number; complete: boolean; error: boolean }) {
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.max(0, Math.min(100, progress)) / 100) * circumference;
  return (
    <div className="relative grid h-28 w-28 place-items-center">
      <div className={`absolute inset-2 rounded-full blur-2xl ${error ? "bg-rose-400/25" : complete ? "bg-emerald-300/25" : "bg-cyan-300/25 animate-pulse"}`} />
      <svg className="-rotate-90" width="112" height="112" viewBox="0 0 112 112" aria-hidden="true">
        <circle cx="56" cy="56" r={radius} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="8" />
        <circle
          cx="56"
          cy="56"
          r={radius}
          fill="none"
          stroke={error ? "rgb(251,113,133)" : complete ? "rgb(52,211,153)" : "rgb(103,232,249)"}
          strokeLinecap="round"
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-2xl font-semibold text-white">{Math.round(progress)}%</div>
        <div className="text-[10px] font-semibold uppercase text-slate-400">{complete ? "Done" : error ? "Paused" : "Analyzing"}</div>
      </div>
    </div>
  );
}

function StepIcon({ state }: { state: "done" | "active" | "pending" | "error" }) {
  if (state === "done") return <CheckCircle2 size={17} className="text-emerald-300" />;
  if (state === "error") return <AlertTriangle size={17} className="text-rose-300" />;
  if (state === "active") return <Activity size={17} className="text-cyan-200 animate-pulse" />;
  return <Circle size={17} className="text-slate-500" />;
}

export function AIGradingModal({ open, pipeline, error, debugMode, isRunning, onRetry, onClose }: AIGradingModalProps) {
  if (!open) return null;
  const progress = pipeline?.progress_state?.progress ?? pipeline?.progress ?? (isRunning ? 14 : 0);
  const phase = pipeline?.progress_state?.phase ?? pipeline?.phase ?? "phase_a";
  const currentStep = pipeline?.progress_state?.step ?? pipeline?.step ?? "preprocessing";
  const statusLabel = pipeline?.progress_state?.status_label ?? pipeline?.status_label ?? (isRunning ? "preprocessing running" : "not started");
  const result = finalResult(pipeline);
  const completed = pipeline?.status === "completed" || Boolean(result);
  const hasError = Boolean(error) || pipeline?.status === "failed" || pipeline?.status === "phase_b_failed";
  const grade = result?.overall_score ?? result?.estimated_grade;

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center overflow-y-auto bg-[#0d1117]/76 p-3 backdrop-blur-2xl sm:p-6">
      <div className="glass-surface relative my-auto w-full max-w-4xl overflow-hidden rounded-[30px]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(103,232,249,0.2),transparent_34%),radial-gradient(circle_at_80%_0%,rgba(167,139,250,0.14),transparent_30%)]" />
        <div className="relative grid max-h-[92vh] gap-5 overflow-y-auto p-4 sm:p-6 lg:grid-cols-[260px_1fr]">
          <div className="glass-card p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs font-semibold text-cyan-100">
                <Sparkles size={14} />
                CardGrader AI
              </div>
              {!isRunning && (
                <button className="rounded-full p-2 text-slate-300 hover:bg-white/10 hover:text-white" onClick={onClose} type="button" aria-label="Close AI grading modal">
                  <X size={18} />
                </button>
              )}
            </div>
            <div className="mt-6 flex justify-center">
              <ProgressRing progress={completed ? 100 : progress} complete={completed} error={hasError} />
            </div>
            <div className="mt-5 text-center">
              <h2 className="text-xl font-semibold text-white">{completed ? "Grading complete" : hasError ? "Grading needs attention" : "AI grading in progress"}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-300">{statusLabel}</p>
            </div>
            {completed && (
              <div className="mt-5 rounded-3xl border border-emerald-300/20 bg-emerald-300/10 p-4 text-center shadow-[0_0_34px_rgba(52,211,153,0.12)]">
                <div className="text-xs font-semibold uppercase text-emerald-100">Final grade</div>
                <div className="mt-1 animate-[pulse_1.6s_ease-in-out_1] text-5xl font-semibold text-white">{displayGrade(grade)}</div>
                <div className="mt-2 text-sm text-emerald-100">Confidence: {displayGrade(result?.confidence)}</div>
              </div>
            )}
          </div>

          <div className="grid gap-4">
            <div className="glass-card p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase text-slate-400">{phase.replace("_", " ")}</div>
                <div className="mt-1 text-lg font-semibold text-white">{currentStep.split("_").join(" ")}</div>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-white/10 sm:w-56">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${hasError ? "bg-rose-300" : completed ? "bg-emerald-300" : "bg-cyan-300 shadow-[0_0_18px_rgba(103,232,249,0.65)]"}`}
                    style={{ width: `${completed ? 100 : progress}%` }}
                  />
                </div>
              </div>
              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {(["Phase A", "Phase B"] as const).map((phaseName) => (
                  <div key={phaseName} className="rounded-2xl border border-white/10 bg-slate-950/42 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]">
                    <div className="mb-3 text-xs font-semibold uppercase text-slate-400">{phaseName}</div>
                    <div className="space-y-3">
                      {timeline.filter((item) => item.phase === phaseName).map((item) => {
                        const state = stepState(item, completed ? 100 : progress, currentStep, completed, hasError);
                        return (
                          <div key={item.key} className="flex items-center gap-3 text-sm">
                            <StepIcon state={state} />
                            <span className={state === "pending" ? "text-slate-400" : "text-slate-100"}>{item.label}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="glass-card p-4">
                <div className="text-xs font-semibold uppercase text-slate-400">Phase A inputs</div>
                <div className="mt-3 space-y-2 text-sm text-slate-200">
                  {["Front image", "Back image", "Centering data"].map((item) => (
                    <div key={item} className="flex items-center gap-2"><CheckCircle2 size={16} className="text-emerald-300" />{item}</div>
                  ))}
                </div>
              </div>
              <div className="glass-card p-4">
                <div className="text-xs font-semibold uppercase text-slate-400">Phase B inputs</div>
                <div className="mt-3 space-y-2 text-sm text-slate-200">
                  {["Emboss", "High Pass", "Sobel", "Working Notes"].map((item) => (
                    <div key={item} className="flex items-center gap-2"><CheckCircle2 size={16} className="text-emerald-300" />{item}</div>
                  ))}
                </div>
              </div>
            </div>

            {completed && (
              <div className="rounded-3xl border border-emerald-300/20 bg-emerald-300/10 p-4">
                <div className="text-sm font-semibold text-emerald-50">Recommendation</div>
                <p className="mt-2 text-sm leading-6 text-emerald-100">{result?.recommended_action || "Review the report cards below for detailed grading notes."}</p>
              </div>
            )}

            {hasError && (
              <div className="rounded-3xl border border-rose-300/25 bg-rose-400/10 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-rose-50">AI grading stopped</div>
                    <p className="mt-1 text-sm leading-6 text-rose-100">{error || pipeline?.error_message || "The grading workflow did not complete."}</p>
                  </div>
                  <button className="min-h-10 rounded-xl bg-rose-400 px-4 text-sm font-semibold text-slate-950 hover:bg-rose-300" onClick={onRetry} type="button">
                    Retry
                  </button>
                </div>
                {debugMode && pipeline?.error_message && <pre className="mt-3 max-h-32 overflow-auto rounded-xl bg-slate-950/70 p-3 text-xs text-rose-100">{pipeline.error_message}</pre>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
