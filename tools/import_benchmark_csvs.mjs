import fs from "node:fs/promises";
import { pathToFileURL } from "node:url";

const artifactPath = "C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";
const { FileBlob, SpreadsheetFile, Workbook } = await import(pathToFileURL(artifactPath).href);

const input = "C:/Users/Admin/Downloads/QuocAn_RAG_Benchmark_24Q.xlsx";
const csvDir = "C:/Users/Admin/Desktop/FA2026/enterprise-knowledge-ai-agent/artifacts/benchmark/exports";
const output = "C:/Users/Admin/Desktop/FA2026/enterprise-knowledge-ai-agent/artifacts/benchmark/QuocAn_RAG_Benchmark_24Q_completed.xlsx";

const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));

async function csvValues(name) {
  const text = await fs.readFile(`${csvDir}/${name}`, "utf8");
  const csvWb = await Workbook.fromCSV(text, { sheetName: "CSV" });
  return csvWb.worksheets.getItem("CSV").getUsedRange().values;
}

function replaceContents(sheet, values) {
  const old = sheet.getUsedRange();
  old.clear({ applyTo: "contents" });
  sheet.getRangeByIndexes(0, 0, values.length, values[0].length).values = values;
}

replaceContents(wb.worksheets.getItem("24 Questions"), await csvValues("benchmark_24_questions.csv"));
replaceContents(wb.worksheets.getItem("Gold Evidence"), await csvValues("benchmark_27_gold_chunks.csv"));
replaceContents(wb.worksheets.getItem("Model Answers"), await csvValues("benchmark_72_model_answers.csv"));

let contexts = wb.worksheets.getItemOrNullObject?.("Retrieved Contexts");
if (!contexts || contexts.isNullObject) contexts = wb.worksheets.add("Retrieved Contexts");
replaceContents(contexts, await csvValues("benchmark_retrieved_contexts.csv"));

wb.recalculate();
await fs.mkdir("C:/Users/Admin/Desktop/FA2026/enterprise-knowledge-ai-agent/artifacts/benchmark", { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(output);

const check = await SpreadsheetFile.importXlsx(await FileBlob.load(output));
const report = check.worksheets.items.map(s => ({ name: s.name, range: s.getUsedRange().address, rows: s.getUsedRange().values.length }));
console.log(JSON.stringify(report));
