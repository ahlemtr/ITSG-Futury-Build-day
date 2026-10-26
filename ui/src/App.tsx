import { Navigate, Route, Routes } from "react-router-dom";
import { TopBar } from "./components/TopBar";
import { SideNav } from "./components/SideNav";
import { PlaceholderScreen } from "./screens/PlaceholderScreen";

export function App() {
  return (
    <div className="shell">
      <TopBar />
      <SideNav />
      <main className="main">
        <Routes>
          <Route path="/" element={<PlaceholderScreen screen="overview" />} />
          <Route path="/spec-changes" element={<PlaceholderScreen screen="specChanges" />} />
          <Route path="/test-catalogue" element={<PlaceholderScreen screen="testCatalogue" />} />
          <Route path="/submissions" element={<PlaceholderScreen screen="submissions" />} />
          <Route path="/advisor-queue" element={<PlaceholderScreen screen="advisorQueue" />} />
          <Route path="/reports" element={<PlaceholderScreen screen="reports" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
