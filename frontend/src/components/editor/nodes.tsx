import { Node, mergeAttributes } from "@tiptap/core";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
  type NodeViewProps,
} from "@tiptap/react";

/* -------------------------------------------------------------------------- */
/* Collapsible — Notion-style "toggle" and "toggle heading"                   */
/* level 0 = plain toggle; 1..3 = toggle heading. Body is real block content. */
/* -------------------------------------------------------------------------- */
function CollapsibleView({ node, updateAttributes }: NodeViewProps) {
  const open = node.attrs.open as boolean;
  const title = node.attrs.title as string;
  const level = node.attrs.level as number;
  return (
    <NodeViewWrapper className="my-1 rounded-md border border-line bg-surface-2/40">
      <div contentEditable={false} className="flex items-center gap-1.5 px-2 py-1">
        <button
          type="button"
          onClick={() => updateAttributes({ open: !open })}
          className="select-none px-1 text-zinc-400 hover:text-zinc-200"
          aria-label={open ? "Daralt" : "Genişlet"}
        >
          {open ? "▾" : "▸"}
        </button>
        <input
          value={title}
          onChange={(e) => updateAttributes({ title: e.target.value })}
          placeholder={level >= 1 ? "Başlık" : "Toggle"}
          className={`flex-1 bg-transparent text-zinc-200 outline-none placeholder:text-zinc-600 ${
            level >= 1 ? "text-lg font-semibold" : "text-sm"
          }`}
        />
      </div>
      <NodeViewContent className={`px-7 pb-2 ${open ? "" : "hidden"}`} />
    </NodeViewWrapper>
  );
}

export const Collapsible = Node.create({
  name: "collapsible",
  group: "block",
  content: "block+",
  defining: true,
  addAttributes() {
    return {
      open: {
        default: true,
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-open") !== "false",
        renderHTML: (a) => ({ "data-open": a.open ? "true" : "false" }),
      },
      title: {
        default: "",
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-title") || "",
        renderHTML: (a) => ({ "data-title": a.title }),
      },
      level: {
        default: 0,
        parseHTML: (el) => Number((el as HTMLElement).getAttribute("data-level") || 0),
        renderHTML: (a) => ({ "data-level": String(a.level) }),
      },
    };
  },
  parseHTML() {
    return [{ tag: "div[data-collapsible]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-collapsible": "" }), 0];
  },
  addNodeView() {
    return ReactNodeViewRenderer(CollapsibleView);
  },
});

/* -------------------------------------------------------------------------- */
/* PageLink — inline chip linking to a child Note page (page-in-page)         */
/* -------------------------------------------------------------------------- */
function PageLinkView({ node, extension }: NodeViewProps) {
  const onOpen = extension.options.onOpenPage as ((id: string) => void) | undefined;
  return (
    <NodeViewWrapper as="span" className="inline">
      <button
        type="button"
        contentEditable={false}
        onClick={() => onOpen?.(node.attrs.pageId)}
        className="mx-0.5 inline-flex items-center gap-1 rounded border border-line-strong bg-surface-2 px-1.5 py-0.5 align-baseline text-sm text-primary-300 hover:border-primary-500"
      >
        📄 {node.attrs.title || "Sayfa"}
      </button>
    </NodeViewWrapper>
  );
}

export const PageLink = Node.create({
  name: "pageLink",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  addOptions() {
    return { onOpenPage: undefined as ((id: string) => void) | undefined };
  },
  addAttributes() {
    return {
      pageId: {
        default: "",
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-page-id") || "",
        renderHTML: (a) => ({ "data-page-id": a.pageId }),
      },
      title: {
        default: "",
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-title") || "",
        renderHTML: (a) => ({ "data-title": a.title }),
      },
    };
  },
  parseHTML() {
    return [{ tag: "a[data-page-id]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return [
      "a",
      mergeAttributes(HTMLAttributes, { "data-page-link": "" }),
      `📄 ${HTMLAttributes["data-title"] || "Sayfa"}`,
    ];
  },
  addNodeView() {
    return ReactNodeViewRenderer(PageLinkView);
  },
});

/* -------------------------------------------------------------------------- */
/* FileChip — block attachment chip with a download link                      */
/* -------------------------------------------------------------------------- */
function FileChipView({ node }: NodeViewProps) {
  const { url, name } = node.attrs as { url: string; name: string };
  const href = url.startsWith("http") ? url : `${import.meta.env.VITE_API_URL ?? ""}${url}`;
  return (
    <NodeViewWrapper className="my-1">
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        contentEditable={false}
        className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-zinc-200 hover:border-primary-500"
      >
        📎 {name || "Dosya"}
      </a>
    </NodeViewWrapper>
  );
}

export const FileChip = Node.create({
  name: "fileChip",
  group: "block",
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      url: {
        default: "",
        parseHTML: (el) => (el as HTMLElement).getAttribute("href") || "",
        renderHTML: (a) => ({ href: a.url }),
      },
      name: {
        default: "",
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-name") || "",
        renderHTML: (a) => ({ "data-name": a.name }),
      },
    };
  },
  parseHTML() {
    return [{ tag: "a[data-file]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return [
      "a",
      mergeAttributes(HTMLAttributes, { "data-file": "", download: "" }),
      `📎 ${HTMLAttributes["data-name"] || "Dosya"}`,
    ];
  },
  addNodeView() {
    return ReactNodeViewRenderer(FileChipView);
  },
});

/* -------------------------------------------------------------------------- */
/* Embed — bookmark-style card for an embedded link                           */
/* -------------------------------------------------------------------------- */
function EmbedView({ node }: NodeViewProps) {
  const url = node.attrs.url as string;
  let host = url;
  try {
    host = new URL(url).hostname;
  } catch {
    /* keep raw */
  }
  return (
    <NodeViewWrapper className="my-1.5">
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        contentEditable={false}
        className="flex items-center gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2 hover:border-primary-500"
      >
        <span className="text-lg">🔗</span>
        <span className="min-w-0">
          <span className="block truncate text-sm text-zinc-200">{url}</span>
          <span className="block text-xs text-zinc-500">{host}</span>
        </span>
      </a>
    </NodeViewWrapper>
  );
}

export const Embed = Node.create({
  name: "embed",
  group: "block",
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      url: {
        default: "",
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-url") || "",
        renderHTML: (a) => ({ "data-url": a.url }),
      },
    };
  },
  parseHTML() {
    return [{ tag: "div[data-embed]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-embed": "" }),
      HTMLAttributes["data-url"] || "",
    ];
  },
  addNodeView() {
    return ReactNodeViewRenderer(EmbedView);
  },
});
