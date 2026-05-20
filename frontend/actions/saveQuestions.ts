"use server";

import { db } from "@/lib/db";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";

export async function saveQuestionsToBank(data: {
  class: string;
  subject: string;
  topic: string;
  questions: any[];
}) {
  const session = await auth.api.getSession({
    headers: await headers()
  });

  if (!session?.user) {
    throw new Error("Unauthorized");
  }

  const createdQuestions = [];
  
  for (const q of data.questions) {
    const newQ = await db.question.create({
      data: {
        userId: session.user.id,
        class: data.class,
        subject: data.subject,
        topic: data.topic,
        content: q.content,
        answer: q.answer || "",
        questionType: q.type || "mcq",
        marks: Number(q.marks) || 1,
        options: q.options || [],
      }
    });
    createdQuestions.push(newQ);
  }

  return { success: true, count: createdQuestions.length };
}

export async function getQuestionsFromBank(query?: string) {
  const session = await auth.api.getSession({
    headers: await headers()
  });

  if (!session?.user) {
    throw new Error("Unauthorized");
  }

  const whereClause: any = { userId: session.user.id };
  if (query) {
    whereClause.OR = [
      { content: { contains: query, mode: 'insensitive' } },
      { topic: { contains: query, mode: 'insensitive' } },
      { subject: { contains: query, mode: 'insensitive' } },
    ];
  }

  const questions = await db.question.findMany({
    where: whereClause,
    orderBy: { createdAt: "desc" }
  });

  return questions;
}
