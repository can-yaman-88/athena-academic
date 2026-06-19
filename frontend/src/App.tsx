import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import PdfPage from "./pages/PdfPage";
import ManagePage from "./pages/ManagePage";
import WorkoutsPage from "./pages/WorkoutsPage";
import IdeasPage from "./pages/IdeasPage";
import { SyncProvider } from "./SyncContext";
import { ChatProvider } from "./ChatContext";

export default function App() {
  return (
    <BrowserRouter>
      <SyncProvider>
        <ChatProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="pdf" element={<PdfPage />} />
            <Route path="manage" element={<ManagePage />} />
            <Route path="workouts" element={<WorkoutsPage />} />
            <Route path="ideas" element={<IdeasPage />} />
          </Route>
        </Routes>
        </ChatProvider>
      </SyncProvider>
    </BrowserRouter>
  );
}
