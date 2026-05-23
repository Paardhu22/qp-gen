"use server";

import { openai } from "@/lib/openai";

export async function generateQuestions(data: {
  subject: string;
  difficulty: string;
  questionType: string;
  numberOfQuestions: string;
  marks: string;
  sourceText?: string;
}) {
  const prompt = `You are an expert exam question generator. Generate ${data.numberOfQuestions} questions for the subject "${data.subject}".
  Difficulty: ${data.difficulty}
  Question Type: ${data.questionType}
  Marks per Question: ${data.marks}
  ${data.sourceText ? `Base the questions on this text: ${data.sourceText}` : ''}
  
  Output the result as a JSON object with a single array property "questions".
  Each question object must have:
  - content: string (the question text)
  - answer: string (the suggested answer)
  - options: string[] (if it is MCQ, provide 4 options, else empty array)
  - type: string (the question type)
  - marks: number (the marks)
  `;

  try {
    const completion = await openai.chat.completions.create({
      model: "gpt-5-mini",
      messages: [
        { role: "system", content: "You are a helpful assistant designed to output JSON." },
        { role: "user", content: prompt }
      ],
      response_format: { type: "json_object" },
    });

    const resultText = completion.choices[0].message.content;
    if (!resultText) throw new Error("Failed to generate content");

    const parsed = JSON.parse(resultText);
    return parsed.questions || [];
  } catch (error) {
    console.error("OpenAI Error:", error);
    throw new Error("Failed to generate questions");
  }
}
