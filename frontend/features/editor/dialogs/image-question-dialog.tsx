"use client";

/**
 * "Question from an image" — and "Use my own image" on an existing question.
 *
 * A teacher brings a picture and can either leave the system to work out what it
 * shows, or tell it: what the image is, what the question should focus on, and
 * what to change about the picture before it is printed. The picture can be
 * edited (crop, highlight, box, arrow, label, cover) by hand, or from a request
 * in words that the AI turns into edits to review.
 *
 * Three promises the dialog keeps:
 *
 *  - **The teacher's words win.** What they write is sent as authoritative; the
 *    AI's own reading of the image fills in only what they leave open.
 *  - **The upload is never modified.** Edits are drawn on a copy. The original
 *    is sent and stored beside the edited picture, and only when edits exist.
 *  - **Nothing is inserted unseen.** The question and what the AI understood of
 *    the picture are shown first; the teacher inserts it, or changes the words
 *    and tries again.
 */

import * as React from "react";
import katex from "katex";
import { toast } from "sonner";
import {
  ArrowUpRight,
  Crop,
  Highlighter,
  ImagePlus,
  MousePointer2,
  Square,
  Trash2,
  Type,
  EyeOff,
  Wand2,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  fetchImageQuestionTypes,
  generateImageQuestion,
  planImageEdits,
  uploadQuestionImage,
  type ImageQuestionResult,
  type ImageQuestionType,
  type ImageQuestionWire,
  type StoredImage,
} from "@/lib/api/image-questions";
import { ImageEditor, type EditorTool } from "../image-editor";
import {
  EDIT_LABELS,
  addEdit,
  describeEdit,
  removeEdit,
  sanitizeEdits,
  type ImageEdit,
} from "../image-edits";
import { ACCEPTED_TYPES, loadImage, prepareUpload, renderEditedBlob, renderEditedImage } from "../render-edits";

const FALLBACK_TYPES: ImageQuestionType[] = [
  { value: "", label: "Let the AI choose" },
  { value: "MCQ", label: "Multiple choice" },
  { value: "SHORT_ANSWER", label: "Short answer" },
  { value: "LONG_ANSWER", label: "Long answer" },
];

const TOOLS: { tool: EditorTool; label: string; icon: React.ReactNode; hint: string }[] = [
  { tool: "select", label: "Select", icon: <MousePointer2 className="size-3.5" />, hint: "Move, resize or delete an edit" },
  { tool: "crop", label: "Crop", icon: <Crop className="size-3.5" />, hint: "Drag to keep only this part" },
  { tool: "highlight", label: "Highlight", icon: <Highlighter className="size-3.5" />, hint: "Drag over the part to mark" },
  { tool: "box", label: "Box", icon: <Square className="size-3.5" />, hint: "Drag to outline a part" },
  { tool: "arrow", label: "Arrow", icon: <ArrowUpRight className="size-3.5" />, hint: "Drag from the tail to the point" },
  { tool: "label", label: "Label", icon: <Type className="size-3.5" />, hint: "Click where the text should go" },
  { tool: "cover", label: "Cover", icon: <EyeOff className="size-3.5" />, hint: "Drag over a part to remove it" },
];

/** Text with `\( … \)` maths typeset, for the question preview. */
function MathText({ text }: { text: string }) {
  const parts = React.useMemo(() => text.split(/(\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])/g), [text]);
  return (
    <>
      {parts.map((part, i) => {
        const display = part.startsWith("\\[");
        if (part.startsWith("\\(") || display) {
          const latex = part.slice(2, -2).trim();
          return (
            <span
              key={i}
              dangerouslySetInnerHTML={{ __html: katex.renderToString(latex, { displayMode: display, throwOnError: false }) }}
            />
          );
        }
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
    </>
  );
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** "create" writes a question about the picture; "attach" puts it in an existing question. */
  mode: "create" | "attach";
  subject?: string;
  classNum?: string | number;
  /** attach mode: the question the picture is for. */
  questionText?: string;
  onInsertQuestion?: (question: ImageQuestionWire) => void;
  onAttachImage?: (image: StoredImage) => void;
}

export function ImageQuestionDialog({
  open,
  onOpenChange,
  mode,
  subject: subjectProp = "",
  classNum: classProp = "10",
  questionText = "",
  onInsertQuestion,
  onAttachImage,
}: Props) {
  const [prepared, setPrepared] = React.useState<{ blob: Blob; resized: boolean } | null>(null);
  const [img, setImg] = React.useState<HTMLImageElement | null>(null);
  const [src, setSrc] = React.useState("");
  const [fileName, setFileName] = React.useState("");

  const [description, setDescription] = React.useState("");
  const [instructions, setInstructions] = React.useState("");
  const [subject, setSubject] = React.useState(subjectProp);
  const [classNum, setClassNum] = React.useState(String(classProp || "10"));
  const [type, setType] = React.useState("");
  const [marks, setMarks] = React.useState("");
  const [difficulty, setDifficulty] = React.useState("");
  const [types, setTypes] = React.useState<ImageQuestionType[]>(FALLBACK_TYPES);

  const [edits, setEdits] = React.useState<ImageEdit[]>([]);
  const [tool, setTool] = React.useState<EditorTool>("select");
  const [selected, setSelected] = React.useState(-1);
  const [showEditor, setShowEditor] = React.useState(false);
  const [editRequest, setEditRequest] = React.useState("");
  const [planning, setPlanning] = React.useState(false);
  const [unsupported, setUnsupported] = React.useState<string[]>([]);
  const [notes, setNotes] = React.useState<string[]>([]);
  const [preview, setPreview] = React.useState("");

  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<ImageQuestionResult | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const fileInput = React.useRef<HTMLInputElement>(null);

  // Start clean each time the dialog opens; keep what was typed while it stays open.
  React.useEffect(() => {
    if (!open) return;
    setSubject(subjectProp);
    setClassNum(String(classProp || "10"));
  }, [open, subjectProp, classProp]);

  React.useEffect(() => {
    if (!open) {
      setPrepared(null);
      setImg(null);
      setSrc("");
      setFileName("");
      setDescription("");
      setInstructions("");
      setType("");
      setMarks("");
      setDifficulty("");
      setEdits([]);
      setSelected(-1);
      setShowEditor(false);
      setEditRequest("");
      setUnsupported([]);
      setNotes([]);
      setResult(null);
      setBusy(false);
    }
  }, [open]);

  React.useEffect(() => {
    if (!open || mode !== "create") return;
    let live = true;
    fetchImageQuestionTypes()
      .then((r) => live && r.types?.length && setTypes(r.types))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [open, mode]);

  // The picture as it will be printed, redrawn whenever the edits change.
  React.useEffect(() => {
    if (!img || edits.length === 0) {
      setPreview("");
      return;
    }
    const canvas = renderEditedImage(img, edits, 900);
    setPreview(canvas.toDataURL("image/png"));
  }, [img, edits]);

  const chooseFile = React.useCallback(async (file: File | null | undefined) => {
    if (!file) return;
    if (!(ACCEPTED_TYPES as readonly string[]).includes(file.type)) {
      toast.error("Choose a PNG, JPEG, WebP or GIF image.");
      return;
    }
    try {
      const ready = await prepareUpload(file);
      const image = await loadImage(ready.blob);
      setPrepared({ blob: ready.blob, resized: ready.resized });
      setImg(image);
      setSrc(image.src);
      setFileName(file.name || "pasted image");
      setEdits([]);
      setSelected(-1);
      setResult(null);
      setUnsupported([]);
      setNotes([]);
      if (ready.resized) toast.info("That picture was very large, so it was reduced to a size the server accepts.");
    } catch (error: any) {
      toast.error(error?.message || "That file could not be opened as an image.");
    }
  }, []);

  const onPaste = (event: React.ClipboardEvent) => {
    const item = Array.from(event.clipboardData?.items ?? []).find((i) => i.type.startsWith("image/"));
    const file = item?.getAsFile();
    if (file) {
      event.preventDefault();
      void chooseFile(file);
    }
  };

  const suggestEdits = async () => {
    if (!prepared || !editRequest.trim()) return;
    setPlanning(true);
    try {
      const plan = await planImageEdits({ image: prepared.blob, instruction: editRequest, description });
      const proposed = sanitizeEdits(plan.edits);
      setEdits((current) => proposed.reduce((list, edit) => addEdit(list, edit), current));
      setNotes(plan.notes ?? []);
      setUnsupported(plan.unsupported ?? []);
      setShowEditor(true);
      setSelected(-1);
      if (proposed.length === 0) toast.info("No edits could be worked out from that. Try describing it differently, or draw them yourself.");
      else toast.success("Suggested edits are drawn on the picture — check them before using it.");
    } catch (error: any) {
      toast.error(error?.message || "Edits could not be suggested right now.");
    } finally {
      setPlanning(false);
    }
  };

  /** What goes to the server: the edited copy and the untouched original, or just the original. */
  const picture = async () => {
    if (!prepared || !img) throw new Error("Choose an image first.");
    if (edits.length === 0) return { image: prepared.blob, original: null as Blob | null, edits: [] as ImageEdit[] };
    return { image: await renderEditedBlob(img, edits), original: prepared.blob, edits };
  };

  const create = async () => {
    setBusy(true);
    try {
      const pic = await picture();
      const output = await generateImageQuestion({
        ...pic,
        description,
        instructions,
        subject,
        classNum,
        questionType: type,
        marks: marks ? Number(marks) : null,
        difficulty,
      });
      setResult(output);
    } catch (error: any) {
      toast.error(error?.message || "The question could not be written. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const attach = async () => {
    setBusy(true);
    try {
      const pic = await picture();
      const stored = await uploadQuestionImage({ ...pic, description });
      onAttachImage?.(stored);
      onOpenChange(false);
    } catch (error: any) {
      toast.error(error?.message || "The picture could not be added. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const insert = () => {
    if (!result) return;
    onInsertQuestion?.(result.question);
    onOpenChange(false);
  };

  const selectedEdit = selected >= 0 ? edits[selected] : undefined;
  const isCreate = mode === "create";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl" onPaste={onPaste}>
        <DialogHeader>
          <DialogTitle>{isCreate ? "Question from an image" : "Use my own image"}</DialogTitle>
          <DialogDescription>
            {isCreate
              ? "Add a picture and, if you like, tell the AI what it shows and what to ask. Leave the boxes empty and it works it out from the picture."
              : "Add your own picture to this question. Your original is kept untouched; edits are made on a copy."}
          </DialogDescription>
          {!isCreate && questionText ? (
            <p className="line-clamp-2 rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">{questionText}</p>
          ) : null}
        </DialogHeader>

        {result ? (
          <ResultPanel result={result} />
        ) : (
          <div className="space-y-5">
            {/* 1 — the picture */}
            {!src ? (
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  void chooseFile(e.dataTransfer.files?.[0]);
                }}
                className={cn(
                  "flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center text-sm text-muted-foreground transition-colors hover:border-primary/60 hover:bg-accent/40",
                  dragging && "border-primary bg-accent/40",
                )}
              >
                <ImagePlus className="size-6" aria-hidden />
                <span className="font-medium text-foreground">Choose an image, drop one here, or paste it</span>
                <span className="text-xs">PNG, JPEG, WebP or GIF · up to 8 MB</span>
              </button>
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                <span className="truncate">{fileName}</span>
                <Button type="button" variant="ghost" size="sm" onClick={() => fileInput.current?.click()}>
                  Change image
                </Button>
              </div>
            )}
            <input
              ref={fileInput}
              type="file"
              accept={ACCEPTED_TYPES.join(",")}
              className="sr-only"
              aria-label="Choose an image"
              onChange={(e) => {
                void chooseFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />

            {src ? (
              <>
                {/* 2 — what it is, and what to ask */}
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium">What does this image show?</span>
                    <Textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="e.g. A velocity–time graph of a lift moving between three floors."
                      rows={3}
                      maxLength={2000}
                    />
                    <span className="block text-xs text-muted-foreground">
                      Optional. {isCreate ? "The AI treats this as true where the picture is unclear." : "Used as the picture’s alt text."}
                    </span>
                  </label>
                  {isCreate ? (
                    <label className="space-y-1.5 text-sm">
                      <span className="font-medium">What should the question focus on?</span>
                      <Textarea
                        value={instructions}
                        onChange={(e) => setInstructions(e.target.value)}
                        placeholder="e.g. Ask for the distance travelled in the first 4 seconds. Use numbers read from the graph."
                        rows={3}
                        maxLength={2000}
                      />
                      <span className="block text-xs text-muted-foreground">
                        Optional. Your instructions take priority over the AI’s own choices.
                      </span>
                    </label>
                  ) : null}
                </div>

                {isCreate ? (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <Field label="Question type">
                      <select value={type} onChange={(e) => setType(e.target.value)} className={SELECT}>
                        {types.map((t) => (
                          <option key={t.value} value={t.value}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Marks">
                      <select value={marks} onChange={(e) => setMarks(e.target.value)} className={SELECT}>
                        <option value="">Let the AI choose</option>
                        {[1, 2, 3, 4, 5, 6].map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Difficulty">
                      <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} className={SELECT}>
                        <option value="">Moderate</option>
                        <option value="easy">Easier</option>
                        <option value="hard">Harder</option>
                      </select>
                    </Field>
                    <Field label="Class">
                      <select value={classNum} onChange={(e) => setClassNum(e.target.value)} className={SELECT}>
                        {Array.from({ length: 12 }, (_, i) => String(i + 1)).map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Subject">
                      <input
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                        placeholder="e.g. Science"
                        className={SELECT}
                      />
                    </Field>
                  </div>
                ) : null}

                {/* 3 — change the picture (optional) */}
                <div className="rounded-lg border">
                  <button
                    type="button"
                    onClick={() => setShowEditor((v) => !v)}
                    aria-expanded={showEditor}
                    className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm font-medium"
                  >
                    <span>
                      Change the picture
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        {edits.length ? `${edits.length} edit${edits.length === 1 ? "" : "s"}` : "optional · crop, highlight, label, remove a part"}
                      </span>
                    </span>
                    <span aria-hidden className="text-muted-foreground">{showEditor ? "−" : "+"}</span>
                  </button>

                  {showEditor ? (
                    <div className="space-y-3 border-t p-3">
                      <div className="flex gap-2">
                        <input
                          value={editRequest}
                          onChange={(e) => setEditRequest(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void suggestEdits();
                            }
                          }}
                          placeholder="Or describe a change: “crop to the circuit and highlight R2”"
                          aria-label="Describe a change to the picture"
                          className={cn(SELECT, "flex-1")}
                        />
                        <Button type="button" variant="outline" size="sm" onClick={suggestEdits} disabled={planning || !editRequest.trim()}>
                          {planning ? <Spinner /> : <Wand2 className="size-3.5" />}
                          Suggest edits
                        </Button>
                      </div>

                      {notes.length || unsupported.length ? (
                        <div className="space-y-1 rounded-md bg-muted/60 px-3 py-2 text-xs">
                          {notes.map((n, i) => (
                            <p key={i}>✓ {n}</p>
                          ))}
                          {unsupported.map((u, i) => (
                            <p key={i} className="text-amber-700 dark:text-amber-400">
                              ⚠ Couldn’t do this automatically: {u}
                              {isCreate ? (
                                <button
                                  type="button"
                                  className="ml-2 underline"
                                  onClick={() => setInstructions((cur) => (cur ? `${cur}\n${u}` : u))}
                                >
                                  Add to the instructions
                                </button>
                              ) : null}
                            </p>
                          ))}
                        </div>
                      ) : null}

                      <div className="flex flex-wrap gap-1" role="toolbar" aria-label="Image tools">
                        {TOOLS.map((t) => (
                          <Button
                            key={t.tool}
                            type="button"
                            size="sm"
                            variant={tool === t.tool ? "default" : "outline"}
                            onClick={() => setTool(t.tool)}
                            title={t.hint}
                            aria-pressed={tool === t.tool}
                          >
                            {t.icon}
                            {t.label}
                          </Button>
                        ))}
                      </div>

                      <ImageEditor
                        src={src}
                        edits={edits}
                        onChange={setEdits}
                        tool={tool}
                        onToolChange={setTool}
                        selected={selected}
                        onSelect={setSelected}
                      />

                      {selectedEdit?.op === "label" ? (
                        <label className="flex items-center gap-2 text-xs">
                          <span className="text-muted-foreground">Label text</span>
                          <input
                            value={selectedEdit.text}
                            maxLength={60}
                            onChange={(e) =>
                              setEdits((list) => list.map((x, i) => (i === selected && x.op === "label" ? { ...x, text: e.target.value } : x)))
                            }
                            className={cn(SELECT, "flex-1")}
                          />
                        </label>
                      ) : null}

                      {edits.length ? (
                        <ul className="flex flex-wrap gap-1.5 text-xs" aria-label="Edits">
                          {edits.map((edit, i) => (
                            <li key={i}>
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1 rounded-full border px-2 py-1",
                                  i === selected && "border-primary bg-primary/10",
                                )}
                              >
                                <button type="button" onClick={() => { setSelected(i); setTool("select"); }}>
                                  {describeEdit(edit)}
                                </button>
                                <button
                                  type="button"
                                  aria-label={`Remove ${EDIT_LABELS[edit.op]}`}
                                  onClick={() => {
                                    setEdits(removeEdit(edits, i));
                                    setSelected(-1);
                                  }}
                                >
                                  <Trash2 className="size-3" />
                                </button>
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : null}

                      {edits.length ? (
                        <div className="space-y-1.5">
                          <p className="text-xs font-medium">This is what will be printed</p>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          {preview ? <img src={preview} alt="The edited picture" className="max-h-56 rounded-md border" /> : null}
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>Your original picture is kept as it was.</span>
                            <button type="button" className="underline" onClick={() => { setEdits([]); setSelected(-1); setNotes([]); setUnsupported([]); }}>
                              Remove all edits
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          {result ? (
            <>
              <Button type="button" variant="outline" onClick={() => setResult(null)}>
                Change and try again
              </Button>
              <Button type="button" onClick={insert}>
                Insert into the paper
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="button" onClick={isCreate ? create : attach} disabled={!prepared || busy}>
                {busy ? <Spinner /> : null}
                {isCreate ? (busy ? "Reading the picture…" : "Create question") : busy ? "Adding…" : "Use this image"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const SELECT =
  "h-9 w-full rounded-lg border border-input bg-transparent px-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="space-y-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

/** The generated question and what the AI understood of the picture. */
function ResultPanel({ result }: { result: ImageQuestionResult }) {
  const { question, understanding, image } = result;
  const letters = ["A", "B", "C", "D", "E", "F"];
  return (
    <div className="space-y-4 text-sm">
      <section className="rounded-lg border bg-muted/40 p-3" aria-label="How the picture was read">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">How the AI read your picture</h3>
        <p>{understanding.summary || "It could not describe this picture."}</p>
        {understanding.elements.length ? (
          <p className="mt-1 text-xs text-muted-foreground">Parts it noticed: {understanding.elements.join(" · ")}</p>
        ) : null}
        {understanding.concerns.length ? (
          <ul className="mt-2 list-disc pl-5 text-xs text-amber-700 dark:text-amber-400">
            {understanding.concerns.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        ) : null}
        <p className="mt-2 text-xs text-muted-foreground">
          {result.usedDescription || result.usedInstructions
            ? "Your description and instructions were treated as authoritative."
            : "You gave no description, so this is the AI’s own reading."}
          {image.edited ? " The picture shown below has your edits; your original is kept." : ""}
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_1fr]" aria-label="The question">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={image.url} alt={image.alt || "The picture used in the question"} className="w-full rounded-md border bg-white object-contain" />
        <div className="space-y-2">
          <p className="whitespace-pre-line leading-relaxed">
            <MathText text={question.content} />
          </p>
          {question.options.length ? (
            <ol className="space-y-1">
              {question.options.map((o, i) => (
                <li key={i} className="flex gap-2">
                  <span className="font-semibold">({letters[i] ?? i + 1})</span>
                  <span>
                    <MathText text={o} />
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
          <p className="text-xs text-muted-foreground">
            {question.marks} mark{question.marks === 1 ? "" : "s"} · {question.type.replace(/_/g, " ").toLowerCase()}
          </p>
          <p className="rounded-md bg-emerald-50 px-2.5 py-1.5 text-xs text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">
            <span className="font-semibold">Answer:</span> <MathText text={question.answer} />
          </p>
        </div>
      </section>
    </div>
  );
}
