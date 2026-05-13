"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { FileUpload } from "@/components/file-upload";
import { streamSse } from "@/lib/api-client";
import { useEditorStore } from "@/store/editor-store";
import { FileCheck, Sparkles, Plus, Trash2, BrainCircuit } from "lucide-react";

const formSchema = z.object({
  subject: z.string().min(2, "Subject is required"),
  difficulty: z.string(),
  questionType: z.string(),
  numberOfQuestions: z.string().min(1),
  marks: z.string().min(1),
});

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

  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedResult, setGeneratedResult] = useState<any>(null);
  const [uploadedDocs, setUploadedDocs] = useState<{ id: string; name: string }[]>([]);
  const [showUpload, setShowUpload] = useState(false);

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
        },
        (event, data) => {
          if (event === "update") {
            setGeneratedResult(data);
          }
          if (event === "error") {
            throw new Error(data.error || "Failed to generate questions");
          }
        }
      );
    } catch (error) {
      console.error(error);
      alert("Failed to generate questions. Please check if your documents contain the relevant info.");
    } finally {
      setIsGenerating(false);
    }
  };

  const addDoc = (id: string) => {
    // In a real app, you'd fetch the doc name. For now we use a placeholder or the component handles it.
    // Let's assume we want to refresh the list or just add it.
    // For simplicity, we will just add a placeholder name if not provided.
    setUploadedDocs(prev => [...prev, { id, name: "New Document" }]);
    setShowUpload(false);
  };

  const removeDoc = (id: string) => {
    setUploadedDocs(prev => prev.filter(d => d.id !== id));
  };

  const handleAddToEditor = () => {
    if (!generatedResult) return;
    
    const allQuestions: any[] = [];
    generatedResult.sections.forEach((section: any) => {
      section.questions.forEach((q: any) => {
        allQuestions.push({
          content: q.content,
          type: q.type,
          options: q.options,
          answer: q.answer,
          marks: q.marks
        });
      });
    });

    useEditorStore.getState().appendQuestions(allQuestions);
  };

  return (
    <div className="h-full flex flex-col p-4 bg-zinc-950 text-zinc-100 overflow-y-auto custom-scrollbar">
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <BrainCircuit className="h-5 w-5 text-indigo-500" />
          <h2 className="text-xl font-bold">AI Generator</h2>
        </div>
        <p className="text-sm text-zinc-400">Questions are generated STRICTLY from your source material.</p>
      </div>

      <div className="mb-6 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-zinc-300">Source Documents</label>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setShowUpload(!showUpload)}
            className="h-7 text-xs text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10"
          >
            {showUpload ? "Cancel" : <><Plus className="h-3 w-3 mr-1" /> Add Source</>}
          </Button>
        </div>

        {showUpload && (
          <div className="animate-in fade-in slide-in-from-top-2 duration-200">
            <FileUpload onUploadComplete={addDoc} />
          </div>
        )}

        <div className="space-y-2">
          {uploadedDocs.length === 0 && !showUpload && (
            <div className="text-center py-6 border border-dashed border-zinc-800 rounded-lg bg-zinc-900/30">
              <p className="text-xs text-zinc-500">No documents uploaded yet.</p>
            </div>
          )}
          {uploadedDocs.map(doc => (
            <div key={doc.id} className="flex items-center justify-between p-2 rounded-lg bg-zinc-900 border border-zinc-800 group">
              <div className="flex items-center gap-2 min-w-0">
                <FileCheck className="h-4 w-4 text-green-500 flex-shrink-0" />
                <span className="text-xs text-zinc-300 truncate">{doc.name}</span>
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
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 flex-1">
          <FormField
            control={form.control}
            name="subject"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Topic / Focus Area</FormLabel>
                <FormControl>
                  <Input placeholder="e.g. Chemical Bonds" className="bg-zinc-900 border-zinc-800 focus:ring-indigo-500" {...field} />
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
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <FormControl>
                      <SelectTrigger className="bg-zinc-900 border-zinc-800">
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent className="bg-zinc-900 border-zinc-800 text-zinc-100">
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
                    <Input type="number" min="1" max="50" className="bg-zinc-900 border-zinc-800" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <div className="pt-4 sticky bottom-0 bg-zinc-950 pb-4">
            <Button 
              type="submit" 
              disabled={isGenerating || uploadedDocs.length === 0} 
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg shadow-indigo-900/20 gap-2"
            >
              {isGenerating ? "Analyzing & Generating..." : <><Sparkles className="h-4 w-4" /> Generate Questions</>}
            </Button>
          </div>
        </form>
      </Form>
      
      {generatedResult && (
        <div className="mt-6 border-t border-zinc-800 pt-6 animate-in fade-in duration-500">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            Generated Output
          </h3>
          
          <div className="space-y-6">
            {generatedResult.sections?.map((section: any, sIdx: number) => (
              <div key={sIdx} className="space-y-4">
                <h4 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider">{section.title}</h4>
                <div className="space-y-3">
                  {section.questions?.map((q: any, qIdx: number) => (
                    <div key={qIdx} className="p-3 bg-zinc-900 border border-zinc-800 rounded-xl space-y-2">
                      <div className="flex justify-between items-start gap-2">
                        <p className="font-medium text-sm text-zinc-100">{q.content}</p>
                        <span className="text-[10px] bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-400 font-mono">{q.marks}m</span>
                      </div>
                      {q.options && q.options.length > 0 && (
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          {q.options.map((opt: string, oIdx: number) => (
                            <div key={oIdx} className="text-[11px] text-zinc-400 border border-zinc-800 p-1.5 rounded bg-zinc-950/50">
                              {String.fromCharCode(65 + oIdx)}. {opt}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="mt-2 pt-2 border-t border-zinc-800">
                         <p className="text-[10px] text-green-500/80 font-medium truncate">Ans: {q.answer}</p>
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
                  className="w-full bg-zinc-100 text-zinc-900 hover:bg-white font-semibold"
                  onClick={handleAddToEditor}
                >
                  Insert All into Editor
                </Button>
                <Button 
                  variant="ghost"
                  className="w-full text-zinc-400 hover:text-zinc-200"
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
