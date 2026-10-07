#!/usr/bin/env node
// Run from frontend: node scripts/test-composite-question-frame.mjs
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createJiti } from "jiti";
import { Schema } from "@tiptap/pm/model";
import { EditorState } from "@tiptap/pm/state";

const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(here, { alias: { "@": path.resolve(here, "..") } });
const { CompositeQuestionFrame } = await jiti.import(path.resolve(here, "../components/editor/extensions/composite-question-frame.ts"));
const schema = new Schema({ nodes: {
  doc: { content: "page+" },
  page: { content: "block+" },
  text: { group: "inline" },
  paragraph: { group: "block", content: "inline*" },
  questionBlock: { group: "block", content: "paragraph+", attrs: { questionType: { default: "SHORT" } } },
  questionGroupBlock: { group: "block", content: "(questionBlock|paragraph)+" },
  sectionBlock: { group: "block", content: "inline*" },
  instructionBlock: { group: "block", content: "paragraph+" },
} });
const para = (text) => ({ type: "paragraph", content: [{ type: "text", text }] });
const question = (type, text) => ({ type: "questionBlock", attrs: { questionType: type }, content: [para(text)] });
const page = (...content) => ({ type: "page", content });
const plugins = CompositeQuestionFrame.config.addProseMirrorPlugins();
const state = EditorState.create({ schema, plugins, doc: schema.nodeFromJSON({ type: "doc", content: [
  page(para("Standalone note"), question("CASE_STUDY", "Read the case"), para("Case passage")),
  page(para("(i) First part"), para("(ii) Last part"), question("MCQ", "Ordinary question"), para("Standalone prose"),
    { type: "sectionBlock", content: [{ type: "text", text: "Next section" }] },
    { type: "questionGroupBlock", content: [question("CASE_STUDY_MATHS", "First branch"), para("Branch one body"), question("DATA_INTERPRETATION", "Second branch"), para("Branch two body")] }),
] }) });
const decorations = plugins[0].props.decorations(state);
const framed = decorations.find();
const texts = framed.map((d) => state.doc.nodeAt(d.from).textContent);
assert.equal(framed.length, 8);
assert.ok(!texts.includes("Standalone note") && !texts.includes("Standalone prose") && !texts.includes("Ordinary question"));
const frame = (text) => framed.find((d) => state.doc.nodeAt(d.from).textContent === text).type.attrs.class;
assert.match(frame("Case passage"), /composite-fragment-end/);
assert.match(frame("(i) First part"), /composite-fragment-start/);
assert.match(frame("(ii) Last part"), /composite-fragment-end/);
assert.match(frame("Branch one body"), /composite-fragment-end/);
assert.match(frame("Branch two body"), /composite-fragment-end/);
assert.equal(plugins[0].props.decorations(state.apply(state.tr.setSelection(state.selection))), decorations, "selection-only transactions reuse cached decorations");
const passage = framed.find((d) => state.doc.nodeAt(d.from).textContent === "Case passage");
const edited = state.apply(state.tr.insertText(" edited", passage.to - 1));
assert.ok(plugins[0].props.decorations(edited).find().some((d) => edited.doc.nodeAt(d.from).textContent === "Case passage edited"));
console.log("PASS: saved composite questions stay framed across pages, OR branches, structural boundaries, edits and cached selection updates.");
