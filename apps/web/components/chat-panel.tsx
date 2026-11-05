"use client";

import type { CaseWorkspace } from "@docketai/shared-types";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function ChatPanel({
  workspace,
  busy,
  liveReply,
  onSend,
}: {
  workspace: CaseWorkspace;
  busy: boolean;
  liveReply: string | null;
  onSend: (message: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [workspace.messages.length, liveReply, pending]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message) return;
    setDraft("");
    setPending(message);
    try {
      await onSend(message);
    } finally {
      setPending(null);
    }
  }

  return (
    <aside className="flex h-[32rem] flex-col rounded-lg border border-line bg-[#fbf8f2] shadow-card">
      <div className="border-b border-line px-4 py-4">
        <p className="text-[11px] uppercase tracking-[0.18em] text-tide">Clerk</p>
        <h2 className="font-serif text-2xl">Details for the form</h2>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {workspace.messages.map((message, index) => (
          <p
            key={`${message.created_at}-${index}`}
            className={
              message.role === "assistant"
                ? "text-sm leading-6"
                : "ms-8 rounded-md bg-white px-3 py-2 text-sm leading-6"
            }
          >
            {message.content}
          </p>
        ))}
        {pending ? <p className="ms-8 rounded-md bg-white px-3 py-2 text-sm leading-6">{pending}</p> : null}
        {liveReply !== null ? <p className="text-sm leading-6">{liveReply || "…"}</p> : null}
        <div ref={end} />
      </div>
      {workspace.missing_fields.length > 0 ? (
        <div className="flex flex-wrap gap-2 px-4 pb-3">
          {workspace.missing_fields.map((field) => (
            <span key={field.key} className="rounded-full border border-line bg-white px-2 py-1 text-xs text-mist">
              {field.label}
            </span>
          ))}
        </div>
      ) : (
        <p className="px-4 pb-3 text-xs text-moss">Required details are recorded.</p>
      )}
      <form onSubmit={submit} className="border-t border-line p-3">
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Answer the clerk"
          aria-label="Message the clerk"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <Button className="mt-2 w-full" type="submit" disabled={busy || !draft.trim()}>
          Send
        </Button>
      </form>
    </aside>
  );
}
