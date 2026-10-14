let pageIdCounter = 0;

export const PAGE_DIMENSIONS = {
  width: 794,
  height: 1123,
  padding: 40,
};

export function createPageId() {
  pageIdCounter += 1;
  return `page-${Date.now()}-${pageIdCounter}`;
}

export function wrapHtmlInPage(html: string, pageId: string = createPageId()) {
  const safeHtml = html || "";
  return `\n    <div data-type="page" data-page-id="${pageId}">\n      <div class="doc-page-inner">\n        <div class="doc-page-header"></div>\n        <div class="doc-page-content" data-page-content="true">${safeHtml}</div>\n        <div class="doc-page-footer"></div>\n      </div>\n    </div>\n  `;
}

export function ensurePageDocument(json: any) {
  if (!json || typeof json !== "object" || json.type !== "doc") return json;

  const hasPage = Array.isArray(json.content)
    ? json.content.some((node: any) => node?.type === "page")
    : false;

  if (hasPage) return json;

  const content = Array.isArray(json.content) && json.content.length > 0
    ? json.content
    : [{ type: "paragraph" }];

  return {
    type: "doc",
    content: [
      {
        type: "page",
        attrs: { pageId: createPageId() },
        content,
      },
    ],
  };
}

export function extractPagesFromDoc(doc: any) {
  if (!doc?.content) return [];

  const pages: Array<{ id: string; blocks: any[] }> = [];
  let pageIndex = 1;

  doc.forEach((node: any) => {
    if (node.type?.name !== "page") return;
    const blocks: any[] = [];
    node.forEach((child: any) => {
      blocks.push(child.toJSON());
    });
    pages.push({
      id: node.attrs?.pageId || `page-${pageIndex}`,
      blocks,
    });
    pageIndex += 1;
  });

  return pages;
}
