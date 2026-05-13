import { db } from "@/lib/db";
import { generateSingleEmbedding } from "./embeddings";

export interface RetrievalResult {
  content: string;
  page: number | null;
  similarity: number;
}

export async function retrieveRelevantChunks(
  query: string,
  documentIds: string[],
  limit: number = 5
): Promise<RetrievalResult[]> {
  if (documentIds.length === 0) return [];

  const queryEmbedding = await generateSingleEmbedding(query);
  const vectorString = `[${queryEmbedding.join(",")}]`;

  const results = await db.$queryRawUnsafe<any[]>(
    `SELECT content, page, 1 - (embedding <=> '${vectorString}'::vector) as similarity
     FROM "DocumentChunk"
     WHERE "documentId" IN (${documentIds.map(id => `'${id}'`).join(",")})
     ORDER BY embedding <=> '${vectorString}'::vector
     LIMIT ${limit};`
  );

  return results.map((r) => ({
    content: r.content,
    page: r.page,
    similarity: r.similarity,
  }));
}
