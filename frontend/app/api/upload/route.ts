import { NextRequest, NextResponse } from 'next/server';
export const dynamic = 'force-dynamic';
import { db } from '@/lib/db';
import { auth } from '@/lib/auth';
import { headers } from 'next/headers';
import { extractTextFromPDF } from '@/lib/pdf';
import { chunkPages, chunkText } from '@/lib/chunking';
import { generateEmbeddings } from '@/lib/embeddings';
import mammoth from 'mammoth';

export async function POST(req: NextRequest) {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session?.user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const formData = await req.formData();
    const file = formData.get('file') as File;
    const projectId = formData.get('projectId') as string | undefined;

    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);
    const fileName = file.name;
    const fileType = file.type;

    let extractedText = '';
    let pages: { pageNumber: number; content: string }[] = [];

    if (fileType === 'application/pdf') {
      const pdfData = await extractTextFromPDF(buffer);
      extractedText = pdfData.text;
      pages = pdfData.pages;
    } else if (fileType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
      const result = await mammoth.extractRawText({ buffer });
      extractedText = result.value;
    } else {
      extractedText = buffer.toString('utf-8');
    }

    if (!extractedText) {
      return NextResponse.json({ error: 'Failed to extract text from document' }, { status: 400 });
    }

    const document = await db.document.create({
      data: {
        title: fileName,
        type: fileType,
        userId: session.user.id,
        projectId: projectId || null,
      },
    });

    let chunks = [];
    if (pages.length > 0) {
      chunks = chunkPages(pages);
    } else {
      chunks = chunkText(extractedText);
    }

    const BATCH_SIZE = 50;
    for (let i = 0; i < chunks.length; i += BATCH_SIZE) {
      const batch = chunks.slice(i, i + BATCH_SIZE);
      const embeddings = await generateEmbeddings(batch.map(c => c.content));

      for (let j = 0; j < batch.length; j++) {
        const chunk = batch[j];
        const embedding = embeddings[j];
        const vectorString = `[${embedding.join(',')}]`;

        await db.$executeRawUnsafe(
          `INSERT INTO "DocumentChunk" ("id", "content", "page", "chunkIndex", "documentId", "embedding")
           VALUES ('${crypto.randomUUID()}', ${JSON.stringify(chunk.content)}, ${chunk.page || 'NULL'}, ${chunk.chunkIndex}, '${document.id}', '${vectorString}'::vector);`
        );
      }
    }

    return NextResponse.json({ documentId: document.id });
  } catch (error: any) {
    console.error('Upload error:', error);
    return NextResponse.json({ error: error.message || 'Failed to process document' }, { status: 500 });
  }
}
