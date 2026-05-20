"use server";

import { db } from "@/lib/db";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";

export async function savePaperAction(data: {
  class: string;
  subject: string;
  examName: string;
  content: string;
  questionRefs: string[];
}) {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user) {
    throw new Error("Unauthorized");
  }

  const newPaper = await db.paper.create({
    data: {
      userId: session.user.id,
      class: data.class,
      subject: data.subject,
      examName: data.examName,
      content: data.content,
      questionRefs: data.questionRefs,
    },
  });

  return { success: true, paperId: newPaper.id };
}

export async function updatePaperAction(
  paperId: string,
  data: {
    class?: string;
    subject?: string;
    examName?: string;
    content?: string;
    questionRefs?: string[];
  }
) {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user) {
    throw new Error("Unauthorized");
  }

  const paper = await db.paper.findUnique({ where: { id: paperId } });
  if (!paper || paper.userId !== session.user.id) {
    throw new Error("Paper not found or unauthorized");
  }

  const updatedPaper = await db.paper.update({
    where: { id: paperId },
    data,
  });

  return { success: true, paperId: updatedPaper.id };
}

export async function getPaperAction(paperId: string) {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user) {
    throw new Error("Unauthorized");
  }

  const paper = await db.paper.findUnique({ where: { id: paperId } });
  if (!paper || paper.userId !== session.user.id) {
    throw new Error("Paper not found or unauthorized");
  }

  return paper;
}
