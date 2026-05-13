import OpenAI from "openai";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export async function generateEmbeddings(texts: string[]): Promise<number[][]> {
  if (texts.length === 0) return [];

  try {
    const response = await openai.embeddings.create({
      model: "text-embedding-3-small",
      input: texts,
    });

    return response.data.map((item) => item.embedding);
  } catch (error) {
    console.error("Error generating embeddings:", error);
    throw new Error("Failed to generate text embeddings");
  }
}

export async function generateSingleEmbedding(text: string): Promise<number[]> {
  const embeddings = await generateEmbeddings([text]);
  return embeddings[0];
}
