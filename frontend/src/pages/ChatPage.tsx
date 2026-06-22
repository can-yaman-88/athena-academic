import ChatBox from "../components/chat/ChatBox";

/**
 * Full-page chat at `/` (replaces the old "Günüm" dashboard). Renders the
 * decomposed ChatBox (ChatMessage + ChatInput) with streaming, tool-call
 * blocks, a Deep Research progress panel, syntax highlighting and drag-drop.
 */
export default function ChatPage() {
  return (
    <div className="h-full min-h-0">
      <ChatBox />
    </div>
  );
}
