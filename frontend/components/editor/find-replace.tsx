"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { type Editor } from "@tiptap/react";
import { Search, X, ChevronDown, ChevronUp, Replace } from "lucide-react";
import { cn } from "@/lib/utils";

interface FindReplaceProps {
  editor: Editor;
  onClose: () => void;
}

export const FindReplace: React.FC<FindReplaceProps> = ({
  editor,
  onClose,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [replaceTerm, setReplaceTerm] = useState("");
  const [matchCount, setMatchCount] = useState(0);
  const [currentMatch, setCurrentMatch] = useState(0);
  const [showReplace, setShowReplace] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  const escapeRegex = useCallback((str: string) =>
    str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), []);

  const clearHighlights = useCallback(() => {
    // Collapse selection to cursor position
    const { from } = editor.state.selection;
    editor.commands.setTextSelection(from);
  }, [editor]);

  const highlightMatches = useCallback((term: string) => {
    // Remove existing search highlights
    clearHighlights();

    if (!term) return;

    // Use ProseMirror search to find and scroll to first match
    const { doc } = editor.state;
    let found = false;

    doc.descendants((node, pos) => {
      if (node.isText && node.text && !found) {
        const index = node.text.toLowerCase().indexOf(term.toLowerCase());
        if (index !== -1) {
          const from = pos + index;
          const to = from + term.length;
          editor.commands.setTextSelection({ from, to });
          found = true;
          return false;
        }
      }
    });
  }, [editor, clearHighlights]);

  useEffect(() => {
    if (!searchTerm) {
      setMatchCount(0);
      setCurrentMatch(0);
      clearHighlights();
      return;
    }

    const text = editor.getText();
    const regex = new RegExp(escapeRegex(searchTerm), "gi");
    const matches = [...text.matchAll(regex)];
    setMatchCount(matches.length);
    setCurrentMatch(matches.length > 0 ? 1 : 0);

    // Highlight matches in editor using decorations
    highlightMatches(searchTerm);
  }, [searchTerm, editor, clearHighlights, escapeRegex, highlightMatches]);

  const findNext = () => {
    if (!searchTerm || matchCount === 0) return;

    const nextMatch = currentMatch < matchCount ? currentMatch + 1 : 1;
    setCurrentMatch(nextMatch);

    // Find nth occurrence
    const { doc } = editor.state;
    const term = searchTerm.toLowerCase();
    let count = 0;

    doc.descendants((node, pos) => {
      if (node.isText && node.text) {
        let searchFrom = 0;
        const text = node.text.toLowerCase();
        while (true) {
          const idx = text.indexOf(term, searchFrom);
          if (idx === -1) break;
          count++;
          if (count === nextMatch) {
            const from = pos + idx;
            const to = from + searchTerm.length;
            editor.commands.setTextSelection({ from, to });
            // Scroll into view
            editor.commands.scrollIntoView();
            return false;
          }
          searchFrom = idx + 1;
        }
      }
    });
  };

  const findPrev = () => {
    if (!searchTerm || matchCount === 0) return;

    const prevMatch = currentMatch > 1 ? currentMatch - 1 : matchCount;
    setCurrentMatch(prevMatch);

    const { doc } = editor.state;
    const term = searchTerm.toLowerCase();
    let count = 0;

    doc.descendants((node, pos) => {
      if (node.isText && node.text) {
        let searchFrom = 0;
        const text = node.text.toLowerCase();
        while (true) {
          const idx = text.indexOf(term, searchFrom);
          if (idx === -1) break;
          count++;
          if (count === prevMatch) {
            const from = pos + idx;
            const to = from + searchTerm.length;
            editor.commands.setTextSelection({ from, to });
            editor.commands.scrollIntoView();
            return false;
          }
          searchFrom = idx + 1;
        }
      }
    });
  };

  const replaceOne = () => {
    if (!searchTerm || matchCount === 0) return;

    const { from, to } = editor.state.selection;
    const selectedText = editor.state.doc.textBetween(from, to);

    if (selectedText.toLowerCase() === searchTerm.toLowerCase()) {
      editor
        .chain()
        .focus()
        .deleteRange({ from, to })
        .insertContent(replaceTerm)
        .run();

      // Recount
      const text = editor.getText();
      const regex = new RegExp(escapeRegex(searchTerm), "gi");
      const matches = [...text.matchAll(regex)];
      setMatchCount(matches.length);

      if (matches.length > 0) {
        findNext();
      } else {
        setCurrentMatch(0);
      }
    } else {
      findNext();
    }
  };

  const replaceAll = () => {
    if (!searchTerm || matchCount === 0) return;

    // Replace all occurrences
    const { doc } = editor.state;
    const term = searchTerm.toLowerCase();
    const replacements: { from: number; to: number }[] = [];

    doc.descendants((node, pos) => {
      if (node.isText && node.text) {
        let searchFrom = 0;
        const text = node.text.toLowerCase();
        while (true) {
          const idx = text.indexOf(term, searchFrom);
          if (idx === -1) break;
          replacements.push({
            from: pos + idx,
            to: pos + idx + searchTerm.length,
          });
          searchFrom = idx + 1;
        }
      }
    });

    // Apply replacements in reverse order to preserve positions
    let chain = editor.chain();
    for (let i = replacements.length - 1; i >= 0; i--) {
      const { from, to } = replacements[i];
      chain = chain.deleteRange({ from, to }).insertContentAt(from, replaceTerm);
    }
    chain.run();

    setMatchCount(0);
    setCurrentMatch(0);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      clearHighlights();
      onClose();
    } else if (e.key === "Enter") {
      if (e.shiftKey) {
        findPrev();
      } else {
        findNext();
      }
    }
  };

  return (
    <div className="flex flex-col gap-1.5 px-3 py-2 bg-background border-b border-border animate-in slide-in-from-top-2 duration-200 shadow-sm">
      {/* Find row */}
      <div className="flex items-center gap-2">
        <Search className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
        <input
          ref={searchRef}
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Find in document…"
          className="flex-1 h-7 bg-muted/50 border border-border rounded px-2 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/60"
        />
        <span className="text-[10px] text-muted-foreground min-w-[44px] text-center font-mono tabular-nums">
          {matchCount > 0 ? `${currentMatch} / ${matchCount}` : "0 / 0"}
        </span>
        <button
          onClick={findPrev}
          disabled={matchCount === 0}
          title="Previous match (Shift+Enter)"
          className="h-6 w-6 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-30 transition-colors"
        >
          <ChevronUp className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={findNext}
          disabled={matchCount === 0}
          title="Next match (Enter)"
          className="h-6 w-6 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-30 transition-colors"
        >
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => setShowReplace(!showReplace)}
          className={cn(
            "h-6 w-6 flex items-center justify-center rounded text-muted-foreground hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors",
            showReplace && "text-primary bg-primary/10 dark:text-primary dark:bg-primary/30"
          )}
          title="Toggle Replace"
        >
          <Replace className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => {
            clearHighlights();
            onClose();
          }}
          title="Close (Esc)"
          className="h-6 w-6 flex items-center justify-center rounded text-muted-foreground hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Replace row */}
      {showReplace && (
        <div className="flex items-center gap-2 animate-in fade-in duration-200">
          <Replace className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
          <input
            type="text"
            value={replaceTerm}
            onChange={(e) => setReplaceTerm(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Replace with…"
            className="flex-1 h-7 bg-muted/50 border border-border rounded px-2 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/60"
          />
          <button
            onClick={replaceOne}
            disabled={matchCount === 0}
            className="h-6 px-2.5 text-[10px] font-medium text-zinc-600 dark:text-muted-foreground hover:text-zinc-900 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded disabled:opacity-30 transition-colors"
          >
            Replace
          </button>
          <button
            onClick={replaceAll}
            disabled={matchCount === 0}
            className="h-6 px-2.5 text-[10px] font-medium text-zinc-600 dark:text-muted-foreground hover:text-zinc-900 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded disabled:opacity-30 transition-colors"
          >
            All
          </button>
        </div>
      )}
    </div>
  );
};
