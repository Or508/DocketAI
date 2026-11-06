"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

export function OfficeBar() {
  const [organization, setOrganization] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/office/auth/me", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as { organization_name: string };
      })
      .then((user) => {
        if (!cancelled && user) setOrganization(user.organization_name);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      {organization ? <p className="text-mist">{organization}</p> : null}
      <Button type="button" variant="outline" onClick={() => void signOut()}>
        Sign out
      </Button>
    </div>
  );
}
