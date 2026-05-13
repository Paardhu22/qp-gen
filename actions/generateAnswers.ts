"use server";

import { openai } from "@/lib/openai";

export async function generateAnswerKey(paperContentHTML: string) {
  const prompt = `You are an expert educator. Here is the HTML content of a question paper:
  
  ${paperContentHTML}
  
  Please extract all the questions from this paper and generate a comprehensive answer key for it.
  Format your response as well-structured HTML (using <h1>, <h2>, <p>, <ul>, <li>, <strong>, etc.) that can be directly inserted into a rich text editor.
  Start with <h1 style="text-align: center">Answer Key</h1>.
  Do not include markdown code block wrappers (like \`\`\`html) in your output, just return the raw HTML string.
  `;

  try {
    const completion = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        { role: "system", content: "You are a helpful assistant." },
        { role: "user", content: prompt }
      ]
    });

    const resultText = completion.choices[0].message.content;
    if (!resultText) throw new Error("Failed to generate content");

    return resultText;
  } catch (error) {
    console.error("OpenAI Error:", error);
    throw new Error("Failed to generate answer key");
  }
}
