import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
// PrismAsync code-splits language grammars (fetched on demand), keeping the
// main bundle small. Importing it from the package root also loads the package
// type declarations, so the deep style import below resolves cleanly.
import { PrismAsync as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { ComponentPropsWithoutRef } from "react";

/**
 * Render assistant replies as markdown (headings, lists, tables, links) with
 * syntax-highlighted fenced code blocks. Inline code stays a simple <code>.
 * Styled for the dark theme; colors track the active theme via prose-invert.
 */
export default function AgentMarkdown({ text }: { text: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none break-words font-chat prose-pre:my-2 prose-pre:bg-transparent prose-pre:p-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
          code({ className, children, ...rest }: ComponentPropsWithoutRef<"code">) {
            const match = /language-(\w+)/.exec(className || "");
            const value = String(children ?? "").replace(/\n$/, "");
            // Fenced block with a language → highlight. Everything else (inline
            // code, or fences without a language) renders as plain <code>.
            if (match) {
              return (
                <SyntaxHighlighter
                  language={match[1]}
                  style={oneDark}
                  PreTag="div"
                  customStyle={{
                    margin: 0,
                    borderRadius: "0.5rem",
                    border: "1px solid var(--line)",
                    background: "rgb(var(--surface-2))",
                    fontSize: "0.8125rem",
                  }}
                >
                  {value}
                </SyntaxHighlighter>
              );
            }
            return (
              <code className={className} {...rest}>
                {children}
              </code>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
