"use client";

/**
 * What the editor says when there is nothing on the page yet.
 *
 * The editor was the app's largest surface and its quietest: a blank A4 sheet
 * beside a toolbar of about a hundred controls, and nothing anywhere
 * indicating a first move. Worse, it is the destination the empty states on
 * the papers and questions pages send teachers to — so the one place the
 * product actively routed a stuck teacher was the place that offered least.
 *
 * ## Not a tour
 *
 * The three actions here are the three real ways a paper starts, and they are
 * the same three the generate dock already offers — the same handlers, so this
 * cannot drift into offering something the dock does not. Nothing is
 * spotlighted, nothing is sequenced, nothing must be dismissed before the
 * editor can be used: a teacher who wants to type simply types, and this
 * disappears the moment the document is not empty.
 *
 * The only first-run-conditional part is the opening line. The actions
 * themselves are permanent, because an empty editor is an empty editor on the
 * five-hundredth visit too and the shortcuts are still the fastest way to
 * fill it.
 */

import { FileText, LayoutTemplate, Sparkles } from "lucide-react";

import { useFirstRun } from "@/lib/use-first-run";

interface Props {
  onGenerate: () => void;
  onBuildFromBank: () => void;
  onUseTemplate: () => void;
}

export function EditorBlankState({
  onGenerate,
  onBuildFromBank,
  onUseTemplate,
}: Props) {
  const { seen } = useFirstRun("editor");

  const actions = [
    {
      icon: Sparkles,
      label: "Generate a paper",
      hint: "Describe it, pick chapters, and let the generator write it.",
      onClick: onGenerate,
      primary: true,
    },
    {
      icon: FileText,
      label: "Build from the question bank",
      hint: "Assemble a paper from questions you have already saved.",
      onClick: onBuildFromBank,
      primary: false,
    },
    {
      icon: LayoutTemplate,
      label: "Start from a template",
      hint: "Reuse a blueprint you or your school has saved.",
      onClick: onUseTemplate,
      primary: false,
    },
  ];

  return (
    // `pointer-events-none` on the wrapper with it restored on the card: the
    // sheet underneath stays clickable, so clicking onto the page and typing
    // is never blocked by guidance sitting on top of it.
    <div className="pointer-events-none absolute inset-0 z-10 flex items-start justify-center overflow-y-auto p-6 print:hidden">
      <div className="pointer-events-auto mt-[12vh] w-full max-w-md rounded-2xl border border-border bg-background/95 p-5 shadow-xl backdrop-blur">
        <p className="text-sm font-semibold text-foreground">
          {seen ? "This paper is empty" : "Start your first paper"}
        </p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          Type straight onto the page, or start from one of these.
        </p>

        <div className="mt-4 space-y-2">
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              onClick={action.onClick}
              className={
                action.primary
                  ? "flex w-full items-start gap-3 rounded-xl bg-primary px-3.5 py-3 text-left transition-opacity hover:opacity-90"
                  : "flex w-full items-start gap-3 rounded-xl border border-border px-3.5 py-3 text-left transition-colors hover:bg-muted"
              }
            >
              <action.icon
                className={
                  action.primary
                    ? "mt-0.5 h-4 w-4 shrink-0 text-primary-foreground"
                    : "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
                }
              />
              <span className="min-w-0">
                <span
                  className={
                    action.primary
                      ? "block text-[13px] font-semibold text-primary-foreground"
                      : "block text-[13px] font-medium text-foreground"
                  }
                >
                  {action.label}
                </span>
                <span
                  className={
                    action.primary
                      ? "block text-[11px] leading-relaxed text-primary-foreground/80"
                      : "block text-[11px] leading-relaxed text-muted-foreground"
                  }
                >
                  {action.hint}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
