"use client";

import { useState, useRef } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useEditorStore } from "@/store/editor-store";
import { toast } from "sonner";
import { FileCheck, Plus, Trash2, Loader2, AlertCircle } from "lucide-react";
import { fetchForm, streamSse } from "@/lib/api-client";

const formSchema = z.object({
  subject: z.string().min(2, "Subject is required"),
  difficulty: z.string(),
  questionType: z.string(),
  numberOfQuestions: z.string().min(1),
  marks: z.string().min(1),
});

interface UploadingDoc {
  tempId: string;
  name: string;
  status: "uploading" | "error";
  error?: string;
}

export const GeneratorForm = () => {
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      subject: "",
      difficulty: "medium",
      questionType: "mcq",
      numberOfQuestions: "5",
      marks: "1",
    },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedResult, setGeneratedResult] = useState<any>(null);
  const [uploadedDocs, setUploadedDocs] = useState<
    { id: string; name: string; size: number }[]
  >([]);
  const [uploadingDocs, setUploadingDocs] = useState<UploadingDoc[]>([]);
  const [generalInstructions, setGeneralInstructions] = useState("");

  const handleAddSourceClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    // Reset input so the same file can be selected again if needed
    e.target.value = "";

    const currentTotalSize = uploadedDocs.reduce(
      (acc, doc) => acc + (doc.size || 0),
      0,
    );
    let newTotalSize = currentTotalSize;
    let newDocCount = uploadedDocs.length + uploadingDocs.length;

    for (const file of files) {
      if (newDocCount >= 5) {
        toast.error("Maximum of 5 sources allowed.");
        break;
      }
      if (file.size > 100 * 1024 * 1024) {
        toast.error(`File ${file.name} exceeds 100MB limit.`);
        continue;
      }
      if (newTotalSize + file.size > 500 * 1024 * 1024) {
        toast.error("Total upload size cannot exceed 500MB.");
        continue;
      }

      newTotalSize += file.size;
      newDocCount += 1;

      const tempId = `${Date.now()}-${Math.random()}`;
      setUploadingDocs((prev) => [
        ...prev,
        { tempId, name: file.name, status: "uploading" },
      ]);

      try {
        const formData = new FormData();
        formData.append("file", file);

        const data = await fetchForm<{ documentId: string }>(
          "/api/documents/upload",
          formData,
        );

        // Upload succeeded — move from uploading to uploaded
        setUploadingDocs((prev) => prev.filter((d) => d.tempId !== tempId));
        setUploadedDocs((prev) => [
          ...prev,
          { id: data.documentId, name: file.name, size: file.size },
        ]);
      } catch (err: any) {
        setUploadingDocs((prev) =>
          prev.map((d) =>
            d.tempId === tempId
              ? { ...d, status: "error", error: err.message || "Upload failed" }
              : d,
          ),
        );
      }
    }
  };

  const dismissUploadError = (tempId: string) => {
    setUploadingDocs((prev) => prev.filter((d) => d.tempId !== tempId));
  };

  const removeDoc = (id: string) => {
    setUploadedDocs((prev) => prev.filter((d) => d.id !== id));
  };

  const onSubmit = async (values: z.infer<typeof formSchema>) => {
    if (uploadedDocs.length === 0) {
      toast.error("Upload at least one source document first.");
      return;
    }

    try {
      setIsGenerating(true);
      setGeneratedResult(null);

      let generationError: string | null = null;

      await streamSse(
        "/api/generation/questions/stream",
        {
          documentIds: uploadedDocs.map((d) => d.id),
          topic: values.subject,
          count: parseInt(values.numberOfQuestions, 10),
          difficulty: values.difficulty,
          instructions: generalInstructions || "",
        },
        (event, data) => {
          if (event === "error") {
            generationError = data.error || "Generation failed";
          } else if (event === "update" || event === "message") {
            setGeneratedResult(data);
          }
          // "done" event signals stream end — no action needed
        },
      );

      if (generationError) {
        toast.error(generationError);
      }
    } catch (error: any) {
      console.error(error);
      toast.error(
        error?.message ||
          "Failed to generate questions. Check whether your documents contain relevant content.",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAddToEditor = () => {
    if (!generatedResult) return;

    const hasSections =
      generatedResult.sections && generatedResult.sections.length > 0;

    if (hasSections) {
      const sections = generatedResult.sections.map((section: any) => ({
        title: section.title,
        questions: section.questions.map((q: any) => ({
          content: q.content,
          type: q.type,
          options: q.options,
          answer: q.answer,
          marks: q.marks,
        })),
      }));
      useEditorStore.getState().appendSections(sections);
      toast.success("Inserted generated sections into the editor.");
    } else {
      const allQuestions: any[] = [];
      (generatedResult.questions || []).forEach((q: any) => {
        allQuestions.push({
          content: q.content,
          type: q.type,
          options: q.options,
          answer: q.answer,
          marks: q.marks,
        });
      });
      useEditorStore.getState().appendQuestions(allQuestions);
      toast.success("Inserted generated questions into the editor.");
    }
  };

  const hasAnyDocs = uploadedDocs.length > 0 || uploadingDocs.length > 0;

  return (
    <div className="h-full flex flex-col p-4 bg-white dark:bg-zinc-950 text-zinc-600 dark:text-zinc-300 overflow-y-auto custom-scrollbar">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-zinc-900 dark:text-white mb-1">
          Question Generator
        </h2>
        <p className="text-xs text-zinc-500">
          Questions are generated STRICTLY from your source material.
        </p>
      </div>

      {/* Hidden file input — triggered by the Add Source button */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.docx"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Source Documents */}
      <div className="mb-6 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Source Documents
          </label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleAddSourceClick}
            className="h-7 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-500/10"
          >
            <Plus className="h-3 w-3 mr-1" />
            Add Source
          </Button>
        </div>

        <div className="space-y-2">
          {/* Empty state */}
          {!hasAnyDocs && (
            <div className="text-center py-6 border border-dashed border-zinc-200 dark:border-zinc-800 rounded-lg bg-zinc-50 dark:bg-zinc-900/30">
              <p className="text-xs text-zinc-500">
                No documents uploaded yet.
              </p>
            </div>
          )}

          {/* Uploading / error rows */}
          {uploadingDocs.map((doc) => (
            <div
              key={doc.tempId}
              className="flex items-center justify-between p-2 rounded-lg bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800"
            >
              <div className="flex items-center gap-2 min-w-0">
                {doc.status === "uploading" ? (
                  <div className="h-4 w-4 rounded-full bg-zinc-200 dark:bg-zinc-700 animate-pulse flex-shrink-0" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <span className="text-xs text-zinc-700 dark:text-zinc-200 truncate block">
                    {doc.name}
                  </span>
                  {doc.status === "error" && (
                    <span className="text-[10px] text-red-400">
                      {doc.error}
                    </span>
                  )}
                </div>
              </div>
              {doc.status === "error" && (
                <button
                  onClick={() => dismissUploadError(doc.tempId)}
                  className="p-1 hover:text-red-400 transition-colors flex-shrink-0"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}

          {/* Successfully uploaded rows */}
          {uploadedDocs.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center justify-between p-2 rounded-lg bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 group"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileCheck className="h-4 w-4 text-green-500 flex-shrink-0" />
                <span className="text-xs text-zinc-700 dark:text-zinc-200 truncate">
                  {doc.name}
                </span>
              </div>
              <button
                onClick={() => removeDoc(doc.id)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="space-y-6 flex-1"
        >
          <FormField
            control={form.control}
            name="subject"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-zinc-700 dark:text-zinc-300">
                  Topic / Focus Area
                </FormLabel>
                <FormControl>
                  <Input
                    placeholder="e.g. Chemical Bonds"
                    className="bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 focus:ring-indigo-500"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid grid-cols-2 gap-4">
            <FormField
              control={form.control}
              name="difficulty"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-zinc-700 dark:text-zinc-300">
                    Difficulty
                  </FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-900 dark:text-zinc-100">
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent className="bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-900 dark:text-zinc-100">
                      <SelectItem value="easy">Easy</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="hard">Hard</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="numberOfQuestions"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-zinc-700 dark:text-zinc-300">
                    Count
                  </FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min="1"
                      max="50"
                      className="bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-900 dark:text-zinc-100"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          {/* General Instructions */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              General Instructions
            </label>
            <Textarea
              placeholder={
                "e.g. Section A: 4 short answer questions (2 marks each)\nSection B: 4 long answer questions (5 marks each)"
              }
              className="bg-white dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 text-sm resize-none focus:ring-indigo-500 min-h-[90px]"
              value={generalInstructions}
              onChange={(e) => setGeneralInstructions(e.target.value)}
            />
            <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
              Describe section structure and question types. The AI will follow
              these instructions.
            </p>
          </div>

          <div className="pt-4 sticky bottom-0 bg-white dark:bg-zinc-950 pb-4">
            <Button
              type="submit"
              disabled={isGenerating || uploadedDocs.length === 0}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg gap-2"
            >
              {isGenerating
                ? "Analyzing & Generating..."
                : "Generate Questions"}
            </Button>
          </div>
        </form>
      </Form>

      {generatedResult && (
        <div className="mt-6 border-t border-zinc-200 dark:border-zinc-800 pt-6 animate-in fade-in duration-500">
          <h3 className="text-lg font-bold text-zinc-900 dark:text-white mb-4 flex items-center gap-2">
            Generated Output
          </h3>

          <div className="space-y-6">
            {generatedResult.sections?.map((section: any, sIdx: number) => (
              <div key={sIdx} className="space-y-4">
                <h4 className="text-sm font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider">
                  {section.title}
                </h4>
                <div className="space-y-3">
                  {section.questions?.map((q: any, qIdx: number) => (
                    <div
                      key={qIdx}
                      className="p-3 bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-xl space-y-2"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <p className="font-medium text-sm text-zinc-800 dark:text-zinc-100">
                          {q.content}
                        </p>
                        <span className="text-[10px] bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-600 dark:text-zinc-400 font-mono">
                          {q.marks}m
                        </span>
                      </div>
                      {q.options && q.options.length > 0 && (
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          {q.options.map((opt: string, oIdx: number) => (
                            <div
                              key={oIdx}
                              className="text-[11px] text-zinc-500 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-800 p-1.5 rounded bg-white dark:bg-zinc-950/50"
                            >
                              {String.fromCharCode(65 + oIdx)}. {opt}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="mt-2 pt-2 border-t border-zinc-200 dark:border-zinc-800">
                        <p className="text-[10px] text-green-600 dark:text-green-500 font-medium truncate">
                          Ans: {q.answer}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 flex flex-col gap-2">
            {!isGenerating && (
              <>
                <Button
                  className="w-full bg-indigo-600 text-white hover:bg-indigo-700 font-semibold"
                  onClick={handleAddToEditor}
                >
                  Insert All into Editor
                </Button>
                <Button
                  variant="ghost"
                  className="w-full text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300"
                  onClick={() => setGeneratedResult(null)}
                >
                  Clear Results
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
