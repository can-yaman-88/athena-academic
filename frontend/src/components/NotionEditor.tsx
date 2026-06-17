import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useEffect, useState, useRef, useCallback } from "react";

export default function NotionEditor({
  initialContent,
  onChange,
}: {
  initialContent: string;
  onChange: (html: string) => void;
}) {
  const [slashMenuOpen, setSlashMenuOpen] = useState(false);
  const [slashCoords, setSlashCoords] = useState({ top: 0, left: 0 });
  const editorRef = useRef<HTMLDivElement>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder: "Bir şeyler yazın veya komutlar için '/' tuşuna basın...",
      }),
    ],
    content: initialContent,
    editorProps: {
      attributes: {
        class: "prose prose-invert prose-emerald max-w-none focus:outline-none min-h-[200px]",
      },
      handleKeyDown: (view, event) => {
        if (event.key === "/") {
          const { top, left } = view.coordsAtPos(view.state.selection.from);
          const editorBox = editorRef.current?.getBoundingClientRect();
          if (editorBox) {
            setSlashCoords({ top: top - editorBox.top + 30, left: left - editorBox.left });
            setSlashMenuOpen(true);
          }
          return false;
        }
        if (event.key === "Escape") {
          setSlashMenuOpen(false);
        }
        return false;
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
      
      // Close slash menu if the user deletes the slash or types something else
      const textBeforeCursor = editor.state.doc.textBetween(
        Math.max(0, editor.state.selection.from - 10),
        editor.state.selection.from,
        " "
      );
      if (!textBeforeCursor.endsWith("/")) {
        setSlashMenuOpen(false);
      }
    },
  });

  useEffect(() => {
    if (editor && initialContent !== editor.getHTML() && initialContent) {
      // update content if it comes from props, but be careful not to override typing
      // usually only needed on mount or distinct document switches
    }
  }, [initialContent, editor]);

  const insertCommand = useCallback((command: () => void) => {
    if (editor) {
      // Delete the "/"
      editor.commands.deleteRange({
        from: editor.state.selection.from - 1,
        to: editor.state.selection.from,
      });
      command();
      editor.view.focus();
    }
    setSlashMenuOpen(false);
  }, [editor]);

  const commands = [
    {
      title: "Heading 1",
      icon: "H1",
      action: () => editor?.chain().focus().toggleHeading({ level: 1 }).run(),
    },
    {
      title: "Heading 2",
      icon: "H2",
      action: () => editor?.chain().focus().toggleHeading({ level: 2 }).run(),
    },
    {
      title: "Heading 3",
      icon: "H3",
      action: () => editor?.chain().focus().toggleHeading({ level: 3 }).run(),
    },
    {
      title: "Bullet List",
      icon: "•",
      action: () => editor?.chain().focus().toggleBulletList().run(),
    },
    {
      title: "Numbered List",
      icon: "1.",
      action: () => editor?.chain().focus().toggleOrderedList().run(),
    },
    {
      title: "Blockquote (Alıntı)",
      icon: "❝",
      action: () => editor?.chain().focus().toggleBlockquote().run(),
    },
    {
      title: "Code Block (Kod Bloğu)",
      icon: "💻",
      action: () => editor?.chain().focus().toggleCodeBlock().run(),
    },
    {
      title: "Date Mention (Tarih)",
      icon: "📅",
      action: () => {
        const dateStr = new Date().toLocaleDateString("tr-TR");
        editor?.chain().focus().insertContent(`**${dateStr}** `).run();
      },
    },
    {
      title: "Divider (Çizgi)",
      icon: "—",
      action: () => editor?.chain().focus().setHorizontalRule().run(),
    },
    {
      title: "Callout (Uyarı)",
      icon: "⚠️",
      action: () => {
        editor?.chain().focus().insertContent(`> **UYARI:** `).run();
      },
    },
  ];

  return (
    <div className="relative h-full w-full bg-zinc-950 text-zinc-200" ref={editorRef}>
      <EditorContent editor={editor} className="h-full cursor-text p-6" />

      {slashMenuOpen && (
        <div
          className="absolute z-50 w-64 rounded-xl border border-zinc-700 bg-zinc-900 p-2 shadow-2xl"
          style={{ top: slashCoords.top, left: slashCoords.left }}
        >
          <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Temel Bloklar
          </div>
          <div className="flex max-h-60 flex-col gap-1 overflow-y-auto">
            {commands.map((cmd) => (
              <button
                key={cmd.title}
                onClick={() => insertCommand(cmd.action)}
                className="flex items-center gap-3 rounded-lg px-2 py-1.5 text-left text-sm text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-white"
              >
                <div className="flex h-6 w-6 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-xs text-zinc-400">
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
