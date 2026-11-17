"use client";

import { useEffect, useState } from "react";

import { DEFAULT_OFFICE_SETTINGS, readOfficeSettings, subscribeOfficeSettings, type OfficeSettings } from "@/lib/office-settings";

export function useOfficeSettings(): OfficeSettings {
  const [settings, setSettings] = useState<OfficeSettings>(DEFAULT_OFFICE_SETTINGS);
  useEffect(() => {
    const apply = () => setSettings(readOfficeSettings());
    apply();
    return subscribeOfficeSettings(apply);
  }, []);
  return settings;
}
