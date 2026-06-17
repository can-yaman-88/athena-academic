import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import PdfPage from "./pages/PdfPage";
import ManagePage from "./pages/ManagePage";
import WorkoutsPage from "./pages/WorkoutsPage";
import IdeasPage from "./pages/IdeasPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="pdf" element={<PdfPage />} />
          <Route path="manage" element={<ManagePage />} />
          <Route path="workouts" element={<WorkoutsPage />} />
          <Route path="ideas" element={<IdeasPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
