import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import TaskList from "@tiptap/extension-task-list";
import TaskItem from "@tiptap/extension-task-item";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import { useEffect, useState, useRef, useCallback } from "react";
import { Collapsible, PageLink, FileChip, Embed } from "./editor/nodes";

export interface InlineUpload {
  url: string;
  name: string;
  kind: string;
}

const absUrl = (url: string) =>
  url.startsWith("http") ? url : `${import.meta.env.VITE_API_URL ?? ""}${url}`;

export default function NotionEditor({
  initialContent,
  onChange,
  fullPage = false,
  onInlineUpload,
  enableSubPages = false,
  onCreateSubPage,
  onOpenPage,
}: {
  initialContent: string;
  onChange: (html: string) => void;
  fullPage?: boolean;
  /** Upload a pasted/selected asset and return a servable URL. */
  onInlineUpload?: (file: File) => Promise<InlineUpload>;
  /** Enable the "Alt sayfa" command (only meaningful inside Notlar). */
  enableSubPages?: boolean;
  /** Create a child page; returns its id+title to embed as a page-link. */
  onCreateSubPage?: () => Promise<{ id: string; title: string }>;
  /** Navigate into a child page when its chip is clicked. */
  onOpenPage?: (id: string) => void;
}) {
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashQuery, setSlashQuery] = useState("");
  const [slashCoords, setSlashCoords] = useState({ top: 0, left: 0 });
  const [selected, setSelected] = useState(0);
  const editorRef = useRef<HTMLDivElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder: "Bir şeyler yazın veya komutlar için '/' tuşuna basın…",
      }),
      TaskList,
      TaskItem.configure({ nested: true }),
      Image,
      Link.configure({ openOnClick: false, autolink: true }),
      Collapsible,
      FileChip,
      Embed,
      PageLink.configure({ onOpenPage }),
    ],
    content: initialContent,
    editorProps: {
      attributes: {
        class: `prose prose-invert max-w-none focus:outline-none ${
          fullPage ? "min-h-[calc(100vh-12rem)]" : "min-h-[200px]"
        }`,
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
      // Detect a "/" slash-query at the caret: line-start or after whitespace,
      // followed by non-space chars (the query).
      const from = editor.state.selection.from;
      const before = editor.state.doc.textBetween(Math.max(0, from - 60), from, "\n", "\n");
      const m = before.match(/(?:^|\s)\/([^\s/]*)$/);
      if (m) {
        setSlashQuery(m[1]);
        setSelected(0);
        const box = editorRef.current?.getBoundingClientRect();
        const caret = editor.view.coordsAtPos(from);
        if (box) {
          setSlashCoords({ top: caret.top - box.top + 26, left: caret.left - box.left });
        }
        setSlashOpen(true);
      } else {
        setSlashOpen(false);
      }
    },
  });

  // Sync content from the parent only when the editor isn't focused, so an
  // external document switch updates the view without ever interrupting typing.
  useEffect(() => {
    if (editor && !editor.isFocused && initialContent !== editor.getHTML()) {
      editor.commands.setContent(initialContent || "", { emitUpdate: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialContent]);

  // Remove the "/query" token that triggered the menu, then run the action.
  const runCommand = useCallback(
    (action: () => void) => {
      if (editor) {
        const from = editor.state.selection.from;
        const tokenLen = slashQuery.length + 1; // query + leading "/"
        const start = Math.max(0, from - tokenLen);
        const slice = editor.state.doc.textBetween(start, from, "\n", "\n");
        if (slice.startsWith("/")) {
          editor.chain().focus().deleteRange({ from: start, to: from }).run();
        }
        action();
        editor.view.focus();
      }
      setSlashOpen(false);
    },
    [editor, slashQuery]
  );

  const promptUrl = (label: string) => {
    const url = window.prompt(label)?.trim();
    return url || null;
  };

  type Cmd = { title: string; icon: string; action: () => void };
  const allCommands: Cmd[] = [
    { title: "Başlık 1", icon: "H1", action: () => editor?.chain().focus().toggleHeading({ level: 1 }).run() },
    { title: "Başlık 2", icon: "H2", action: () => editor?.chain().focus().toggleHeading({ level: 2 }).run() },
    { title: "Başlık 3", icon: "H3", action: () => editor?.chain().focus().toggleHeading({ level: 3 }).run() },
    { title: "Yapılacaklar (To-do)", icon: "☑", action: () => editor?.chain().focus().toggleTaskList().run() },
    { title: "Madde listesi", icon: "•", action: () => editor?.chain().focus().toggleBulletList().run() },
    { title: "Numaralı liste", icon: "1.", action: () => editor?.chain().focus().toggleOrderedList().run() },
    { title: "Toggle", icon: "▸", action: () => editor?.chain().focus().insertContent({ type: "collapsible", attrs: { level: 0, open: true }, content: [{ type: "paragraph" }] }).run() },
    { title: "Toggle başlık", icon: "▸H", action: () => editor?.chain().focus().insertContent({ type: "collapsible", attrs: { level: 1, open: true }, content: [{ type: "paragraph" }] }).run() },
    { title: "Alıntı", icon: "❝", action: () => editor?.chain().focus().toggleBlockquote().run() },
    { title: "Kod bloğu", icon: "💻", action: () => editor?.chain().focus().toggleCodeBlock().run() },
    { title: "Çizgi", icon: "—", action: () => editor?.chain().focus().setHorizontalRule().run() },
    { title: "Uyarı (Callout)", icon: "⚠️", action: () => editor?.chain().focus().insertContent("> **UYARI:** ").run() },
    { title: "Tarih", icon: "📅", action: () => editor?.chain().focus().insertContent(`**${new Date().toLocaleDateString("tr-TR")}** `).run() },
    {
      title: "Görsel",
      icon: "🖼",
      action: () => imageInputRef.current?.click(),
    },
    {
      title: "Dosya",
      icon: "📎",
      action: () => fileInputRef.current?.click(),
    },
    {
      title: "Link",
      icon: "🔗",
      action: () => {
        const url = promptUrl("Bağlantı URL'si:");
        if (!url) return;
        const { empty } = editor!.state.selection;
        if (empty) editor?.chain().focus().insertContent(`<a href="${url}">${url}</a> `).run();
        else editor?.chain().focus().setLink({ href: url }).run();
      },
    },
    {
      title: "Link embed (kart)",
      icon: "🔲",
      action: () => {
        const url = promptUrl("Gömülecek bağlantı URL'si:");
        if (url) editor?.chain().focus().insertContent({ type: "embed", attrs: { url } }).run();
      },
    },
  ];
  if (enableSubPages) {
    allCommands.push({
      title: "Alt sayfa",
      icon: "📄",
      action: async () => {
        if (!onCreateSubPage) return;
        const child = await onCreateSubPage();
        editor?.chain().focus().insertContent({ type: "pageLink", attrs: { pageId: child.id, title: child.title } }).run();
      },
    });
  }

  const filtered = slashQuery
    ? allCommands.filter((c) => c.title.toLowerCase().includes(slashQuery.toLowerCase()))
    : allCommands;

  // Keyboard navigation for the slash menu (capture so ProseMirror doesn't move
  // the caret while choosing a command).
  useEffect(() => {
    if (!slashOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(s + 1, Math.max(0, filtered.length - 1)));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(s - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = filtered[selected];
        if (cmd) runCommand(cmd.action);
      } else if (e.key === "Escape") {
        e.preventDefault();
        setSlashOpen(false);
      }
    };
    document.addEventListener("keydown", onKey, { capture: true });
    return () => document.removeEventListener("keydown", onKey, { capture: true });
  }, [slashOpen, filtered, selected, runCommand]);

  const handleUpload = async (file: File | undefined, asImage: boolean) => {
    if (!file || !onInlineUpload) return;
    try {
      const up = await onInlineUpload(file);
      if (asImage) {
        editor?.chain().focus().setImage({ src: absUrl(up.url), alt: up.name }).run();
      } else {
        editor?.chain().focus().insertContent({ type: "fileChip", attrs: { url: up.url, name: up.name } }).run();
      }
    } catch {
      /* ignore upload failure */
    }
  };

  return (
    <div className="relative h-full w-full bg-surface-2 text-zinc-200" ref={editorRef}>
      <EditorContent editor={editor} className={`cursor-text p-6 ${fullPage ? "h-full min-h-full" : "h-full"}`} />

      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          void handleUpload(e.target.files?.[0], true);
          e.target.value = "";
        }}
      />
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={(e) => {
          void handleUpload(e.target.files?.[0], false);
          e.target.value = "";
        }}
      />

      {slashOpen && filtered.length > 0 && (
        <div
          className="absolute z-50 w-64 rounded-xl border border-line-strong bg-elevated p-2 shadow-2xl"
          style={{ top: slashCoords.top, left: slashCoords.left }}
        >
          <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Bloklar
          </div>
          <div className="flex max-h-72 flex-col gap-0.5 overflow-y-auto">
            {filtered.map((cmd, i) => (
              <button
                key={cmd.title}
                onMouseEnter={() => setSelected(i)}
                onClick={() => runCommand(cmd.action)}
                className={`flex items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm transition-colors ${
                  i === selected ? "bg-white/[0.06] text-white" : "text-zinc-300 hover:bg-white/[0.04]"
                }`}
              >
                <div className="flex h-6 w-6 items-center justify-center rounded border border-line-strong bg-surface-2 text-xs text-zinc-400">
                  {cmd.icon}
                </div>
                {cmd.title}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
