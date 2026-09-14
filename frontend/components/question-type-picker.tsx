"use client";

/**
 * Choosing a question type from the catalogue — a hundred-odd types that should
 * never feel like a hundred.
 *
 * Closed, the picker is a quiet button naming the type. Open, it shows only a
 * short "Suggested" list — the types this class and subject are usually set —
 * under a search box that reaches every other type. The full catalogue, grouped
 * by family, appears only once the teacher searches or asks to browse it.
 *
 * Nothing is hidden for being unusual. A type usually set to other classes is
 * ranked below the rest and shows its class range instead of its marks; a type
 * that needs a printed picture stays listed but disabled, so a teacher learns
 * it exists without choosing one that could only come back empty.
 *
 * Built on Base UI's Combobox, so keyboard navigation, highlighting and
 * screen-reader semantics come with it rather than being rebuilt here.
 */

import * as React from "react";
import { Combobox } from "@base-ui/react/combobox";
import { Check, ChevronsUpDown, Search } from "lucide-react";

import type { QuestionTypeOption } from "@/lib/api-client";
import { SHAPE_DEFAULT_TYPE } from "@/lib/question-types.generated";
import { cn } from "@/lib/utils";

type OptionGroup = {
  label: string;
  items: QuestionTypeOption[];
};

export interface QuestionTypePickerProps {
  /** The current type: a catalogue code, or a runtime shape on older slots. */
  value: string;
  options: QuestionTypeOption[];
  onChange: (option: QuestionTypeOption) => void;
  /** "popover" sits in a slot row; "inline" fills a dialog. */
  variant?: "popover" | "inline";
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}

/** The option a stored value names: its catalogue code, or its shape's default type. */
export function findTypeOption(
  options: QuestionTypeOption[],
  value: string,
): QuestionTypeOption | undefined {
  const key = String(value || "").trim().toUpperCase();
  if (!key) return undefined;
  return (
    options.find((option) => option.code === key) ??
    options.find((option) => option.code === SHAPE_DEFAULT_TYPE[key])
  );
}

/** Every word of the query appears in the label, family or what it tests. */
function matchesQuery(option: QuestionTypeOption, query: string): boolean {
  const haystack = `${option.label} ${option.group} ${option.tests}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

/** This class's own types first, then other classes', then picture types. */
function rank(option: QuestionTypeOption): number {
  if (option.availability !== "available") return 2;
  return option.inClass ? 0 : 1;
}

function humanise(code: string): string {
  return code
    .toLowerCase()
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

function TypeRow({ option }: { option: QuestionTypeOption }) {
  const unavailable = option.availability !== "available";
  const [first, last] = option.classes;
  const aside = unavailable
    ? "Needs a picture"
    : option.inClass
      ? `${option.defaultMarks}m`
      : first === last
        ? `Class ${first}`
        : `Class ${first}–${last}`;

  return (
    <Combobox.Item
      value={option}
      disabled={unavailable}
      title={unavailable ? option.reason : option.tests}
      className="flex cursor-default select-none items-center gap-2 rounded-lg px-2 py-1.5 text-sm outline-none data-highlighted:bg-muted data-disabled:cursor-not-allowed data-disabled:opacity-50"
    >
      <span className="flex size-3.5 shrink-0 items-center justify-center">
        <Combobox.ItemIndicator>
          <Check className="size-3.5" />
        </Combobox.ItemIndicator>
      </span>
      <span className="min-w-0 flex-1 truncate">{option.label}</span>
      <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
        {aside}
      </span>
    </Combobox.Item>
  );
}

export function QuestionTypePicker({
  value,
  options,
  onChange,
  variant = "popover",
  disabled,
  className,
  "aria-label": ariaLabel,
}: QuestionTypePickerProps) {
  const [query, setQuery] = React.useState("");
  const [browsing, setBrowsing] = React.useState(false);

  const selected = React.useMemo(
    () => findTypeOption(options, value),
    [options, value],
  );

  const families = React.useMemo<OptionGroup[]>(() => {
    const byFamily = new Map<string, QuestionTypeOption[]>();
    for (const option of options) {
      const list = byFamily.get(option.group) ?? [];
      list.push(option);
      byFamily.set(option.group, list);
    }
    return Array.from(byFamily, ([label, items]) => ({
      label,
      items: [...items].sort((a, b) => rank(a) - rank(b)),
    }));
  }, [options]);

  const suggestions = React.useMemo<QuestionTypeOption[]>(() => {
    const common = options.filter((option) => option.common);
    // The current type stays one click away even when it is not a suggestion.
    return selected && !selected.common ? [selected, ...common] : common;
  }, [options, selected]);

  const showAll = browsing || query.trim() !== "" || suggestions.length === 0;
  const groups: OptionGroup[] = showAll
    ? families
    : [{ label: "Suggested", items: suggestions }];

  const panel = (
    <>
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
        <Combobox.Input
          placeholder={`Search ${options.length} question types`}
          className="h-9 w-full min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground/70"
        />
      </div>
      {/* Rendered even while the list has items (it announces "no results"),
          so it must take no room when it has nothing to say. */}
      <Combobox.Empty className="px-3 py-6 text-center text-xs text-muted-foreground empty:m-0 empty:p-0">
        No question type matches that.
      </Combobox.Empty>
      <Combobox.List
        className={cn(
          "overflow-y-auto overscroll-contain p-1 empty:p-0",
          // Inline, the list sits in a dialog that scrolls on a phone; kept
          // short enough that the dialog's own buttons stay in view.
          variant === "inline"
            ? "max-h-[min(40vh,20rem)]"
            : "max-h-[min(22rem,var(--available-height))]",
        )}
      >
        {(group: OptionGroup) => (
          <Combobox.Group key={group.label} items={group.items} className="pb-1">
            <Combobox.GroupLabel className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {group.label}
            </Combobox.GroupLabel>
            <Combobox.Collection>
              {(option: QuestionTypeOption) => (
                <TypeRow key={option.code} option={option} />
              )}
            </Combobox.Collection>
          </Combobox.Group>
        )}
      </Combobox.List>
      {showAll ? null : (
        <button
          type="button"
          onClick={() => setBrowsing(true)}
          className="w-full border-t border-border px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
        >
          Browse all {options.length} types
        </button>
      )}
    </>
  );

  return (
    <Combobox.Root
      items={groups}
      value={selected ?? null}
      onValueChange={(next) => {
        if (next) onChange(next as QuestionTypeOption);
      }}
      itemToStringLabel={(option: QuestionTypeOption) => option.label}
      isItemEqualToValue={(a: QuestionTypeOption, b: QuestionTypeOption) =>
        a?.code === b?.code
      }
      filter={(option: QuestionTypeOption, text: string) => matchesQuery(option, text)}
      inputValue={query}
      onInputValueChange={(text) => setQuery(text)}
      onOpenChange={(open) => {
        if (!open) {
          setQuery("");
          setBrowsing(false);
        }
      }}
      autoHighlight
      inline={variant === "inline"}
      disabled={disabled}
    >
      {variant === "inline" ? (
        <div className={cn("overflow-hidden rounded-xl border border-border", className)}>
          {panel}
        </div>
      ) : (
        <>
          <Combobox.Trigger
            aria-label={ariaLabel}
            className={cn(
              "flex h-8 w-full min-w-0 items-center justify-between gap-1 rounded-lg border border-input bg-transparent px-2 text-left text-xs shadow-xs outline-none transition-colors hover:bg-muted/40 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
              className,
            )}
          >
            <span className="truncate">
              {selected?.label ?? (value ? humanise(value) : "Choose a type")}
            </span>
            <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
          </Combobox.Trigger>
          <Combobox.Portal>
            {/* Layer 60 of the app's z-index scale: a picker opened inside a
                modal (the Blueprint Builder is one) must sit above it. */}
            <Combobox.Positioner
              className="isolate z-60 outline-none"
              sideOffset={4}
              align="start"
            >
              <Combobox.Popup className="w-80 max-w-[calc(100vw-2rem)] origin-(--transform-origin) overflow-hidden rounded-xl bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10 outline-none duration-100 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95">
                {panel}
              </Combobox.Popup>
            </Combobox.Positioner>
          </Combobox.Portal>
        </>
      )}
    </Combobox.Root>
  );
}
