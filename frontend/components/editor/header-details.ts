/** Paper details shared by the editor, saved HTML and Word export. */
export interface HeaderDetail { id: string; label: string; value: string }
interface HeaderNode { attrs?: Record<string, unknown>; content?: HeaderNode[]; type?: string; text?: string }

export const HEADER_FIELDS = [
  { id: "subject", label: "Subject" },
  { id: "class", label: "Class" },
  { id: "marks", label: "Max marks" },
  { id: "set", label: "Set" },
  { id: "time", label: "Time" },
] as const;

const aliases: Record<string, string> = {
  subject: "subject", grade: "class", class: "class", set: "set",
  maxmark: "marks", maxmarks: "marks", marks: "marks", totalmarks: "marks",
  time: "time", duration: "time", date: "date",
};
const text = (node?: HeaderNode): string => node?.text ?? (node?.content ?? []).map(text).join(" ").trim();

export function schoolNameOf(node: HeaderNode): string {
  return text(node.content?.find(child => child.type === "heading" && child.attrs?.level === 1));
}

export function isGenericPaperTitle(node: HeaderNode): boolean {
  return node.type === "heading" && node.attrs?.level === 2 &&
    /^(?:(?:CBSE|ICSE)\s*[-–—:]?\s*)?Question Paper$/i.test(text(node).trim());
}

/** Only the old label/value grid is metadata; other header tables remain content. */
export function legacyHeaderTableIndex(node: HeaderNode): number {
  return (node.content ?? []).findIndex(child => {
    const rows = child.content ?? [];
    const labels = rows[0]?.content ?? [];
    return child.type === "table" && rows.length === 2 && labels.length > 0 &&
      labels.every(cell => cell.type === "tableHeader") &&
      labels.some(cell => aliases[text(cell).toLowerCase().replace(/[^a-z]/g, "")]);
  });
}

export function readHeaderDetails(node: HeaderNode): HeaderDetail[] {
  if (Array.isArray(node.attrs?.details)) {
    return node.attrs.details.filter((field): field is HeaderDetail =>
      Boolean(field && typeof field.id === "string" && typeof field.label === "string" && typeof field.value === "string"));
  }
  const table = node.content?.[legacyHeaderTableIndex(node)];
  const labels = table?.content?.[0]?.content ?? [];
  const values = table?.content?.[1]?.content ?? [];
  return labels.map((cell, index) => {
    const label = text(cell);
    const id = aliases[label.toLowerCase().replace(/[^a-z]/g, "")] ?? `custom-${index}`;
    return { id, label: HEADER_FIELDS.find(field => field.id === id)?.label ?? label, value: text(values[index]) };
  });
}

export function visibleHeaderDetails(node: HeaderNode): HeaderDetail[] {
  const hidden = Array.isArray(node.attrs?.hiddenFields) ? node.attrs.hiddenFields : [];
  return readHeaderDetails(node).filter(field => !hidden.includes(field.id) && field.value.trim() &&
    !/^[_\s—-]+$/.test(field.value) && !(field.id === "date" && node.attrs?.showDate));
}

export function editableHeaderDetails(node: HeaderNode): HeaderDetail[] {
  const existing = readHeaderDetails(node);
  return [...HEADER_FIELDS.map(field => existing.find(item => item.id === field.id) ?? { ...field, value: "" }),
    ...existing.filter(field => !HEADER_FIELDS.some(item => item.id === field.id))];
}
