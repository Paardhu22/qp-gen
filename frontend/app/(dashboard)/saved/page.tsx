"use client";

import { useEffect, useState } from "react";
import { fetchProjects } from "@/lib/api-client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function SavedQuestionsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchProjects<any[]>()
      .then(setProjects)
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="p-8 space-y-8 bg-background min-h-full">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-foreground">Saved Questions</h2>
        <p className="text-muted-foreground mt-2">View and manage questions saved to your workspace subdivisions.</p>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground text-center py-12 border border-dashed border-border rounded-lg">
          Loading saved questions...
        </div>
      ) : projects.length === 0 ? (
        <div className="text-muted-foreground text-center py-12 border border-dashed border-border rounded-lg">
          No saved questions or subdivisions found.
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <Card key={project.id} className="bg-card border-border flex flex-col h-full">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg text-foreground">{project.name}</CardTitle>
                <CardDescription className="text-muted-foreground">
                  {project.questions.length} questions saved
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 overflow-y-auto max-h-64 custom-scrollbar space-y-3">
                {project.questions.map((q: any, idx: number) => (
                  <div key={q.id} className="p-3 bg-muted/50 rounded-md border border-border">
                    <div className="flex justify-between items-start gap-2 mb-2">
                      <span className="text-xs font-medium text-muted-foreground">Q{idx + 1}</span>
                      <Badge variant="outline" className="text-xs border-primary/50 text-primary bg-primary/10">
                        {q.type} - {q.marks}m
                      </Badge>
                    </div>
                    <p className="text-sm text-foreground">{q.content}</p>
                    {q.answer && (
                      <div className="mt-2 text-xs text-muted-foreground bg-muted p-2 rounded">
                        <span className="text-green-600 font-medium mr-1">Answer:</span>
                        {q.answer}
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
