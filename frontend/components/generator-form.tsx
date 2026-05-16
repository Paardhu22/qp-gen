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
import { streamSse, fetchForm } from "@/lib/api-client";
import { useEditorStore } from "@/store/editor-store";
import {
  FileCheck,
  Plus,
  Trash2,
  BrainCircuit,
  Loader2,
  AlertCircle,
} from "lucide-react";

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
    { id: string; name: string }[]
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

    for (const file of files) {
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
          { id: data.documentId, name: file.name },
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
      alert("Please upload at least one document to generate questions from.");
      return;
    }

    try {
      setIsGenerating(true);
      setGeneratedResult(null);

      await streamSse(
        "/api/generation/questions/stream",
        {
          documentIds: uploadedDocs.map((d) => d.id),
          topic: values.subject,
          count: parseInt(values.numberOfQuestions, 10),
          difficulty: values.difficulty,
          instructions: generalInstructions,
        },
        (event, data) => {
          if (event === "update") {
            setGeneratedResult(data);
          }
          if (event === "error") {
            throw new Error(data.error || "Failed to generate questions");
          }
        },
      );
    } catch (error) {
      console.error(error);
      alert(
        "Failed to generate questions. Please check if your documents contain the relevant info.",
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
    }
  };

  const hasAnyDocs = uploadedDocs.length > 0 || uploadingDocs.length > 0;

  return (
    <div className="h-full flex flex-col p-4 bg-background text-foreground overflow-y-auto custom-scrollbar">
      <div className="mb-6">
        <p className="text-sm text-muted-foreground">
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
          <label className="text-sm font-medium text-foreground">
            Source Documents
          </label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleAddSourceClick}
            className="h-7 text-xs text-primary hover:text-primary/80 hover:bg-primary/10"
          >
            <Plus className="h-3 w-3 mr-1" />
            Add Source
          </Button>
        </div>

        <div className="space-y-2">
          {/* Empty state */}
          {!hasAnyDocs && (
            <div className="text-center py-6 border border-dashed border-border rounded-lg bg-muted/30">
              <p className="text-xs text-muted-foreground">
                No documents uploaded yet.
              </p>
            </div>
          )}

          {/* Uploading / error rows */}
          {uploadingDocs.map((doc) => (
            <div
              key={doc.tempId}
              className="flex items-center justify-between p-2 rounded-lg bg-muted/50 border border-border"
            >
              <div className="flex items-center gap-2 min-w-0">
                {doc.status === "uploading" ? (
                  <Loader2 className="h-4 w-4 text-primary flex-shrink-0 animate-spin" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <span className="text-xs text-foreground truncate block">
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
              className="flex items-center justify-between p-2 rounded-lg bg-muted/50 border border-border group"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileCheck className="h-4 w-4 text-green-500 flex-shrink-0" />
                <span className="text-xs text-foreground truncate">
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
                <FormLabel>Topic / Focus Area</FormLabel>
                <FormControl>
                  <Input
                    placeholder="e.g. Chemical Bonds"
                    className="bg-muted/50 border-border focus:ring-primary"
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
                  <FormLabel>Difficulty</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="bg-muted/50 border-border">
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent className="bg-popover border-border text-popover-foreground">
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
                  <FormLabel>Count</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min="1"
                      max="50"
                      className="bg-muted/50 border-border"
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
            <label className="text-sm font-medium text-foreground flex items-center gap-1">
              <BrainCircuit className="h-3.5 w-3.5 text-primary" />
              General Instructions
            </label>
            <Textarea
              placeholder={
                "e.g. Section A: 4 short answer questions (2 marks each)\nSection B: 4 long answer questions (5 marks each)"
              }
              className="bg-muted/50 border-border text-sm resize-none focus:ring-primary min-h-[90px]"
              value={generalInstructions}
              onChange={(e) => setGeneralInstructions(e.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">
              Describe section structure and question types. The AI will follow
              these instructions.
            </p>
          </div>

          <div className="pt-4 sticky bottom-0 bg-background pb-4">
            <Button
              type="submit"
              disabled={isGenerating || uploadedDocs.length === 0}
              className="w-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg gap-2"
            >
              {isGenerating
                ? "Analyzing & Generating..."
                : "Generate Questions"}
            </Button>
          </div>
        </form>
      </Form>

      {generatedResult && (
        <div className="mt-6 border-t border-border pt-6 animate-in fade-in duration-500">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
            Generated Output
          </h3>

          <div className="space-y-6">
            {generatedResult.sections?.map((section: any, sIdx: number) => (
              <div key={sIdx} className="space-y-4">
                <h4 className="text-sm font-semibold text-primary uppercase tracking-wider">
                  {section.title}
                </h4>
                <div className="space-y-3">
                  {section.questions?.map((q: any, qIdx: number) => (
                    <div
                      key={qIdx}
                      className="p-3 bg-muted/50 border border-border rounded-xl space-y-2"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <p className="font-medium text-sm text-foreground">
                          {q.content}
                        </p>
                        <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded text-muted-foreground font-mono">
                          {q.marks}m
                        </span>
                      </div>
                      {q.options && q.options.length > 0 && (
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          {q.options.map((opt: string, oIdx: number) => (
                            <div
                              key={oIdx}
                              className="text-[11px] text-muted-foreground border border-border p-1.5 rounded bg-background/50"
                            >
                              {String.fromCharCode(65 + oIdx)}. {opt}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="mt-2 pt-2 border-t border-border">
                        <p className="text-[10px] text-green-600 font-medium truncate">
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
                  className="w-full bg-primary text-primary-foreground hover:bg-primary/90 font-semibold"
                  onClick={handleAddToEditor}
                >
                  Insert All into Editor
                </Button>
                <Button
                  variant="ghost"
                  className="w-full text-muted-foreground hover:text-foreground"
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
