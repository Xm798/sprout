import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { HistoryPage } from "@/pages/HistoryPage";
import { InboxPage } from "@/pages/InboxPage";
import { SchedulesPage } from "@/pages/SchedulesPage";
import { SettingsPage } from "@/pages/SettingsPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<InboxPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/schedules" element={<SchedulesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </AppShell>
  );
}
