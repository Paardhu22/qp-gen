"use server";

import { db } from "@/lib/db";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";

export async function saveQuestionsToWorkspace(data: {
  projectName: string;
  questions: any[];
}) {
  const session = await auth.api.getSession({
    headers: await headers()
  });

  if (!session?.user) {
    throw new Error("Unauthorized");
  }

  // Find or create project
  let project = await db.project.findFirst({
    where: {
      name: data.projectName,
      userId: session.user.id
    }
  });

  if (!project) {
    project = await db.project.create({
      data: {
        name: data.projectName,
        userId: session.user.id
      }
    });
  }

  // Create questions
  for (const q of data.questions) {
    await db.question.create({
      data: {
        content: q.content,
        answer: q.answer,
        type: q.type || "mcq",
        marks: Number(q.marks) || 1,
        options: q.options || [],
        projectId: project.id
      }
    });
  }

  return { success: true };
}

export async function getUserProjects() {
  const session = await auth.api.getSession({
    headers: await headers()
  });

  if (!session?.user) {
    return [];
  }

  return db.project.findMany({
    where: { userId: session.user.id },
    orderBy: { createdAt: "desc" }
  });
}
