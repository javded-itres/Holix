/** Monaco workers + completion providers for Holix Studio. */

const MONACO_VERSION = "0.52.2";
const MONACO_BASE = `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO_VERSION}/min/`;

const WORKER_PATHS = {
  json: "vs/language/json/jsonWorker.js",
  css: "vs/language/css/cssWorker.js",
  scss: "vs/language/css/cssWorker.js",
  less: "vs/language/css/cssWorker.js",
  html: "vs/language/html/htmlWorker.js",
  handlebars: "vs/language/html/htmlWorker.js",
  razor: "vs/language/html/htmlWorker.js",
  typescript: "vs/language/typescript/tsWorker.js",
  javascript: "vs/language/typescript/tsWorker.js",
};

function workerBlobUrl(relPath) {
  const workerUrl = `${MONACO_BASE}${relPath}`;
  const code = [
    `self.MonacoEnvironment = { baseUrl: ${JSON.stringify(MONACO_BASE)} };`,
    `importScripts(${JSON.stringify(workerUrl)});`,
  ].join("");
  return URL.createObjectURL(new Blob([code], { type: "text/javascript" }));
}

export function setupMonacoEnvironment() {
  if (globalThis.MonacoEnvironment?.getWorkerUrl) return;
  globalThis.MonacoEnvironment = {
    getWorkerUrl(_moduleId, label) {
      const rel = WORKER_PATHS[label] || "vs/base/worker/workerMain.js";
      return workerBlobUrl(rel);
    },
  };
}

export const EDITOR_SUGGEST_OPTIONS = {
  quickSuggestions: { other: true, comments: false, strings: true },
  suggestOnTriggerCharacters: true,
  wordBasedSuggestions: "matchingDocuments",
  tabCompletion: "on",
  parameterHints: { enabled: true },
  acceptSuggestionOnEnter: "on",
  snippetSuggestions: "top",
};

function snippet(label, insertText, detail) {
  return { label, insertText, detail };
}

const SNIPPET_CATALOG = {
  python: [
    snippet("def", "def ${1:name}(${2:args}):\n\t${3:pass}", "Function"),
    snippet("class", "class ${1:Name}:\n\tdef __init__(self${2:, args}):\n\t\t${3:pass}", "Class"),
    snippet("if", "if ${1:condition}:\n\t${2:pass}", "If"),
    snippet("elif", "elif ${1:condition}:\n\t${2:pass}", "Elif"),
    snippet("else", "else:\n\t${1:pass}", "Else"),
    snippet("for", "for ${1:item} in ${2:items}:\n\t${3:pass}", "For loop"),
    snippet("while", "while ${1:condition}:\n\t${2:pass}", "While loop"),
    snippet("try", "try:\n\t${1:pass}\nexcept ${2:Exception} as ${3:e}:\n\t${4:pass}", "Try/except"),
    snippet("with", "with ${1:expr} as ${2:var}:\n\t${3:pass}", "Context manager"),
    snippet("import", "import ${1:module}", "Import"),
    snippet("from", "from ${1:module} import ${2:name}", "From import"),
    snippet("async def", "async def ${1:name}(${2:args}):\n\t${3:pass}", "Async function"),
  ],
  shell: [
    snippet("if", "if [ ${1:condition} ]; then\n\t${2:command}\nfi", "If"),
    snippet("for", "for ${1:item} in ${2:items}; do\n\t${3:command}\n done", "For loop"),
    snippet("function", "${1:name}() {\n\t${2:command}\n}", "Function"),
  ],
  yaml: [
    snippet("list", "- ${1:item}\n- ${2:item}", "YAML list"),
    snippet("map", "${1:key}: ${2:value}", "Key/value"),
  ],
  markdown: [
    snippet("heading", "## ${1:Title}", "Heading"),
    snippet("code", "```${1:lang}\n${2:code}\n```", "Code fence"),
    snippet("link", "[${1:text}](${2:url})", "Link"),
  ],
  rust: [
    snippet("fn", "fn ${1:name}(${2:args}) -> ${3:()} {\n\t${4:todo!()}\n}", "Function"),
    snippet("struct", "struct ${1:Name} {\n\t${2:field}: ${3:type},\n}", "Struct"),
    snippet("impl", "impl ${1:Type} {\n\t${2:}\n}", "Impl block"),
  ],
  go: [
    snippet("func", "func ${1:name}(${2:args}) ${3:error} {\n\t${4:return nil}\n}", "Function"),
    snippet("if", "if ${1:err} != nil {\n\t${2:return err}\n}", "Error check"),
    snippet("struct", "type ${1:Name} struct {\n\t${2:Field} ${3:type}\n}", "Struct"),
  ],
  sql: [
    snippet("select", "SELECT ${1:columns}\nFROM ${2:table}\nWHERE ${3:condition};", "SELECT"),
    snippet("insert", "INSERT INTO ${1:table} (${2:columns})\nVALUES (${3:values});", "INSERT"),
  ],
  java: [
    snippet("class", "public class ${1:Name} {\n\t${2:}\n}", "Class"),
    snippet("method", "public ${1:void} ${2:name}(${3:args}) {\n\t${4:}\n}", "Method"),
  ],
  ruby: [
    snippet("def", "def ${1:name}(${2:args})\n\t${3:}\nend", "Method"),
    snippet("class", "class ${1:Name}\n\t${2:}\nend", "Class"),
  ],
  php: [
    snippet("function", "function ${1:name}(${2:args}) {\n\t${3:}\n}", "Function"),
    snippet("class", "class ${1:Name} {\n\t${2:}\n}", "Class"),
  ],
};

let languagesConfigured = false;

export function configureMonacoLanguages(monaco) {
  if (languagesConfigured) return;
  languagesConfigured = true;

  const ts = monaco.languages.typescript;
  const compilerOptions = {
    target: ts.ScriptTarget.ES2020,
    allowNonTsExtensions: true,
    moduleResolution: ts.ModuleResolutionKind.NodeJs,
    module: ts.ModuleKind.ESModule,
    noEmit: true,
    esModuleInterop: true,
    allowJs: true,
    jsx: ts.JsxEmit.React,
    strict: false,
  };
  ts.typescriptDefaults.setCompilerOptions(compilerOptions);
  ts.javascriptDefaults.setCompilerOptions(compilerOptions);
  ts.typescriptDefaults.setDiagnosticsOptions({
    noSemanticValidation: false,
    noSyntaxValidation: false,
  });
  ts.javascriptDefaults.setDiagnosticsOptions({
    noSemanticValidation: false,
    noSyntaxValidation: false,
  });

  const kind = monaco.languages.CompletionItemKind.Snippet;
  const rule = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;

  for (const [languageId, items] of Object.entries(SNIPPET_CATALOG)) {
    monaco.languages.registerCompletionItemProvider(languageId, {
      triggerCharacters: [".", " "],
      provideCompletionItems(model, position) {
        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };
        return {
          suggestions: items.map((item) => ({
            label: item.label,
            kind,
            detail: item.detail,
            insertText: item.insertText,
            insertTextRules: rule,
            range,
          })),
        };
      },
    });
  }
}