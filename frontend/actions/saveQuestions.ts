import { fetchProjectsWithQuestions } from "@/lib/api-client";

/**
 * Fetch all questions from the Question Paper, optionally filtered by
 * a search query matched against question content or project name.
 */
export async function getQuestionsFromBank(query?: string): Promise<any[]> {
  const projects = await fetchProjectsWithQuestions<any[]>();

  const allQuestions = (projects as any[]).flatMap((project: any) =>
    (project.questions || []).map((q: any) => ({
      ...q,
      projectName: project.name,
    })),
  );

  if (!query?.trim()) return allQuestions;

  const term = query.trim().toLowerCase();
  return allQuestions.filter(
    (q: any) =>
      q.content?.toLowerCase().includes(term) ||
      q.projectName?.toLowerCase().includes(term),
  );
}
