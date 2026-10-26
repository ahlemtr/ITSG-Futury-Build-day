import { Navigate, Route, Routes } from "react-router-dom";
import { TopBar } from "./components/TopBar";
import { TopBarProvider } from "./components/TopBarContext";
import { SideNav } from "./components/SideNav";
import { PlaceholderScreen } from "./screens/PlaceholderScreen";
import { OverviewScreen } from "./screens/OverviewScreen";
import { SubmissionsScreen } from "./screens/SubmissionsScreen";
import { SubmissionResultScreen } from "./screens/SubmissionResultScreen";
import { MyTestsScreen } from "./screens/vendor/MyTestsScreen";
import { TestRunScreen } from "./screens/vendor/TestRunScreen";
import { VendorResultsScreen } from "./screens/vendor/VendorResultsScreen";

export function App() {
  return (
    <TopBarProvider>
      <div className="shell">
        <TopBar />
        <SideNav />
        <main className="main">
          <Routes>
            <Route path="/" element={<OverviewScreen />} />
            <Route path="/spec-changes" element={<PlaceholderScreen screen="specChanges" />} />
            <Route path="/test-catalogue" element={<PlaceholderScreen screen="testCatalogue" />} />
            <Route path="/submissions" element={<SubmissionsScreen />} />
            <Route path="/submissions/:id" element={<SubmissionResultScreen />} />
            <Route path="/advisor-queue" element={<PlaceholderScreen screen="advisorQueue" />} />
            <Route path="/reports" element={<PlaceholderScreen screen="reports" />} />
            <Route path="/vendor" element={<MyTestsScreen />} />
            <Route path="/vendor/runs/:id" element={<TestRunScreen />} />
            <Route path="/vendor/results" element={<VendorResultsScreen />} />
            <Route path="/vendor/results/:id" element={<SubmissionResultScreen />} />
            <Route path="/vendor/reports" element={<PlaceholderScreen screen="vendorReports" />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </TopBarProvider>
  );
}
