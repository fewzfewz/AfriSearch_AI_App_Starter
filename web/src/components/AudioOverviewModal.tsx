// NotebookLM-Style Two-Host Audio Overview / Podcast Modal
import {
  Copy, Download, Headphones, MessageSquare, Mic, Pause,
  Play, Radio, RotateCcw, SkipBack, SkipForward, Sparkles,
  Volume2, VolumeX, X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { generatePodcast, type PodcastResult } from "../lib/api";
import { useApi } from "../lib/hooks";
import type { DocumentInfo, Provider } from "../lib/types";
import { FileIcon } from "./answer";
import { Badge, Button, IconButton, Spinner, cx, useToast } from "./ui";

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
}

export function AudioOverviewModal({
  open,
  initialDocIds,
  allDocuments,
  onClose,
}: {
  open: boolean;
  initialDocIds: string[];
  allDocuments: DocumentInfo[];
  onClose: () => void;
}) {
  const toast = useToast();
  const navigate = useNavigate();

  const [selectedIds, setSelectedIds] = useState<string[]>(initialDocIds);
  const [tone, setTone] = useState<"conversational" | "deep_dive" | "critique">("conversational");
  const [length, setLength] = useState<"quick" | "medium" | "deep">("medium");
  const [generating, setGenerating] = useState(false);
  const [podcast, setPodcast] = useState<PodcastResult | null>(null);

  // Audio Playback State
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTurn, setCurrentTurn] = useState(0);
  const [speed, setSpeed] = useState<number>(1.0);
  const [isMuted, setIsMuted] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  const activeTurnRef = useRef<HTMLDivElement>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);
  const utterRef = useRef<SpeechSynthesisUtterance | null>(null);

  const providers = useApi<{ providers: Provider[]; default: string | null }>("/providers");
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);

  // Initialize SpeechSynthesis Voices
  useEffect(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      synthRef.current = window.speechSynthesis;
      const loadVoices = () => {
        const available = window.speechSynthesis.getVoices();
        setVoices(available);
      };
      loadVoices();
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }
  }, []);

  // Cleanup speech when modal closes or unmounts
  useEffect(() => {
    if (!open) {
      stopPlayback();
    }
  }, [open]);

  useEffect(() => {
    if (open) {
      setSelectedIds(initialDocIds.length > 0 ? initialDocIds : (allDocuments[0] ? [allDocuments[0].source_id] : []));
      setPodcast(null);
      setCurrentTurn(0);
      setIsPlaying(false);
    }
  }, [open, initialDocIds]);

  // Scroll active turn into view
  useEffect(() => {
    if (isPlaying && activeTurnRef.current) {
      activeTurnRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [currentTurn, isPlaying]);

  const selectedDocs = allDocuments.filter((d) => selectedIds.includes(d.source_id));
  const availableDocsToAdd = allDocuments.filter((d) => !selectedIds.includes(d.source_id));

  const handleGenerate = async () => {
    if (selectedIds.length === 0) {
      toast("Please select at least one document.", "error");
      return;
    }

    stopPlayback();
    setGenerating(true);
    setCurrentTurn(0);

    try {
      const result = await generatePodcast({
        source_ids: selectedIds,
        tone,
        length,
        provider: selectedProvider,
      });
      setPodcast(result);
      toast("Audio overview generated! Ready to play.");
    } catch (err: any) {
      toast(err.message || "Failed to generate podcast", "error");
    } finally {
      setGenerating(false);
    }
  };

  const stopPlayback = () => {
    if (synthRef.current) {
      synthRef.current.cancel();
    }
    setIsPlaying(false);
  };

  const playTurn = (turnIndex: number) => {
    if (!synthRef.current || !podcast || !podcast.script[turnIndex]) return;

    synthRef.current.cancel();
    const turn = podcast.script[turnIndex];
    setCurrentTurn(turnIndex);

    if (isMuted) {
      setIsPlaying(true);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(turn.text);
    utterRef.current = utterance;
    utterance.rate = speed;

    // Pick voices: Alex (female / higher pitch), Sam (male / lower pitch)
    if (voices.length > 0) {
      const englishVoices = voices.filter((v) => v.lang.startsWith("en"));
      const femaleVoice = englishVoices.find((v) => /female|zira|samantha|karen|victoria|moira/i.test(v.name)) || englishVoices[0];
      const maleVoice = englishVoices.find((v) => /male|david|george|alex|daniel|oliver/i.test(v.name)) || englishVoices[1] || englishVoices[0];

      if (turn.speaker === "Alex") {
        if (femaleVoice) utterance.voice = femaleVoice;
        utterance.pitch = 1.05;
      } else {
        if (maleVoice) utterance.voice = maleVoice;
        utterance.pitch = 0.92;
      }
    } else {
      utterance.pitch = turn.speaker === "Alex" ? 1.1 : 0.9;
    }

    utterance.onend = () => {
      if (turnIndex + 1 < podcast.script.length) {
        playTurn(turnIndex + 1);
      } else {
        setIsPlaying(false);
        setCurrentTurn(0);
        toast("Audio overview complete!");
      }
    };

    utterance.onerror = (e) => {
      if (e.error !== "canceled" && e.error !== "interrupted") {
        setIsPlaying(false);
      }
    };

    synthRef.current.speak(utterance);
    setIsPlaying(true);
  };

  const togglePlayPause = () => {
    if (!podcast) return;
    if (isPlaying) {
      if (synthRef.current?.speaking) {
        synthRef.current.pause();
      }
      setIsPlaying(false);
    } else {
      if (synthRef.current?.paused) {
        synthRef.current.resume();
        setIsPlaying(true);
      } else {
        playTurn(currentTurn);
      }
    }
  };

  const handleNextTurn = () => {
    if (!podcast) return;
    const next = Math.min(podcast.script.length - 1, currentTurn + 1);
    playTurn(next);
  };

  const handlePrevTurn = () => {
    if (!podcast) return;
    const prev = Math.max(0, currentTurn - 1);
    playTurn(prev);
  };

  const handleSpeedChange = () => {
    const speeds = [1.0, 1.25, 1.5, 1.75, 2.0];
    const nextIndex = (speeds.indexOf(speed) + 1) % speeds.length;
    const newSpeed = speeds[nextIndex];
    setSpeed(newSpeed);
    if (isPlaying) {
      playTurn(currentTurn);
    }
  };

  const handleOpenInChat = () => {
    stopPlayback();
    onClose();
    navigate("/app", {
      state: {
        question: `Based on the Audio Overview discussion between Alex and Sam, explain the most important takeaways from ${selectedDocs.map((d) => d.source_name).join(", ")}.`,
        scope: selectedIds,
      },
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-ink-950/60 backdrop-blur-sm animate-fade-in">
      <div className="relative flex flex-col w-full max-w-5xl h-[92vh] max-h-[920px] rounded-2xl bg-white shadow-2xl dark:bg-ink-900 border border-ink-200/80 dark:border-ink-800 overflow-hidden">
        
        {/* Header */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-ink-200/80 px-4 sm:px-6 dark:border-ink-800 bg-ink-50/70 dark:bg-ink-950/40">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-brand-600 text-white shadow-sm">
              <Headphones className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-ink-900 dark:text-ink-50">Audio Overview & Podcast Generator</h2>
                <Badge tone="violet">NotebookLM Style</Badge>
              </div>
              <p className="text-[11px] text-ink-500">Realistic two-host conversational deep-dive audio briefing</p>
            </div>
          </div>
          <IconButton label="Close" onClick={() => { stopPlayback(); onClose(); }}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>

        {/* Modal Body */}
        <div className="flex flex-1 min-h-0 divide-x divide-ink-200/80 dark:divide-ink-800">
          
          {/* Left Column: Configuration & Controls */}
          <div className="w-full md:w-80 lg:w-96 flex flex-col shrink-0 overflow-y-auto p-4 sm:p-5 space-y-5 bg-ink-50/30 dark:bg-ink-950/20">
            
            {/* Document Sources */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-ink-500">
                  Document Sources ({selectedDocs.length})
                </span>
                {selectedDocs.length === 0 && (
                  <span className="text-[11px] text-red-600 font-medium">Select a document</span>
                )}
              </div>
              <div className="space-y-1.5">
                {selectedDocs.map((doc) => (
                  <div
                    key={doc.source_id}
                    className="flex items-center justify-between gap-2 rounded-xl border border-ink-200/80 bg-white p-2 text-xs shadow-soft dark:border-ink-800 dark:bg-ink-900"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileIcon name={doc.source_name} className="h-4 w-4 shrink-0" />
                      <span className="truncate font-medium text-ink-800 dark:text-ink-200" title={doc.source_name}>
                        {doc.source_name}
                      </span>
                    </div>
                    {selectedDocs.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setSelectedIds((all) => all.filter((id) => id !== doc.source_id))}
                        className="text-ink-400 hover:text-ink-600 dark:hover:text-ink-200 p-0.5"
                        title="Remove document"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {availableDocsToAdd.length > 0 && selectedIds.length < 5 && (
                <div className="mt-2">
                  <select
                    className="w-full text-xs rounded-xl border border-dashed border-ink-300 bg-transparent px-2.5 py-1.5 text-ink-600 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-ink-700 dark:text-ink-400"
                    onChange={(e) => {
                      if (e.target.value) {
                        setSelectedIds([...selectedIds, e.target.value]);
                        e.target.value = "";
                      }
                    }}
                    defaultValue=""
                  >
                    <option value="" disabled>+ Add another document to podcast...</option>
                    {availableDocsToAdd.map((d) => (
                      <option key={d.source_id} value={d.source_id}>{d.source_name}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Episode Tone */}
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-500 block mb-2">
                Discussion Tone
              </span>
              <div className="grid grid-cols-1 gap-1.5">
                {[
                  { id: "conversational", label: "🎙️ Conversational & Engaging", desc: "Friendly banter, relatable analogies, upbeat chemistry" },
                  { id: "deep_dive", label: "🔬 Analytical Deep Dive", desc: "Technical breakdown, metrics, and data focus" },
                  { id: "critique", label: "⚖️ Critique & Debate", desc: "Probing assumptions, trade-offs, and critical debate" },
                ].map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTone(t.id as any)}
                    className={cx(
                      "flex flex-col text-left p-2 rounded-xl border transition text-xs",
                      tone === t.id
                        ? "border-brand-500 bg-brand-50/70 text-brand-900 ring-2 ring-brand-500/10 dark:border-brand-600 dark:bg-brand-950/40 dark:text-brand-200"
                        : "border-ink-200/80 bg-white hover:border-ink-300 text-ink-700 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-300"
                    )}
                  >
                    <span className="font-semibold">{t.label}</span>
                    <span className="text-[11px] text-ink-500 dark:text-ink-400 mt-0.5">{t.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Target Duration */}
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-500 block mb-2">
                Episode Length
              </span>
              <div className="grid grid-cols-3 gap-1.5">
                {[
                  { id: "quick", label: "Quick Brief", time: "~2-3 min" },
                  { id: "medium", label: "Standard", time: "~4-5 min" },
                  { id: "deep", label: "Deep Dive", time: "~7-8 min" },
                ].map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => setLength(l.id as any)}
                    className={cx(
                      "flex flex-col items-center justify-center p-2 rounded-xl border text-center transition",
                      length === l.id
                        ? "border-brand-500 bg-brand-50/70 text-brand-900 font-semibold ring-2 ring-brand-500/10 dark:border-brand-600 dark:bg-brand-950/40 dark:text-brand-200"
                        : "border-ink-200/80 bg-white text-ink-700 hover:border-ink-300 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-300"
                    )}
                  >
                    <span className="text-xs">{l.label}</span>
                    <span className="text-[10px] text-ink-400 mt-0.5">{l.time}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* AI Model */}
            {providers.data && providers.data.providers.length > 0 && (
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-ink-500 block mb-1.5">
                  AI Model
                </span>
                <select
                  value={selectedProvider || ""}
                  onChange={(e) => setSelectedProvider(e.target.value || null)}
                  className="w-full text-xs rounded-xl border border-ink-200 bg-white px-2.5 py-2 shadow-soft focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-ink-800 dark:bg-ink-900 text-ink-700 dark:text-ink-200"
                >
                  <option value="">Default AI Model</option>
                  {providers.data.providers.filter((p) => p.available).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label || p.id} ({p.kind === "local" ? "Local CPU" : "Cloud"})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Generate Button */}
            <div className="pt-2">
              <Button
                variant="primary"
                className="w-full shadow-glow"
                onClick={handleGenerate}
                loading={generating}
                disabled={selectedIds.length === 0}
                icon={<Sparkles className="h-4 w-4" />}
              >
                {podcast ? "Regenerate Podcast Episode" : "Generate Audio Overview"}
              </Button>
            </div>
          </div>

          {/* Right Column: Audio Player & Synchronized Transcript */}
          <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-ink-900 overflow-hidden">
            
            {generating && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center py-24">
                <Spinner className="h-8 w-8 text-brand-600" />
                <div>
                  <p className="text-sm font-semibold text-ink-800 dark:text-ink-200">Recording podcast with Alex & Sam...</p>
                  <p className="text-xs text-ink-500 mt-1">Analyzing source evidence and scripting two-host conversation</p>
                </div>
              </div>
            )}

            {!generating && !podcast && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-center p-6 text-ink-400">
                <div className="h-16 w-16 rounded-3xl bg-gradient-to-br from-indigo-50 to-brand-50 dark:from-indigo-950/40 dark:to-brand-950/40 flex items-center justify-center text-brand-600 shadow-soft">
                  <Radio className="h-8 w-8" />
                </div>
                <h3 className="text-base font-semibold text-ink-800 dark:text-ink-200">Turn Your Documents into an Audio Podcast</h3>
                <p className="text-xs max-w-md text-ink-500 leading-relaxed">
                  Two AI co-hosts (Alex and Sam) will break down your documents in a lively, deep-dive conversational audio discussion.
                  Select your tone and click "Generate Audio Overview" to start.
                </p>
              </div>
            )}

            {!generating && podcast && (
              <div className="flex flex-col h-full min-h-0">
                
                {/* Hero Audio Player Header */}
                <div className="shrink-0 border-b border-ink-200/80 p-4 sm:p-5 bg-gradient-to-b from-ink-50/80 to-white dark:from-ink-950/50 dark:to-ink-900">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                    <div className="min-w-0">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400 flex items-center gap-1.5">
                        <Radio className="h-3.5 w-3.5 animate-pulse" />
                        AfriSearch Deep Dive Episode
                      </span>
                      <h3 className="text-base font-bold text-ink-900 dark:text-ink-50 truncate mt-0.5">
                        {podcast.title}
                      </h3>
                      <p className="text-xs text-ink-500 mt-0.5">
                        Est. Duration: {formatDuration(podcast.estimated_seconds)} · {podcast.total_turns} dialogue turns · {podcast.total_words} words
                      </p>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Download className="h-3.5 w-3.5" />}
                        onClick={() => downloadBlob(`${podcast.title}.md`, podcast.full_text, "text/markdown")}
                        title="Download full episode script"
                      >
                        Script (.md)
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Copy className="h-3.5 w-3.5" />}
                        onClick={() => navigator.clipboard.writeText(podcast.full_text).then(() => toast("Script copied"))}
                        title="Copy script"
                      >
                        Copy
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<MessageSquare className="h-3.5 w-3.5 text-brand-600" />}
                        onClick={handleOpenInChat}
                        title="Discuss this episode in Chat"
                      >
                        Discuss in Chat
                      </Button>
                    </div>
                  </div>

                  {/* Player Controls Card */}
                  <div className="flex items-center justify-between gap-3 rounded-2xl border border-ink-200 bg-white/90 p-3 shadow-soft dark:border-ink-800 dark:bg-ink-950/60 backdrop-blur">
                    
                    {/* Speaker Avatar & Name Indicator */}
                    <div className="flex items-center gap-2.5 min-w-[140px]">
                      <div className={cx(
                        "flex h-9 w-9 items-center justify-center rounded-xl text-white font-bold text-xs shadow-sm transition-all",
                        podcast.script[currentTurn]?.speaker === "Alex"
                          ? "bg-gradient-to-br from-blue-500 to-sky-600 ring-2 ring-blue-500/30"
                          : "bg-gradient-to-br from-violet-500 to-indigo-600 ring-2 ring-violet-500/30"
                      )}>
                        {podcast.script[currentTurn]?.speaker === "Alex" ? "AL" : "SA"}
                      </div>
                      <div>
                        <span className="text-xs font-bold text-ink-900 dark:text-ink-100 flex items-center gap-1">
                          {podcast.script[currentTurn]?.speaker || "Alex"}
                          {isPlaying && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />}
                        </span>
                        <span className="text-[10px] text-ink-400">
                          Turn {currentTurn + 1} of {podcast.script.length}
                        </span>
                      </div>
                    </div>

                    {/* Centered Playback Controls */}
                    <div className="flex items-center gap-2">
                      <IconButton
                        label="Previous turn"
                        disabled={currentTurn <= 0}
                        onClick={handlePrevTurn}
                      >
                        <SkipBack className="h-4 w-4" />
                      </IconButton>

                      <button
                        type="button"
                        onClick={togglePlayPause}
                        aria-label={isPlaying ? "Pause audio" : "Play audio"}
                        className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow hover:brightness-110 active:scale-95 transition"
                      >
                        {isPlaying ? <Pause className="h-5 w-5 fill-current" /> : <Play className="h-5 w-5 fill-current ml-0.5" />}
                      </button>

                      <IconButton
                        label="Next turn"
                        disabled={currentTurn >= podcast.script.length - 1}
                        onClick={handleNextTurn}
                      >
                        <SkipForward className="h-4 w-4" />
                      </IconButton>

                      <IconButton
                        label="Replay current turn"
                        onClick={() => playTurn(currentTurn)}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </IconButton>
                    </div>

                    {/* Speed & Volume Controls */}
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleSpeedChange}
                        className="rounded-lg border border-ink-200 bg-ink-50 px-2 py-1 text-xs font-bold text-ink-700 hover:bg-ink-100 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-200"
                        title="Change audio playback speed"
                      >
                        {speed}x
                      </button>
                      <IconButton
                        label={isMuted ? "Unmute audio" : "Mute audio"}
                        onClick={() => setIsMuted((m) => !m)}
                      >
                        {isMuted ? <VolumeX className="h-4 w-4 text-red-500" /> : <Volume2 className="h-4 w-4" />}
                      </IconButton>
                    </div>

                  </div>
                </div>

                {/* Synchronized Script Transcript */}
                <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-3.5 bg-ink-50/20 dark:bg-ink-950/20">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold uppercase tracking-wider text-ink-400">
                      Synchronized Transcript ({podcast.script.length} turns)
                    </span>
                    <span className="text-[11px] text-ink-400 italic">
                      Click any dialogue bubble to jump playback
                    </span>
                  </div>

                  {podcast.script.map((turn, idx) => {
                    const isCurrent = idx === currentTurn;
                    const isAlex = turn.speaker === "Alex";
                    return (
                      <div
                        key={idx}
                        ref={isCurrent ? activeTurnRef : undefined}
                        onClick={() => playTurn(idx)}
                        className={cx(
                          "cursor-pointer rounded-2xl border p-3.5 transition-all text-xs leading-relaxed",
                          isCurrent
                            ? isAlex
                              ? "border-blue-400 bg-blue-50/70 shadow-soft ring-2 ring-blue-400/20 dark:border-blue-700 dark:bg-blue-950/40"
                              : "border-violet-400 bg-violet-50/70 shadow-soft ring-2 ring-violet-400/20 dark:border-violet-700 dark:bg-violet-950/40"
                            : "border-ink-200/80 bg-white hover:border-ink-300 dark:border-ink-800 dark:bg-ink-900/80 dark:hover:border-ink-700"
                        )}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <div className="flex items-center gap-1.5">
                            <span className={cx(
                              "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white",
                              isAlex ? "bg-gradient-to-r from-blue-600 to-sky-600" : "bg-gradient-to-r from-violet-600 to-indigo-600"
                            )}>
                              <Mic className="h-2.5 w-2.5" />
                              {turn.speaker}
                            </span>
                            <span className="text-[11px] font-semibold text-ink-700 dark:text-ink-300">
                              {isAlex ? "Host · Co-Lead" : "Host · Deep Dive Analyst"}
                            </span>
                          </div>
                          {isCurrent && (
                            <span className="text-[10px] font-bold text-brand-600 dark:text-brand-400 flex items-center gap-1">
                              {isPlaying ? "Playing now" : "Paused here"}
                            </span>
                          )}
                        </div>
                        <p className={cx(
                          "text-ink-800 dark:text-ink-100",
                          isCurrent ? "font-medium" : "text-ink-700 dark:text-ink-300"
                        )}>
                          {turn.text}
                        </p>
                      </div>
                    );
                  })}
                </div>

              </div>
            )}

          </div>

        </div>

      </div>
    </div>
  );
}
