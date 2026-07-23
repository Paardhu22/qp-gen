"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import { getTiptapExtensions } from "./tiptap-editor";
import { useEffect, useState } from "react";

type TiptapViewerProps = {
  content: string;
};

export function TiptapViewer({ content }: TiptapViewerProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const editor = useEditor({
    editable: false,
    extensions: getTiptapExtensions(false),
    content: mounted ? (content ? JSON.parse(content).editorJSON || JSON.parse(content) : undefined) : undefined,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: "document-editor focus:outline-none text-black cursor-default",
      },
    },
  });

  useEffect(() => {
    if (editor && content) {
      setTimeout(() => {
        try {
          const parsed = JSON.parse(content);
          editor.commands.setContent(parsed.editorJSON || parsed);
        } catch (e) {
          console.error("Failed to parse or set Tiptap viewer content:", e);
        }
      }, 0);
    }
  }, [editor, content]);

  if (!mounted || !editor) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground animate-pulse">
        Loading document...
      </div>
    );
  }

  return (
    <div className="flex-1 w-full h-full max-w-full overflow-auto overscroll-contain custom-scrollbar bg-transparent print:p-0">
      <EditorContent editor={editor} className="h-full pb-32" />
    </div>
  );
}
