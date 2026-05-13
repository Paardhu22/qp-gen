export interface Chunk {
  content: string;
  page?: number;
  chunkIndex: number;
}

export function chunkText(text: string, options: { 
  chunkSize?: number; 
  chunkOverlap?: number;
  pageNumber?: number;
  startIndex?: number;
} = {}): Chunk[] {
  const { 
    chunkSize = 1000, 
    chunkOverlap = 200, 
    pageNumber,
    startIndex = 0
  } = options;

  const chunks: Chunk[] = [];
  let currentPos = 0;
  let index = startIndex;

  while (currentPos < text.length) {
    let endPos = currentPos + chunkSize;
    
    // Try to find a good breaking point (newline or period)
    if (endPos < text.length) {
      const lastNewline = text.lastIndexOf('\n', endPos);
      const lastPeriod = text.lastIndexOf('. ', endPos);
      
      const breakPos = Math.max(lastNewline, lastPeriod);
      
      if (breakPos > currentPos + (chunkSize * 0.5)) {
        endPos = breakPos + 1;
      }
    }

    const content = text.slice(currentPos, endPos).trim();
    
    if (content.length > 0) {
      chunks.push({
        content,
        page: pageNumber,
        chunkIndex: index++
      });
    }

    // Move currentPos forward by chunkSize - overlap
    currentPos = endPos - chunkOverlap;
    
    // Safety check to avoid infinite loop
    if (currentPos <= 0 && text.length > chunkSize) {
        currentPos = endPos; 
    }
    
    // If we're at the end of the text, break
    if (endPos >= text.length) break;
    
    // Ensure we are making progress
    if (currentPos <= (endPos - chunkSize)) {
       currentPos = endPos;
    }
  }

  return chunks;
}

export function chunkPages(pages: { pageNumber: number, content: string }[]): Chunk[] {
  let allChunks: Chunk[] = [];
  let globalIndex = 0;

  for (const page of pages) {
    const pageChunks = chunkText(page.content, { 
      pageNumber: page.pageNumber,
      startIndex: globalIndex
    });
    allChunks = [...allChunks, ...pageChunks];
    globalIndex += pageChunks.length;
  }

  return allChunks;
}
