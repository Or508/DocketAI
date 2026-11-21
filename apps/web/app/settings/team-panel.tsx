"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api, type InviteResult, type Member, type MemberRole, type MemberStatus } from "@/lib/api";

const ROLE: Record<MemberRole, string> = { owner: "מנהל/ת", staff: "צוות" };
const STATUS: Record<MemberStatus, string> = {
  active: "פעיל",
  invited: "ממתין להצטרפות",
  invite_expired: "פג תוקף ההזמנה",
  inactive: "כבוי",
};

function problem(error: unknown): string {
  if (error instanceof ApiError && error.message && error.message !== "Request failed") return error.message;
  if (error instanceof ApiError) return error.message || "Request failed";
  return "לא ניתן להגיע לשירות המשרד.";
}

function InviteOutcomeView({ result }: { result: InviteResult }) {
  const [copied, setCopied] = useState(false);
  if (result.email_sent) {
    return (
      <p className="mt-3 text-sm font-semibold text-[#0d4a2e]" role="status">
        ההזמנה נשלחה ל-{result.member.email}.
      </p>
    );
  }
  const whatsapp = `https://wa.me/?text=${encodeURIComponent(result.invite_url)}`;
  return (
    <div className="mt-3">
      {result.email_error ? (
        <p className="text-sm font-medium text-clay" role="alert">
          {result.email_error}
        </p>
      ) : null}
      <p className="mt-2 break-all text-sm" dir="ltr">
        {result.invite_url}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            void navigator.clipboard.writeText(result.invite_url).then(
              () => setCopied(true),
              () => setCopied(false),
            );
          }}
        >
          העתקת הקישור
        </Button>
        <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-tide underline-offset-2 hover:underline">
          שליחה בוואטסאפ
        </a>
        {copied ? <span className="text-sm text-mist">הקישור הועתק.</span> : null}
      </div>
    </div>
  );
}

export function TeamPanel() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [owner, setOwner] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<MemberRole>("staff");
  const [sending, setSending] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteNotice, setInviteNotice] = useState<InviteResult | null>(null);
  const [rowNotice, setRowNotice] = useState<{ id: string; result: InviteResult } | null>(null);
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const acting = useRef(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.me(), api.team()])
      .then(([me, list]) => {
        if (cancelled) return;
        setOwner(me.role === "owner");
        setMembers(list);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setLoadError(problem(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function reload() {
    setMembers(await api.team());
  }

  async function invite(event: FormEvent) {
    event.preventDefault();
    if (acting.current) return;
    acting.current = true;
    setSending(true);
    setInviteError(null);
    setInviteNotice(null);
    try {
      const result = await api.inviteMember({ email: email.trim(), display_name: name.trim(), role });
      setInviteNotice(result);
      setEmail("");
      setName("");
      setRole("staff");
      await reload();
    } catch (reason) {
      setInviteError(problem(reason));
    } finally {
      acting.current = false;
      setSending(false);
    }
  }

  async function resend(member: Member) {
    if (acting.current) return;
    acting.current = true;
    setBusyId(member.id);
    setRowError(null);
    setRowNotice(null);
    try {
      const result = await api.resendInvite(member.id);
      setRowNotice({ id: member.id, result });
      await reload();
    } catch (reason) {
      setRowError({ id: member.id, message: problem(reason) });
    } finally {
      acting.current = false;
      setBusyId(null);
    }
  }

  async function changeRole(member: Member, next: MemberRole) {
    if (next === member.role || acting.current) return;
    acting.current = true;
    setBusyId(member.id);
    setRowError(null);
    try {
      await api.updateMember(member.id, { role: next });
      if (member.is_you) setOwner((await api.me()).role === "owner");
      await reload();
    } catch (reason) {
      setRowError({ id: member.id, message: problem(reason) });
    } finally {
      acting.current = false;
      setBusyId(null);
    }
  }

  async function setActive(member: Member, active: boolean) {
    if (acting.current) return;
    acting.current = true;
    if (!active) {
      const confirmed = window.confirm(
        `לכבות את החשבון של ${member.display_name}? החשבון ינותק מיד, ואי אפשר יהיה להתחבר אליו עד שתפעילו אותו מחדש.`,
      );
      if (!confirmed) {
        acting.current = false;
        return;
      }
    }
    setBusyId(member.id);
    setRowError(null);
    try {
      await api.updateMember(member.id, { is_active: active });
      if (member.is_you) setOwner((await api.me()).role === "owner");
      await reload();
    } catch (reason) {
      setRowError({ id: member.id, message: problem(reason) });
    } finally {
      acting.current = false;
      setBusyId(null);
    }
  }

  return (
    <section className="mt-8 rounded-lg border border-ink/15 bg-white p-5">
      <h2 className="font-serif text-2xl">צוות המשרד</h2>
      {owner ? null : members ? <p className="mt-2 text-sm font-medium">רק מנהל המשרד יכול להוסיף עובדים או לשנות הרשאות.</p> : null}

      {owner ? (
        <form className="mt-4 grid gap-3" onSubmit={(event) => void invite(event)}>
          <label className="block text-sm font-semibold" htmlFor="team-email">
            דוא״ל
            <Input
              id="team-email"
              type="email"
              className="mt-2"
              dir="ltr"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="off"
            />
          </label>
          <label className="block text-sm font-semibold" htmlFor="team-name">
            שם
            <Input id="team-name" className="mt-2" value={name} onChange={(event) => setName(event.target.value)} required autoComplete="off" />
          </label>
          <label className="block text-sm font-semibold" htmlFor="team-role">
            תפקיד
            <select
              id="team-role"
              className="mt-2 h-11 w-full rounded-md border border-line bg-white px-3 text-base text-ink"
              value={role}
              onChange={(event) => setRole(event.target.value === "owner" ? "owner" : "staff")}
            >
              <option value="staff">צוות</option>
              <option value="owner">מנהל/ת</option>
            </select>
          </label>
          <div>
            <Button type="submit" disabled={sending}>
              הזמנה
            </Button>
          </div>
          {inviteError ? (
            <p className="text-sm font-medium text-clay" role="alert">
              {inviteError}
            </p>
          ) : null}
          {inviteNotice ? <InviteOutcomeView result={inviteNotice} /> : null}
        </form>
      ) : null}

      {loadError ? (
        <p className="mt-4 text-sm font-medium text-clay" role="alert">
          {loadError}
        </p>
      ) : null}
      {members ? (
        <ul className="mt-5 grid gap-3">
          {members.map((member) => (
            <li key={member.id} className="rounded-md border border-line p-4">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-semibold">{member.display_name}</span>
                {member.is_you ? <span className="text-sm text-mist">את/ה</span> : null}
                <span className="text-sm text-mist" dir="ltr">
                  {member.email}
                </span>
              </div>
              <p className="mt-1 text-sm">
                {ROLE[member.role]} · {STATUS[member.status]}
                {member.mfa_enabled ? " · אימות דו-שלבי" : ""}
              </p>
              {owner ? (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {member.status === "invited" || member.status === "invite_expired" ? (
                    <Button type="button" variant="outline" size="sm" disabled={busyId === member.id} onClick={() => void resend(member)}>
                      שליחת ההזמנה שוב
                    </Button>
                  ) : null}
                  <label className="text-sm font-semibold" htmlFor={`role-${member.id}`}>
                    תפקיד
                    <select
                      id={`role-${member.id}`}
                      className="ms-2 h-8 rounded-md border border-line bg-white px-2 text-sm"
                      value={member.role}
                      disabled={busyId === member.id}
                      onChange={(event) => void changeRole(member, event.target.value === "owner" ? "owner" : "staff")}
                    >
                      <option value="staff">צוות</option>
                      <option value="owner">מנהל/ת</option>
                    </select>
                  </label>
                  {member.status === "inactive" ? (
                    <Button type="button" variant="outline" size="sm" disabled={busyId === member.id} onClick={() => void setActive(member, true)}>
                      הפעלה מחדש
                    </Button>
                  ) : member.is_you ? null : (
                    <Button type="button" variant="danger" size="sm" disabled={busyId === member.id} onClick={() => void setActive(member, false)}>
                      כיבוי חשבון
                    </Button>
                  )}
                </div>
              ) : null}
              {rowError?.id === member.id ? (
                <p className="mt-2 text-sm font-medium text-clay" role="alert">
                  {rowError.message}
                </p>
              ) : null}
              {rowNotice?.id === member.id ? <InviteOutcomeView result={rowNotice.result} /> : null}
            </li>
          ))}
        </ul>
      ) : loadError ? null : (
        <p className="mt-4 text-sm text-mist">טוענים את צוות המשרד…</p>
      )}
    </section>
  );
}
