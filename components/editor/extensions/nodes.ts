import { Node, mergeAttributes } from '@tiptap/core';

export const QuestionItem = Node.create({
  name: 'questionItem',
  group: 'block',
  content: 'block+',
  draggable: true,

  addAttributes() {
    return {
      marks: {
        default: 1,
      },
      number: {
        default: null,
      }
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="question"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div', 
      mergeAttributes(HTMLAttributes, { 'data-type': 'question', class: 'question-item relative pl-8 my-4' }),
      [
        'span', 
        { class: 'absolute left-0 top-0 font-bold text-zinc-500 question-number' }, 
        HTMLAttributes.number ? `${HTMLAttributes.number}.` : ''
      ],
      ['div', { class: 'question-content' }, 0],
      [
        'span', 
        { class: 'absolute right-0 top-0 text-xs font-mono bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-400' }, 
        `[${HTMLAttributes.marks} Marks]`
      ]
    ];
  },
});

export const SectionHeader = Node.create({
  name: 'sectionHeader',
  group: 'block',
  content: 'inline*',
  draggable: true,

  addAttributes() {
    return {
      title: {
        default: 'SECTION A',
      }
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="section-header"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div', 
      mergeAttributes(HTMLAttributes, { 
        'data-type': 'section-header', 
        class: 'section-header w-full border-y border-zinc-800 py-2 my-6 text-center font-bold tracking-widest bg-zinc-900/50' 
      }), 
      0
    ];
  },
});
