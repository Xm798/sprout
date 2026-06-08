import { Link, Route, Routes } from "react-router-dom";
import { InboxPage } from "./pages/InboxPage";
import { SchedulesPage } from "./pages/SchedulesPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <nav className="flex items-center gap-4 border-b px-4 py-3">
        <span className="font-semibold">Sprout 🌱</span>
        <Link to="/" className="text-sm hover:underline">Inbox</Link>
        <Link to="/schedules" className="text-sm hover:underline">Schedules</Link>
        <Link to="/settings" className="text-sm hover:underline">Settings</Link>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<InboxPage />} />
          <Route path="/schedules" element={<SchedulesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
