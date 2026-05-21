import { Node, mergeAttributes } from "@tiptap/core";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
} from "@tiptap/react";
import React from "react";

type PageContainerProps = {
  node: any;
};

export const PageContent = () => {
  return <NodeViewContent />;
};

export const PageContainer = ({ node }: PageContainerProps) => {
  return (
    <NodeViewWrapper className="doc-page" data-page-id={node.attrs.pageId}>
      <div className="doc-page-inner">
        <div className="doc-page-header" contentEditable={false} />
        <div className="doc-page-content editable-container" data-page-content="true">
          <PageContent />
        </div>
        <div className="doc-page-footer" contentEditable={false} />
      </div>
    </NodeViewWrapper>
  );
};

export const PageNode = Node.create({
  name: "page",
  group: "block",
  content: "block+",
  defining: true,
  isolating: true,

  addAttributes() {
    return {
      pageId: { default: null },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="page"]',
        getAttrs: (element) => {
          const pageId = (element as HTMLElement).getAttribute("data-page-id");
          return { pageId };
        },
        contentElement: "div.doc-page-content",
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const pageId = HTMLAttributes.pageId as string | null;
    const attrs: Record<string, string> = {
      "data-type": "page",
      class: "doc-page",
    };

    if (pageId) {
      attrs["data-page-id"] = pageId;
    }

    return [
      "div",
      mergeAttributes(HTMLAttributes, attrs),
      [
        "div",
        { class: "doc-page-inner" },
        ["div", { class: "doc-page-header" }],
        [
          "div",
          { class: "doc-page-content", "data-page-content": "true" },
          0,
        ],
        ["div", { class: "doc-page-footer" }],
      ],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(PageContainer);
  },
});
