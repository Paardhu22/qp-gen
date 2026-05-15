const pdf = require('pdf-parse');

export interface ExtractedPage {
  pageNumber: number;
  content: string;
}

export interface PDFData {
  text: string;
  metadata: any;
  pages: ExtractedPage[];
}

export async function extractTextFromPDF(buffer: Buffer): Promise<PDFData> {
  try {
    const data = await pdf(buffer);
    
    const pages: ExtractedPage[] = [];
    let currentPage = 1;
    
    const options = {
      pagerender: (pageData: any) => {
        return pageData.getTextContent().then((textContent: any) => {
          let lastY, text = '';
          for (const item of textContent.items) {
            if (lastY == item.transform[5] || !lastY) {
              text += item.str;
            } else {
              text += '\n' + item.str;
            }
            lastY = item.transform[5];
          }
          pages.push({
            pageNumber: currentPage++,
            content: text
          });
          return text;
        });
      }
    };

    await pdf(buffer, options);

    return {
      text: data.text,
      metadata: data.metadata,
      pages: pages
    };
  } catch (error) {
    console.error('Error parsing PDF:', error);
    throw new Error('Failed to parse PDF document');
  }
}
