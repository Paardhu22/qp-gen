"use server";

import { streamObject } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import { retrieveRelevantChunks } from '@/lib/retrieval';
import { createStreamableValue } from '@ai-sdk/rsc';

const questionSchema = z.object({
  sections: z.array(z.object({
    title: z.string(),
    questions: z.array(z.object({
      content: z.string(),
      type: z.enum(['MCQ', 'SHORT', 'LONG', 'TF']),
      options: z.array(z.string()).optional(),
      answer: z.string(),
      marks: z.number()
    }))
  }))
});

export async function generateQuestionsStream(params: {
  documentIds: string[];
  topic: string;
  count: number;
  difficulty: string;
}) {
  const { documentIds, topic, count, difficulty } = params;
  const stream = createStreamableValue();

  (async () => {
    try {
      const context = await retrieveRelevantChunks(topic, documentIds, 15);
      const contextText = context.map(c => c.content).join('\n\n');

      if (context.length === 0) {
        stream.error("No relevant content found in the uploaded documents.");
        return;
      }

      const { partialObjectStream } = await streamObject({
        model: openai('gpt-4o'),
        schema: questionSchema,
        system: `You are an expert exam question generator. 
        Your task is to generate high-quality exam questions based ONLY on the provided context.
        
        STRICT RULES:
        1. Do NOT hallucinate. 
        2. ONLY use the retrieved context below.
        3. If a question or its answer cannot be fully supported by the context, do NOT generate it.
        4. If there is insufficient context to generate the requested ${count} questions, generate only what is possible.
        5. Provide a mix of types: MCQ (Multiple Choice), SHORT (Short Answer), LONG (Long Answer), and TF (True/False).
        6. For MCQ, provide exactly 4 options.
        7. For TF, the options should be ['True', 'False'].
        
        Context:
        ${contextText}`,
        prompt: `Generate ${count} ${difficulty} difficulty questions about "${topic}".`,
      });

      for await (const partialObject of partialObjectStream) {
        stream.update(partialObject);
      }

      stream.done();
    } catch (error: any) {
      console.error('Generation error:', error);
      stream.error(error.message || 'Failed to generate questions');
    }
  })();

  return { object: stream.value };
}
