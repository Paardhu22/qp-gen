import OpenAI from 'openai';

// Initialize the OpenAI client
// The API key is automatically read from the OPENAI_API_KEY environment variable
export const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

/**
 * Architecture placeholder for the RAG-ready question generation pipeline
 */
export async function generateQuestionsFromPrompt(prompt: string, settings: any) {
  // TODO: Implement OpenAI generation logic using structured outputs
  throw new Error("Not implemented");
}
