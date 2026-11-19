/**
 * App.tsx — Outlaw AI Records — Producer Chat Dashboard
 *
 * Layout: left sidebar (upload + campaign list) | right panel (chat UI)
 * Flow:   upload .mp3 → chat/start → chat/message → proposals → resume → done
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AudioAnalysis {
  bpm?: number;
  key?: string;
  hook_start?: number;
  hook_end?: number;
  spectral_centroid_mean?: number;
  rms_energy_mean?: number;
}

interface Proposal {
  platform: string;
  copy: string;
  hashtags: string[];
  hook_reference?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface CampaignSummary {
  campaign_id: string;
  original_filename: string | null;
  workflow_status: string;
  thread_id: string | null;
  created_at: string;
}

interface Session {
  threadId: string;
  campaignId: string;
  messages: Message[];
  waitingForInput: boolean;
  waitingForApproval: boolean;
  audioAnalysis?: AudioAnalysis;
  audioAnalysisSummary?: string;
  musicBrief?: string;
  lore?: string;
  proposals?: Proposal[];
  productionAssets?: Record<string, unknown>;
  taskType?: string;
  goal?: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const BASE = "";

async function apiUpload(file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await axios.post(`${BASE}/upload`, form);
  return data as { campaign_id: string; original_filename: string };
}

async function apiCampaigns() {
  const { data } = await axios.get(`${BASE}/campaigns`);
  return data as CampaignSummary[];
}

async function apiStartChat(campaign_id: string) {
  const { data } = await axios.post(`${BASE}/chat/start`, { campaign_id });
  return data as {
    thread_id: string;
    campaign_id: string;
    assistant_message: string;
    waiting_for_input: boolean;
  };
}

async function apiSendMessage(thread_id: string, message: string) {
  const { data } = await axios.post(`${BASE}/chat/message`, {
    thread_id,
    message,
  });
  return data as {
    waiting_for_input: boolean;
    waiting_for_approval: boolean;
    clarification_needed: string;
    assistant_message: string;
    task_type?: string;
    goal?: string;
    social_media_proposals?: Proposal[];
    error?: string;
  };
}

async function apiGetState(thread_id: string) {
  const { data } = await axios.get(`${BASE}/state/${thread_id}`);
  return data as {
    messages?: Message[];
    audio_analysis?: AudioAnalysis;
    audio_analysis_summary?: string;
    music_brief?: string;
    lore?: string;
    social_media_proposals?: Proposal[];
    production_assets?: Record<string, unknown>;
    task_type?: string;
    goal?: string;
    waiting_for_input: boolean;
    waiting_for_approval: boolean;
    error?: string;
  };
}

async function apiResume(thread_id: string, idx: number, notes: string) {
  const { data } = await axios.post(`${BASE}/resume`, {
    thread_id,
    selected_proposal_index: idx,
    reviewer_notes: notes,
  });
  return data as {
    production_assets?: Record<string, unknown>;
    status: string;
  };
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function fmtSec(s?: number): string {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function apiErrMsg(err: unknown): string {
  return axios.isAxiosError(err)
    ? (err.response?.data?.detail ?? err.message)
    : String(err);
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    created: "badge-pending",
    chat: "badge-pending",
    analyzing: "badge-running",
    brainstorming: "badge-running",
    awaiting_approval: "badge-waiting",
    producing: "badge-running",
    done: "badge-done",
    error: "badge-error",
  };
  return (
    <span className={map[status] ?? "badge-pending"}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Tiny components
// ---------------------------------------------------------------------------

function Spinner({ size = "md" }: { size?: "sm" | "md" }) {
  const sz = size === "sm" ? "w-4 h-4 border-2" : "w-8 h-8 border-4";
  return (
    <div
      className={`${sz} border-haystack/40 border-t-haystack rounded-full animate-spin`}
    />
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 mb-4">
      <span className="text-2xl">🤠</span>
      <div className="bg-dusk-light border border-saddle/30 rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1.5 items-center">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-2 h-2 bg-haystack/60 rounded-full animate-bounce"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MessageBubble
// ---------------------------------------------------------------------------

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div
      className={`flex items-end gap-2 mb-4 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <span className="text-2xl flex-shrink-0">{isUser ? "🎸" : "🤠"}</span>
      <div
        className={[
          "max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-saddle/40 border border-saddle/50 text-parchment rounded-br-sm"
            : "bg-dusk-light border border-saddle/30 text-parchment/90 rounded-bl-sm font-serif",
        ].join(" ")}
      >
        {msg.content}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AudioCard (collapsible)
// ---------------------------------------------------------------------------

function AudioCard({
  analysis,
  summary,
}: {
  analysis: AudioAnalysis;
  summary?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-pine/20 border border-pine/40 rounded-xl mb-3 overflow-hidden">
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-pine/10 transition-colors"
      >
        <span>🎼</span>
        <span className="text-sm font-semibold text-haystack flex-1">
          Audio Analysis
        </span>
        <span className="text-parchment/40 text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="px-4 pb-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5 text-sm mt-1">
            {[
              ["BPM", analysis.bpm?.toFixed(1)],
              ["Key", analysis.key],
              ["Hook In", fmtSec(analysis.hook_start)],
              ["Hook Out", fmtSec(analysis.hook_end)],
              ["Centroid", analysis.spectral_centroid_mean?.toFixed(0) + " Hz"],
              ["RMS Energy", analysis.rms_energy_mean?.toFixed(4)],
            ].map(([label, value]) => (
              <div key={label}>
                <span className="text-parchment/40">{label}: </span>
                <span className="text-parchment font-medium">
                  {value ?? "—"}
                </span>
              </div>
            ))}
          </div>
          {summary && (
            <p className="mt-3 text-parchment/60 text-xs italic border-t border-pine/30 pt-2">
              {summary}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LoreCard (collapsible)
// ---------------------------------------------------------------------------

function LoreCard({ lore }: { lore: string }) {
  const [open, setOpen] = useState(false);
  const preview = lore.slice(0, 180);
  return (
    <div className="bg-saddle/20 border border-saddle/40 rounded-xl mb-3 overflow-hidden">
      <button
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-saddle/10 transition-colors"
      >
        <span>📖</span>
        <span className="text-sm font-semibold text-haystack flex-1">
          Artist Lore
        </span>
        <span className="text-parchment/40 text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <p className="px-4 pb-4 text-parchment/80 text-sm leading-relaxed font-serif italic">
          {open ? lore : preview + (lore.length > 180 ? "…" : "")}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProposalCards
// ---------------------------------------------------------------------------

const PLATFORM_ICON: Record<string, string> = {
  Instagram: "📸",
  "Twitter/X": "🐦",
  TikTok: "🎵",
  image_prompt: "🎨",
  video_script: "🎬",
};

interface ProposalCardsProps {
  proposals: Proposal[];
  selectedIdx: number;
  onSelect: (i: number) => void;
}

function ProposalCards({
  proposals,
  selectedIdx,
  onSelect,
}: ProposalCardsProps) {
  return (
    <div className="space-y-3 mb-4">
      <p className="text-xs uppercase tracking-wider text-parchment/40 mb-2">
        Choose a proposal
      </p>
      {proposals.map((p, i) => (
        <button
          key={i}
          onClick={() => onSelect(i)}
          className={[
            "w-full text-left rounded-xl border p-4 transition-all duration-150",
            i === selectedIdx
              ? "border-haystack bg-haystack/10 shadow-glow"
              : "border-saddle/30 hover:border-saddle/60 hover:bg-saddle/10",
          ].join(" ")}
        >
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">{PLATFORM_ICON[p.platform] ?? "📝"}</span>
            <span className="font-semibold text-haystack text-sm">
              {p.platform}
            </span>
            {i === selectedIdx && (
              <span className="ml-auto text-xs badge bg-haystack/20 text-haystack border border-haystack/30 px-2 py-0.5 rounded-full">
                ✓ Selected
              </span>
            )}
          </div>
          <p className="text-parchment/80 text-sm leading-relaxed line-clamp-4 whitespace-pre-wrap">
            {p.copy}
          </p>
          {p.hashtags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {p.hashtags.map((h, j) => (
                <span
                  key={j}
                  className="text-xs text-haystack/70 bg-haystack/10 px-1.5 py-0.5 rounded"
                >
                  {h}
                </span>
              ))}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProductionResult
// ---------------------------------------------------------------------------

function ProductionResult({ assets }: { assets: Record<string, unknown> }) {
  const proposal = assets.approved_proposal as Proposal | undefined;
  const notes = assets.reviewer_notes as string | undefined;
  return (
    <div className="bg-pine/20 border border-pine/50 rounded-xl p-5 mb-4">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🏆</span>
        <h3 className="text-haystack font-serif text-lg">
          Production Complete
        </h3>
      </div>
      {proposal && (
        <>
          <p className="text-xs text-parchment/40 mb-1.5 uppercase tracking-wider">
            {PLATFORM_ICON[proposal.platform] ?? "📝"} Approved{" "}
            {proposal.platform} post
          </p>
          <div className="bg-dusk-light rounded-lg p-3 border border-saddle/30 mb-3">
            <p className="text-parchment text-sm leading-relaxed whitespace-pre-wrap">
              {proposal.copy}
            </p>
          </div>
          {proposal.hashtags?.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-3">
              {proposal.hashtags.map((h, i) => (
                <span
                  key={i}
                  className="text-xs text-haystack/80 bg-haystack/10 px-1.5 py-0.5 rounded"
                >
                  {h}
                </span>
              ))}
            </div>
          )}
        </>
      )}
      {notes && (
        <p className="text-parchment/50 text-xs italic border-t border-pine/30 pt-2">
          Notes: {notes}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatPanel
// ---------------------------------------------------------------------------

interface ChatPanelProps {
  campaign: CampaignSummary | null;
  session: Session | null;
  sending: boolean;
  onStartSession: (campaignId: string) => Promise<void>;
  onSend: (msg: string) => Promise<void>;
  onApprove: (idx: number, notes: string) => Promise<void>;
  resuming: boolean;
}

function ChatPanel({
  campaign,
  session,
  sending,
  onStartSession,
  onSend,
  onApprove,
  resuming,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [notes, setNotes] = useState("");
  const [localErr, setLocalErr] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to newest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, sending]);

  // Focus input when it becomes active
  useEffect(() => {
    if (session?.waitingForInput && !sending) {
      inputRef.current?.focus();
    }
  }, [session?.waitingForInput, sending]);

  // Reset proposal selection when proposals change
  useEffect(() => {
    setSelectedIdx(0);
  }, [session?.proposals?.length]);

  // ---- Empty states ---------------------------------------------------------

  if (!campaign) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-parchment/30">
        <span className="text-6xl mb-4">🎸</span>
        <p className="text-sm">Upload a track or select a campaign to begin</p>
      </div>
    );
  }

  if (!session && campaign.workflow_status === "created") {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <span className="text-5xl">🤠</span>
        <p className="text-parchment/60 text-sm text-center max-w-sm">
          <strong className="text-parchment">
            {campaign.original_filename ?? "This track"}
          </strong>{" "}
          is uploaded and ready. Start a chat session to describe your campaign
          goals.
        </p>
        <button
          className="btn-primary"
          disabled={sending}
          onClick={async () => {
            setLocalErr(null);
            try {
              await onStartSession(campaign.campaign_id);
            } catch (e) {
              setLocalErr(apiErrMsg(e));
            }
          }}
        >
          {sending ? (
            <span className="flex items-center gap-2">
              <Spinner size="sm" /> Starting…
            </span>
          ) : (
            "🚀 Start Chat Session"
          )}
        </button>
        {localErr && <p className="text-red-400 text-sm">{localErr}</p>}
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner />
      </div>
    );
  }

  // ---- Active session -------------------------------------------------------

  const isDone = !!session.productionAssets;
  const canSend = session.waitingForInput && !sending && !isDone;

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || !canSend) return;
    setInput("");
    setLocalErr(null);
    try {
      await onSend(msg);
    } catch (e) {
      setLocalErr(apiErrMsg(e));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleApprove = async () => {
    setLocalErr(null);
    try {
      await onApprove(selectedIdx, notes);
    } catch (e) {
      setLocalErr(apiErrMsg(e));
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-saddle/20 flex-shrink-0">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-parchment truncate text-sm">
            {campaign.original_filename ?? "Untitled Track"}
          </p>
          {session.goal && (
            <p className="text-xs text-parchment/40 truncate">
              Goal: {session.goal}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {session.taskType && session.taskType !== "unknown" && (
            <span className="text-xs bg-haystack/10 text-haystack border border-haystack/20 px-2 py-0.5 rounded-full">
              {session.taskType.replace(/_/g, " ")}
            </span>
          )}
          {statusBadge(campaign.workflow_status)}
        </div>
      </div>

      {/* Messages + context area */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {session.messages.map((m, i) => (
          <MessageBubble key={i} msg={m} />
        ))}

        {sending && <TypingIndicator />}

        {/* Context cards — appear after workflow generates data */}
        {session.audioAnalysis && (
          <AudioCard
            analysis={session.audioAnalysis}
            summary={session.audioAnalysisSummary}
          />
        )}
        {session.lore && <LoreCard lore={session.lore} />}

        {/* Proposals for approval */}
        {session.waitingForApproval &&
          session.proposals &&
          session.proposals.length > 0 && (
            <div className="mt-2">
              <ProposalCards
                proposals={session.proposals}
                selectedIdx={selectedIdx}
                onSelect={setSelectedIdx}
              />
            </div>
          )}

        {/* Production result */}
        {isDone && session.productionAssets && (
          <ProductionResult assets={session.productionAssets} />
        )}

        {/* Error */}
        {(session.error ?? localErr) && (
          <div className="rounded-md bg-ember/20 border border-ember/40 px-3 py-2 text-red-300 text-sm mb-4">
            ⚠️ {session.error ?? localErr}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Bottom bar */}
      {!isDone && (
        <div className="border-t border-saddle/20 px-4 py-3 flex-shrink-0">
          {session.waitingForApproval ? (
            /* Approval bar */
            <div className="space-y-2">
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={1}
                placeholder="Reviewer notes (optional)…"
                className="input-field text-sm resize-none"
              />
              <button
                onClick={handleApprove}
                disabled={resuming}
                className="btn-primary w-full"
              >
                {resuming ? (
                  <span className="flex items-center justify-center gap-2">
                    <Spinner size="sm" />
                    Producing…
                  </span>
                ) : (
                  `✅ Approve proposal ${selectedIdx + 1} & Execute Production`
                )}
              </button>
            </div>
          ) : (
            /* Chat input */
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder={
                  canSend
                    ? "Message the orchestrator… (Enter to send)"
                    : sending
                      ? "Thinking…"
                      : "Waiting for workflow…"
                }
                disabled={!canSend}
                className="input-field text-sm resize-none flex-1 disabled:opacity-40"
              />
              <button
                onClick={handleSend}
                disabled={!canSend || !input.trim()}
                className="btn-primary px-4 py-2.5 flex-shrink-0 disabled:opacity-40"
              >
                ↑
              </button>
            </div>
          )}
        </div>
      )}

      {isDone && (
        <div className="border-t border-saddle/20 px-4 py-3 flex-shrink-0 text-center">
          <p className="text-parchment/40 text-xs">
            Campaign complete · Upload a new track to start a fresh session
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// UploadPanel
// ---------------------------------------------------------------------------

function UploadPanel({ onUploaded }: { onUploaded: (id: string) => void }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      try {
        const r = await apiUpload(file);
        onUploaded(r.campaign_id);
      } catch (e) {
        setError(apiErrMsg(e));
      } finally {
        setUploading(false);
      }
    },
    [onUploaded],
  );

  return (
    <div className="card">
      <h2 className="flex items-center gap-2 text-lg font-serif text-haystack mb-4">
        <span>🎵</span> Upload Track
      </h2>
      <div
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files[0];
          if (f) handleFile(f);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onClick={() => inputRef.current?.click()}
        className={[
          "flex flex-col items-center justify-center border-2 border-dashed rounded-xl py-10 px-4 cursor-pointer transition-all duration-200",
          dragging
            ? "border-haystack bg-haystack/10 shadow-glow"
            : "border-saddle/50 hover:border-haystack/60 hover:bg-saddle/10",
        ].join(" ")}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".mp3,.wav,.flac,.ogg,.m4a"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
        {uploading ? (
          <Spinner />
        ) : (
          <>
            <span className="text-4xl mb-2">🎸</span>
            <p className="text-parchment/70 text-center text-sm">
              Drop your <strong className="text-haystack">.mp3</strong> or click
              to browse
            </p>
            <p className="text-parchment/30 text-xs mt-1">
              mp3 · wav · flac · ogg · m4a
            </p>
          </>
        )}
      </div>
      {error && (
        <p className="mt-2 text-red-400 text-xs bg-ember/20 rounded px-2 py-1.5">
          ⚠️ {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CampaignList
// ---------------------------------------------------------------------------

interface CampaignListProps {
  campaigns: CampaignSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  onRefresh: () => void;
}

function CampaignList({
  campaigns,
  selectedId,
  onSelect,
  loading,
  onRefresh,
}: CampaignListProps) {
  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-serif text-haystack">
          <span>📋</span> Campaigns
        </h2>
        <button
          onClick={onRefresh}
          className="text-parchment/40 hover:text-haystack text-lg transition-colors"
          title="Refresh"
        >
          ↻
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-6">
          <Spinner />
        </div>
      ) : campaigns.length === 0 ? (
        <p className="text-parchment/30 text-sm text-center py-6">
          No campaigns yet.
        </p>
      ) : (
        <ul className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {campaigns.map((c) => (
            <li key={c.campaign_id}>
              <button
                onClick={() => onSelect(c.campaign_id)}
                className={[
                  "w-full text-left rounded-lg px-3 py-2.5 transition-all border",
                  selectedId === c.campaign_id
                    ? "border-haystack bg-haystack/10 shadow-glow-sm"
                    : "border-saddle/30 hover:border-saddle/60 hover:bg-saddle/10",
                ].join(" ")}
              >
                <p className="truncate text-sm font-medium text-parchment">
                  {c.original_filename ?? "Untitled Track"}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  {statusBadge(c.workflow_status)}
                  <span className="text-parchment/30 text-xs">
                    {new Date(c.created_at).toLocaleDateString()}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// App (root)
// ---------------------------------------------------------------------------

export default function App() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [sending, setSending] = useState(false);
  const [resuming, setResuming] = useState(false);

  const selectedCampaign =
    campaigns.find((c) => c.campaign_id === selectedId) ?? null;

  // ---- Data loading ---------------------------------------------------------

  const loadCampaigns = useCallback(async () => {
    setCampaignsLoading(true);
    try {
      setCampaigns(await apiCampaigns());
    } catch {
      // ignore — backend may be starting up
    } finally {
      setCampaignsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  // ---- Load existing session when a campaign with thread_id is selected -----

  const loadSession = useCallback(async (campaign: CampaignSummary) => {
    if (!campaign.thread_id) return;
    try {
      const s = await apiGetState(campaign.thread_id);
      setSession({
        threadId: campaign.thread_id,
        campaignId: campaign.campaign_id,
        messages: s.messages ?? [],
        waitingForInput: s.waiting_for_input,
        waitingForApproval: s.waiting_for_approval,
        audioAnalysis: s.audio_analysis,
        audioAnalysisSummary: s.audio_analysis_summary,
        musicBrief: s.music_brief,
        lore: s.lore,
        proposals: s.social_media_proposals,
        productionAssets: s.production_assets,
        taskType: s.task_type,
        goal: s.goal,
        error: s.error,
      });
    } catch {
      // thread may no longer exist
    }
  }, []);

  // ---- Session lifecycle ----------------------------------------------------

  const startSession = useCallback(
    async (campaignId: string) => {
      setSending(true);
      try {
        const r = await apiStartChat(campaignId);
        setSession({
          threadId: r.thread_id,
          campaignId,
          messages: r.assistant_message
            ? [{ role: "assistant", content: r.assistant_message }]
            : [],
          waitingForInput: r.waiting_for_input,
          waitingForApproval: false,
        });
        await loadCampaigns();
      } finally {
        setSending(false);
      }
    },
    [loadCampaigns],
  );

  const sendMessage = useCallback(
    async (msg: string) => {
      if (!session) return;

      // Optimistically append the user message
      setSession((s) =>
        s
          ? {
              ...s,
              messages: [...s.messages, { role: "user", content: msg }],
              waitingForInput: false,
            }
          : s,
      );
      setSending(true);

      try {
        const r = await apiSendMessage(session.threadId, msg);

        setSession((s) => {
          if (!s) return s;
          const newMessages: Message[] = r.assistant_message
            ? [
                ...s.messages,
                { role: "assistant", content: r.assistant_message },
              ]
            : s.messages;
          return {
            ...s,
            messages: newMessages,
            waitingForInput: r.waiting_for_input,
            waitingForApproval: r.waiting_for_approval,
            proposals: r.social_media_proposals ?? s.proposals,
            taskType: r.task_type ?? s.taskType,
            goal: r.goal ?? s.goal,
            error: r.error ?? null,
          };
        });

        // If waiting for approval, fetch full state to get audio/lore data
        if (r.waiting_for_approval) {
          try {
            const full = await apiGetState(session.threadId);
            setSession((s) =>
              s
                ? {
                    ...s,
                    audioAnalysis: full.audio_analysis ?? s.audioAnalysis,
                    audioAnalysisSummary:
                      full.audio_analysis_summary ?? s.audioAnalysisSummary,
                    musicBrief: full.music_brief ?? s.musicBrief,
                    lore: full.lore ?? s.lore,
                    proposals: full.social_media_proposals ?? s.proposals,
                  }
                : s,
            );
          } catch {
            /* not critical */
          }
          await loadCampaigns();
        }
      } finally {
        setSending(false);
      }
    },
    [session, loadCampaigns],
  );

  const approveProposal = useCallback(
    async (idx: number, notes: string) => {
      if (!session) return;
      setResuming(true);
      try {
        const r = await apiResume(session.threadId, idx, notes);
        setSession((s) =>
          s
            ? {
                ...s,
                productionAssets: r.production_assets,
                waitingForApproval: false,
              }
            : s,
        );
        await loadCampaigns();
      } finally {
        setResuming(false);
      }
    },
    [session, loadCampaigns],
  );

  // ---- Campaign selection ---------------------------------------------------

  const handleSelectCampaign = useCallback(
    async (id: string) => {
      setSelectedId(id);
      setSession(null);
      const campaign = campaigns.find((c) => c.campaign_id === id);
      if (campaign?.thread_id) {
        await loadSession(campaign);
      }
    },
    [campaigns, loadSession],
  );

  const handleUploaded = useCallback(
    async (campaignId: string) => {
      await loadCampaigns();
      setSelectedId(campaignId);
      setSession(null);
      await startSession(campaignId);
    },
    [loadCampaigns, startSession],
  );

  // ---- Render ---------------------------------------------------------------

  return (
    <div className="h-screen flex flex-col bg-dusk text-parchment overflow-hidden">
      {/* Header */}
      <header className="border-b border-saddle/30 bg-dusk-light/80 backdrop-blur-sm flex-shrink-0 z-10">
        <div className="max-w-screen-xl mx-auto px-6 py-3 flex items-center gap-4">
          <span className="text-3xl">🤠</span>
          <div>
            <h1 className="text-lg font-serif text-haystack leading-tight">
              Outlaw AI Records
            </h1>
            <p className="text-xs text-parchment/40 tracking-wider uppercase">
              Producer Dashboard
            </p>
          </div>
          <div className="ml-auto hidden sm:flex items-center gap-2 text-parchment/30 text-xs">
            <span className="w-2 h-2 rounded-full bg-pine inline-block" />
            System Online
          </div>
        </div>
      </header>

      {/* Main: sidebar + chat */}
      <div className="flex-1 flex overflow-hidden max-w-screen-xl mx-auto w-full">
        {/* Sidebar */}
        <aside className="w-72 xl:w-80 flex-shrink-0 border-r border-saddle/20 overflow-y-auto p-4 space-y-4">
          <UploadPanel onUploaded={handleUploaded} />
          <CampaignList
            campaigns={campaigns}
            selectedId={selectedId}
            onSelect={handleSelectCampaign}
            loading={campaignsLoading}
            onRefresh={loadCampaigns}
          />
        </aside>

        {/* Chat panel */}
        <main className="flex-1 overflow-hidden">
          <ChatPanel
            campaign={selectedCampaign}
            session={session}
            sending={sending}
            onStartSession={startSession}
            onSend={sendMessage}
            onApprove={approveProposal}
            resuming={resuming}
          />
        </main>
      </div>
    </div>
  );
}
