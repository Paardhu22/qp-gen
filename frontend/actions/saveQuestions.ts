import { saveQuestions, fetchProjectsWithQuestions } from "@/lib/api-client";

/**
 * Save questions to the Question Paper.
 *
 * Questions are grouped under a Project named "<class> — <subject> — <topic>".
 * Auth is handled by api-client (JWT Bearer token from localStorage), matching
 * the rest of the app — NOT better-auth, which is not used here.
 */
export async function saveQuestionsToBank(data: {
  class: string;
  subject: string;
  topic: string;
  questions: any[];
}): Promise<{ success: boolean; count: number }> {
  const projectName = `${data.class} — ${data.subject} — ${data.topic}`;

  await saveQuestions<{ success: boolean; projectId: string }>({
    projectName,
    questions: data.questions.map((q) => ({
      type: q.type || "short",
      content: q.content,
      answer: q.answer || "",
      options: q.options || [],
      marks: Number(q.marks) || 1,
    })),
  });

  return { success: true, count: data.questions.length };
}

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
