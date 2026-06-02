"use client";

import { useEffect, useRef, useState } from "react";
import { useTerminal, type ChatTurn } from "@/hooks/useTerminalStore";
import { fmtQty } from "@/lib/format";
import type { ChatTradeAction, ChatWatchlistAction } from "@/types/api";

export function ChatPanel({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { chat, chatBusy, sendChat } = useTerminal();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chat]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.trim() || chatBusy) return;
    sendChat(draft);
    setDraft("");
  };

  if (collapsed) {
    return (
      <button
        type="button"
        data-testid="chat-toggle"
        onClick={onToggle}
        className="flex h-full w-12 flex-col items-center justify-center gap-3 rounded-md border border-hairline bg-panel text-inkMute shadow-panel transition-colors hover:text-amber"
        aria-label="Open AI assistant"
      >
        <span className="h-2 w-2 rounded-full bg-amber animate-pulseDot" />
        <span
          className="font-display text-micro font-700 uppercase tracking-[0.3em]"
          style={{ writingMode: "vertical-rl" }}
        >
          AI Copilot
        </span>
      </button>
    );
  }

  return (
    <section
      data-testid="chat-panel"
      className="flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-hairline bg-panel shadow-panel"
    >
      <header className="flex shrink-0 items-center justify-between border-b border-hairline bg-surface/60 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-amber animate-pulseDot" />
          <span className="panel-label">FinAlly Copilot</span>
        </div>
        <button
          type="button"
          data-testid="chat-collapse"
          onClick={onToggle}
          aria-label="Collapse assistant"
          className="rounded px-1.5 text-inkFaint transition-colors hover:text-ink"
        >
          ›
        </button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3" data-testid="chat-history">
        {chat.length === 0 ? (
          <Welcome />
        ) : (
          chat.map((turn) => <ChatBubble key={turn.id} turn={turn} />)
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="shrink-0 border-t border-hairline bg-surface/60 p-2.5"
      >
        <div className="flex items-end gap-2">
          <textarea
            data-testid="chat-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e);
              }
            }}
            rows={1}
            placeholder="Ask FinAlly to analyze or trade…"
            className="max-h-28 min-h-[38px] flex-1 resize-none rounded border border-hairline bg-base px-3 py-2 text-data text-ink placeholder:text-inkFaint focus:border-purple focus:outline-none"
          />
          <button
            type="submit"
            data-testid="chat-send"
            disabled={chatBusy || !draft.trim()}
            className="rounded border border-purple/50 bg-purple/80 px-4 py-2 text-data font-600 uppercase tracking-wider text-ink transition-colors hover:bg-purple disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </section>
  );
}

function Welcome() {
  return (
    <div className="rounded border border-hairline bg-base/60 p-3 text-data leading-relaxed text-inkMute">
      <p className="mb-2 font-display font-600 text-ink">I&apos;m FinAlly, your copilot.</p>
      <p>Try:</p>
      <ul className="mt-1 space-y-1 text-inkFaint">
        <li>· &ldquo;How is my portfolio doing?&rdquo;</li>
        <li>· &ldquo;Buy 5 shares of AAPL.&rdquo;</li>
        <li>· &ldquo;Add NVDA to my watchlist.&rdquo;</li>
        <li>· &ldquo;Am I too concentrated in tech?&rdquo;</li>
      </ul>
    </div>
  );
}

function ChatBubble({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  return (
    <div
      data-testid={`chat-msg-${turn.role}`}
      data-role={turn.role}
      className={`flex animate-riseIn ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[88%] rounded-lg px-3 py-2 text-data leading-relaxed ${
          isUser
            ? "border border-blue/30 bg-blue/10 text-ink"
            : "border border-hairline bg-base/70 text-ink"
        }`}
      >
        {turn.pending ? (
          <TypingDots />
        ) : (
          <>
            <p className="whitespace-pre-wrap">{turn.content}</p>
            {turn.raw && (
              <pre className="mt-2 overflow-x-auto rounded bg-base p-2 text-micro text-inkMute">
                {turn.raw}
              </pre>
            )}
            <ActionChips actions={turn.actions} />
          </>
        )}
      </div>
    </div>
  );
}

function ActionChips({ actions }: { actions?: ChatTurn["actions"] }) {
  if (!actions) return null;
  const trades = actions.trades ?? [];
  const wl = actions.watchlist_changes ?? [];
  if (trades.length === 0 && wl.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5" data-testid="chat-actions">
      {trades.map((t, i) => (
        <TradeChip key={`t${i}`} t={t} />
      ))}
      {wl.map((w, i) => (
        <WatchChip key={`w${i}`} w={w} />
      ))}
    </div>
  );
}

function chipBase(error?: string) {
  return error
    ? "border-down/40 bg-down/10 text-down"
    : "border-up/40 bg-up/10 text-up";
}

function TradeChip({ t }: { t: ChatTradeAction }) {
  const err = t.status === "error" || t.error;
  return (
    <span
      data-testid="chat-action"
      data-kind="trade"
      data-ticker={t.ticker.toUpperCase()}
      className={`tnum rounded border px-2 py-0.5 text-micro font-600 uppercase tracking-wider ${chipBase(err ? "e" : undefined)}`}
      title={t.error}
    >
      {err ? "✕" : "✓"} {t.side} {fmtQty(t.quantity)} {t.ticker.toUpperCase()}
      {t.error ? ` · ${t.error}` : ""}
    </span>
  );
}

function WatchChip({ w }: { w: ChatWatchlistAction }) {
  const err = w.status === "error" || w.error;
  return (
    <span
      data-testid="chat-action"
      data-kind="watchlist"
      data-ticker={w.ticker.toUpperCase()}
      className={`rounded border px-2 py-0.5 text-micro font-600 uppercase tracking-wider ${chipBase(err ? "e" : undefined)}`}
      title={w.error}
    >
      {err ? "✕" : "✓"} {w.action} {w.ticker.toUpperCase()}
      {w.error ? ` · ${w.error}` : ""}
    </span>
  );
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1 py-1" data-testid="chat-typing" aria-label="Assistant is thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-amber animate-pulseDot"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </span>
  );
}
