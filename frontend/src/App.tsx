import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ChatPage from "./pages/ChatPage";
import PdfPage from "./pages/PdfPage";
import AcademicTasksPage from "./pages/AcademicTasksPage";
import NotesPage from "./pages/NotesPage";
import NoteEditorPage from "./pages/NoteEditorPage";
import DayPage from "./pages/DayPage";
import IdeasPage from "./pages/IdeasPage";
import { ChatProvider } from "./ChatContext";
import { ThemeProvider } from "./ThemeContext";

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <ChatProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<ChatPage />} />
              <Route path="akademik" element={<AcademicTasksPage />} />
              <Route path="notlar" element={<NotesPage />} />
              <Route path="notlar/:id" element={<NoteEditorPage />} />
              <Route path="gunum" element={<DayPage />} />
              <Route path="ideas" element={<IdeasPage />} />
              <Route path="pdf" element={<PdfPage />} />
            </Route>
          </Routes>
        </ChatProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
