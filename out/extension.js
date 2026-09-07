"use strict";
/**
 * extension.ts — Auto-FMEA VS Code Extension Entry Point
 * =========================================================
 * Activates on startup. Listens for file saves on Python/Java/C# files,
 * spawns the Python analysis engine as a subprocess, parses the JSON output,
 * and drives diagnostics, decorations, status bar, and the webview dashboard.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const cp = __importStar(require("child_process"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const dashboardPanel_1 = require("./dashboardPanel");
// ---------------------------------------------------------------------------
// Extension state
// ---------------------------------------------------------------------------
let statusBarItem;
let diagnosticCollection;
let outputChannel;
let analyzeTimeout;
// Map from file URI string → last analysis result (for decoration refresh)
const analysisCache = new Map();
// ---------------------------------------------------------------------------
// Language detection
// ---------------------------------------------------------------------------
const SUPPORTED_LANGUAGES = {
    python: 'python',
    java: 'java',
    csharp: 'csharp',
};
function getLanguage(doc) {
    return SUPPORTED_LANGUAGES[doc.languageId] ?? null;
}
// ---------------------------------------------------------------------------
// Engine invocation
// ---------------------------------------------------------------------------
/**
 * Spawn the Python analysis engine and return the parsed JSON result.
 * Always resolves (never rejects) — errors are returned as AnalysisResult
 * with an "error" field.
 */
function runAnalysisEngine(filePath, language, projectRoot, pythonPath) {
    return new Promise((resolve) => {
        const enginePath = path.join(__dirname, '..', 'engine', 'analyzer.py');
        // Verify engine exists
        if (!fs.existsSync(enginePath)) {
            resolve({
                error: `Engine not found at: ${enginePath}`,
                file: filePath,
                language,
                classes: [],
                project_summary: {
                    total_classes_analyzed: 0,
                    average_rpn: 0,
                    project_health_score: 100,
                    critical_count: 0,
                    high_count: 0,
                    medium_count: 0,
                    low_count: 0,
                    top_risks: [],
                    all_classes: [],
                },
            });
            return;
        }
        const args = [
            enginePath,
            '--file', filePath,
            '--language', language,
            '--project-root', projectRoot,
        ];
        outputChannel.appendLine(`[Auto-FMEA] Running: ${pythonPath} ${args.join(' ')}`);
        const startTime = Date.now();
        let stdout = '';
        let stderr = '';
        const proc = cp.spawn(pythonPath, args, {
            cwd: projectRoot,
            timeout: 30000, // 30-second hard timeout
        });
        proc.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
        proc.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        proc.on('close', (code) => {
            const elapsed = Date.now() - startTime;
            outputChannel.appendLine(`[Auto-FMEA] Engine exited (code=${code}) in ${elapsed}ms`);
            if (stderr) {
                outputChannel.appendLine(`[Auto-FMEA] STDERR: ${stderr}`);
            }
            try {
                const result = JSON.parse(stdout);
                resolve(result);
            }
            catch {
                resolve({
                    error: `Failed to parse engine output: ${stdout.substring(0, 500)}`,
                    file: filePath,
                    language,
                    classes: [],
                    project_summary: {
                        total_classes_analyzed: 0,
                        average_rpn: 0,
                        project_health_score: 100,
                        critical_count: 0,
                        high_count: 0,
                        medium_count: 0,
                        low_count: 0,
                        top_risks: [],
                        all_classes: [],
                    },
                });
            }
        });
        proc.on('error', (err) => {
            resolve({
                error: `Failed to start engine: ${err.message}. Check autofmea.pythonPath setting.`,
                file: filePath,
                language,
                classes: [],
                project_summary: {
                    total_classes_analyzed: 0,
                    average_rpn: 0,
                    project_health_score: 100,
                    critical_count: 0,
                    high_count: 0,
                    medium_count: 0,
                    low_count: 0,
                    top_risks: [],
                    all_classes: [],
                },
            });
        });
    });
}
// ---------------------------------------------------------------------------
// Diagnostics
// ---------------------------------------------------------------------------
const RISK_TO_SEVERITY = {
    CRITICAL: vscode.DiagnosticSeverity.Error,
    HIGH: vscode.DiagnosticSeverity.Error,
    MEDIUM: vscode.DiagnosticSeverity.Warning,
    LOW: vscode.DiagnosticSeverity.Information,
};
function updateDiagnostics(doc, result) {
    const diags = [];
    for (const cls of result.classes) {
        // Main RPN diagnostic on the class declaration line
        const startLine = Math.max(0, cls.line_start - 1);
        const lineText = doc.lineAt(startLine).text;
        const range = new vscode.Range(startLine, 0, startLine, lineText.length);
        const severity = RISK_TO_SEVERITY[cls.risk_level] ?? vscode.DiagnosticSeverity.Information;
        const mainMsg = [
            `[Auto-FMEA] ${cls.name} — ${cls.risk_level} Risk`,
            `RPN: ${cls.rpn} (S=${cls.severity} × O=${cls.occurrence} × D=${cls.detection})`,
            `CC: ${cls.cyclomatic_complexity} | Fan-In: ${cls.fan_in} | Fan-Out: ${cls.fan_out}`,
        ].join(' | ');
        const diag = new vscode.Diagnostic(range, mainMsg, severity);
        diag.source = 'Auto-FMEA';
        diag.code = cls.risk_level;
        diags.push(diag);
        // Individual recommendation diagnostics (only for CRITICAL/HIGH)
        if (cls.risk_level === 'CRITICAL' || cls.risk_level === 'HIGH') {
            for (const rec of cls.recommendations.slice(0, 3)) {
                const recDiag = new vscode.Diagnostic(range, rec, vscode.DiagnosticSeverity.Information);
                recDiag.source = 'Auto-FMEA';
                recDiag.code = 'recommendation';
                diags.push(recDiag);
            }
        }
    }
    diagnosticCollection.set(doc.uri, diags);
}
// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------
function updateStatusBar(result) {
    const summary = result.project_summary;
    const health = summary.project_health_score;
    let icon = '$(shield)';
    let color;
    if (summary.critical_count > 0) {
        icon = '$(error)';
        color = 'statusBarItem.errorBackground';
    }
    else if (summary.high_count > 0) {
        icon = '$(warning)';
        color = 'statusBarItem.warningBackground';
    }
    else if (summary.medium_count > 0) {
        icon = '$(info)';
    }
    statusBarItem.text = `${icon} Auto-FMEA: Health ${health}% | C:${summary.critical_count} H:${summary.high_count} M:${summary.medium_count} L:${summary.low_count}`;
    statusBarItem.tooltip = `Project Health Score: ${health}%\nClick to open Risk Dashboard`;
    statusBarItem.backgroundColor = color
        ? new vscode.ThemeColor(color)
        : undefined;
    statusBarItem.show();
}
// ---------------------------------------------------------------------------
// Main analysis trigger
// ---------------------------------------------------------------------------
async function analyzeDocument(doc) {
    const language = getLanguage(doc);
    if (!language) {
        return;
    }
    const config = vscode.workspace.getConfiguration('autofmea');
    const pythonPath = config.get('pythonPath', 'python');
    // ---------------------------------------------------------------
    // Resolve project root (3-tier fallback):
    //   1. The workspace folder that contains this document
    //   2. The first workspace folder (multi-root workspaces)
    //   3. The file's parent directory (standalone file — warning)
    // ---------------------------------------------------------------
    const docWorkspaceFolder = vscode.workspace.getWorkspaceFolder(doc.uri);
    let projectRoot;
    if (docWorkspaceFolder) {
        projectRoot = docWorkspaceFolder.uri.fsPath;
    }
    else if (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
        projectRoot = vscode.workspace.workspaceFolders[0].uri.fsPath;
        outputChannel.appendLine(`[Auto-FMEA] WARNING: File "${doc.uri.fsPath}" is outside the workspace. ` +
            `Using workspace root "${projectRoot}" for dependency scanning.`);
    }
    else {
        projectRoot = path.dirname(doc.uri.fsPath);
        outputChannel.appendLine(`[Auto-FMEA] WARNING: No workspace folder open. ` +
            `Fan-in analysis will be limited to "${projectRoot}". ` +
            `Open a folder (File > Open Folder) for full cross-file dependency analysis.`);
    }
    outputChannel.appendLine(`[Auto-FMEA] project-root resolved to: "${projectRoot}" ` +
        `(file: "${doc.uri.fsPath}")`);
    statusBarItem.text = '$(sync~spin) Auto-FMEA: Analyzing…';
    statusBarItem.tooltip = 'Analysis in progress…';
    statusBarItem.show();
    const result = await runAnalysisEngine(doc.uri.fsPath, language, projectRoot, pythonPath);
    if (result.error) {
        outputChannel.appendLine(`[Auto-FMEA] ERROR: ${result.error}`);
        vscode.window.showWarningMessage(`Auto-FMEA: Analysis error — ${result.error}`);
        statusBarItem.text = '$(error) Auto-FMEA: Error';
        statusBarItem.tooltip = result.error;
        return;
    }
    // Cache and update UI
    analysisCache.set(doc.uri.toString(), result);
    updateDiagnostics(doc, result);
    updateStatusBar(result);
    dashboardPanel_1.DashboardPanel.update(result);
    // Show a brief summary notification for high/critical findings
    const criticalCount = result.classes.filter(c => c.risk_level === 'CRITICAL').length;
    if (criticalCount > 0) {
        const msg = `Auto-FMEA: ${criticalCount} CRITICAL risk class(es) detected in ${path.basename(doc.uri.fsPath)}.`;
        vscode.window.showErrorMessage(msg, 'Open Dashboard').then(choice => {
            if (choice === 'Open Dashboard') {
                vscode.commands.executeCommand('autofmea.showDashboard');
            }
        });
    }
}
// ---------------------------------------------------------------------------
// Activation
// ---------------------------------------------------------------------------
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('Auto-FMEA');
    outputChannel.appendLine('[Auto-FMEA] Extension activating…');
    // Diagnostic collection
    diagnosticCollection = vscode.languages.createDiagnosticCollection('auto-fmea');
    context.subscriptions.push(diagnosticCollection);
    // Status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'autofmea.showDashboard';
    statusBarItem.text = '$(shield) Auto-FMEA: Ready';
    statusBarItem.tooltip = 'Click to open Auto-FMEA Risk Dashboard';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
    // Register commands
    context.subscriptions.push(vscode.commands.registerCommand('autofmea.showDashboard', () => {
        dashboardPanel_1.DashboardPanel.createOrShow(context.extensionUri);
        // Send cached data if available
        const activeDoc = vscode.window.activeTextEditor?.document;
        if (activeDoc) {
            const cached = analysisCache.get(activeDoc.uri.toString());
            if (cached) {
                dashboardPanel_1.DashboardPanel.update(cached);
            }
        }
    }), vscode.commands.registerCommand('autofmea.analyzeNow', () => {
        const doc = vscode.window.activeTextEditor?.document;
        if (!doc) {
            vscode.window.showWarningMessage('Auto-FMEA: No active editor.');
            return;
        }
        analyzeDocument(doc);
    }), vscode.commands.registerCommand('autofmea.exportReport', () => {
        dashboardPanel_1.DashboardPanel.exportReport();
    }), vscode.commands.registerCommand('autofmea.clearHistory', () => {
        const projectRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (projectRoot) {
            const historyFile = path.join(__dirname, '..', 'engine', '.fmea_history.json');
            try {
                if (fs.existsSync(historyFile)) {
                    fs.unlinkSync(historyFile);
                }
                diagnosticCollection.clear();
                analysisCache.clear();
                dashboardPanel_1.DashboardPanel.clear();
                vscode.window.showInformationMessage('Auto-FMEA: Analysis history cleared.');
            }
            catch {
                vscode.window.showWarningMessage('Auto-FMEA: Failed to clear history file.');
            }
        }
    }));
    // File save listener (debounced 500ms)
    context.subscriptions.push(vscode.workspace.onDidSaveTextDocument((doc) => {
        const config = vscode.workspace.getConfiguration('autofmea');
        if (!config.get('analyzeOnSave', true)) {
            return;
        }
        if (!getLanguage(doc)) {
            return;
        }
        if (analyzeTimeout) {
            clearTimeout(analyzeTimeout);
        }
        analyzeTimeout = setTimeout(() => { analyzeDocument(doc); }, 500);
    }));
    // Re-apply decorations when switching editors
    context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor((editor) => {
        if (!editor) {
            return;
        }
        const cached = analysisCache.get(editor.document.uri.toString());
        if (cached) {
            updateStatusBar(cached);
        }
    }));
    // Analyze the currently active file on activation
    const activeDoc = vscode.window.activeTextEditor?.document;
    if (activeDoc && getLanguage(activeDoc)) {
        setTimeout(() => analyzeDocument(activeDoc), 1500);
    }
    outputChannel.appendLine('[Auto-FMEA] Extension activated successfully.');
}
function deactivate() {
    if (analyzeTimeout) {
        clearTimeout(analyzeTimeout);
    }
    diagnosticCollection?.dispose();
    statusBarItem?.dispose();
    outputChannel?.appendLine('[Auto-FMEA] Extension deactivated.');
}
//# sourceMappingURL=extension.js.map