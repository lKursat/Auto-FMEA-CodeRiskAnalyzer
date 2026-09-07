"use strict";
/**
 * dashboardPanel.ts — Auto-FMEA Risk Dashboard Webview Panel
 * ===========================================================
 * Manages a VS Code WebviewPanel that shows the full project-wide
 * risk dashboard, 5x5 risk matrix, and export functionality.
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
exports.DashboardPanel = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
class DashboardPanel {
    constructor(panel, extensionUri) {
        this._disposables = [];
        this._panel = panel;
        this._extensionUri = extensionUri;
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
        this._panel.webview.onDidReceiveMessage((message) => this._handleMessage(message), null, this._disposables);
    }
    static createOrShow(extensionUri) {
        const column = vscode.ViewColumn.Beside;
        if (DashboardPanel.currentPanel) {
            DashboardPanel.currentPanel._panel.reveal(column);
            return;
        }
        const panel = vscode.window.createWebviewPanel('autofmeaDashboard', 'Auto-FMEA Risk Dashboard', column, {
            enableScripts: true,
            retainContextWhenHidden: true,
            localResourceRoots: [
                vscode.Uri.joinPath(extensionUri, 'webview'),
            ],
        });
        DashboardPanel.currentPanel = new DashboardPanel(panel, extensionUri);
        if (DashboardPanel.lastResult) {
            DashboardPanel.currentPanel._render(DashboardPanel.lastResult);
        }
        else {
            DashboardPanel.currentPanel._renderEmpty();
        }
    }
    static update(result) {
        DashboardPanel.lastResult = result;
        if (DashboardPanel.currentPanel) {
            DashboardPanel.currentPanel._render(result);
        }
    }
    static clear() {
        DashboardPanel.lastResult = undefined;
        if (DashboardPanel.currentPanel) {
            DashboardPanel.currentPanel._renderEmpty();
        }
    }
    static exportReport() {
        if (!DashboardPanel.lastResult) {
            vscode.window.showWarningMessage('Auto-FMEA: No analysis data to export. Save a file first.');
            return;
        }
        const result = DashboardPanel.lastResult;
        const summary = result.project_summary;
        const now = new Date().toISOString();
        const lines = [
            '# Auto-FMEA Risk Report',
            '',
            `**Generated:** ${now}`,
            `**Project Health Score:** ${summary.project_health_score}%`,
            `**Total Classes Analyzed:** ${summary.total_classes_analyzed}`,
            `**Average RPN:** ${summary.average_rpn}`,
            '',
            '## Risk Summary',
            '',
            `| Risk Level | Count |`,
            `|------------|-------|`,
            `| 🔴 CRITICAL | ${summary.critical_count} |`,
            `| 🟠 HIGH     | ${summary.high_count} |`,
            `| 🟡 MEDIUM   | ${summary.medium_count} |`,
            `| 🟢 LOW      | ${summary.low_count} |`,
            '',
            '## All Classes',
            '',
            '| Class Name | File | Severity | Occurrence | Detection | RPN | Risk Level |',
            '|-----------|------|----------|------------|-----------|-----|------------|',
            ...summary.all_classes.map(c => `| ${c.name} | ${path.basename(c.file)} | ${c.severity} | ${c.occurrence} | ${c.detection} | ${c.rpn} | ${c.risk_level} |`),
            '',
            '## Top Risks',
            '',
            ...summary.top_risks.map((name, i) => `${i + 1}. **${name}**`),
            '',
            '## Last Analyzed File',
            '',
            `**File:** ${result.file}`,
            `**Language:** ${result.language}`,
            '',
            '### Class Details',
        ];
        for (const cls of result.classes) {
            lines.push('', `#### ${cls.name}`, '');
            lines.push(`- **Risk Level:** ${cls.risk_level}`);
            lines.push(`- **RPN:** ${cls.rpn} (S=${cls.severity} × O=${cls.occurrence} × D=${cls.detection})`);
            lines.push(`- **Cyclomatic Complexity:** ${cls.cyclomatic_complexity}`);
            lines.push(`- **Fan-In:** ${cls.fan_in} | **Fan-Out:** ${cls.fan_out}`);
            if (cls.affected_classes.length > 0) {
                lines.push(`- **Affected Classes:** ${cls.affected_classes.join(', ')}`);
            }
            lines.push('', '**Recommendations:**', '');
            cls.recommendations.forEach(r => lines.push(`- ${r}`));
        }
        const reportContent = lines.join('\n');
        vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file('auto-fmea-report.md'),
            filters: { Markdown: ['md'], 'Text File': ['txt'] },
        }).then((uri) => {
            if (uri) {
                fs.writeFileSync(uri.fsPath, reportContent, 'utf-8');
                vscode.window.showInformationMessage(`Auto-FMEA: Report exported to ${path.basename(uri.fsPath)}`, 'Open File').then(choice => {
                    if (choice === 'Open File') {
                        vscode.commands.executeCommand('vscode.open', uri);
                    }
                });
            }
        });
    }
    // -------------------------------------------------------------------------
    // Message handling
    // -------------------------------------------------------------------------
    _handleMessage(message) {
        switch (message.command) {
            case 'exportReport':
                DashboardPanel.exportReport();
                break;
            case 'analyzeNow':
                vscode.commands.executeCommand('autofmea.analyzeNow');
                break;
            case 'clearHistory':
                vscode.commands.executeCommand('autofmea.clearHistory');
                break;
        }
    }
    // -------------------------------------------------------------------------
    // Rendering
    // -------------------------------------------------------------------------
    _render(result) {
        this._panel.webview.html = this._buildHtml(result);
    }
    _renderEmpty() {
        this._panel.webview.html = this._buildEmptyHtml();
    }
    _buildHtml(result) {
        const summary = result.project_summary;
        const classes = result.classes;
        const all = summary.all_classes;
        // Read dashboard HTML template
        const htmlPath = path.join(this._extensionUri.fsPath, 'webview', 'dashboard.html');
        let html = '';
        try {
            html = fs.readFileSync(htmlPath, 'utf-8');
        }
        catch {
            html = '<html><body><p>Dashboard template not found.</p></body></html>';
        }
        // Inject analysis data as a JSON script tag
        const history = result.history || [];
        const dataScript = `<script id="fmea-data" type="application/json">${JSON.stringify({ result, summary, all, classes, history }, null, 0)}</script>`;
        return html.replace('<!-- FMEA_DATA_INJECTION -->', dataScript);
    }
    _buildEmptyHtml() {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Auto-FMEA Dashboard</title>
<style>
  body { background: #0d1117; color: #8b949e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column; }
  .icon { font-size: 64px; margin-bottom: 24px; }
  h2 { color: #c9d1d9; margin: 0 0 12px; }
  p { margin: 0 0 24px; text-align: center; max-width: 320px; line-height: 1.6; }
  button { background: #238636; color: #fff; border: none; padding: 10px 20px;
           border-radius: 6px; cursor: pointer; font-size: 14px; }
  button:hover { background: #2ea043; }
</style>
</head>
<body>
<div class="icon">🛡️</div>
<h2>Auto-FMEA Risk Dashboard</h2>
<p>Save a Python, Java, or C# file to trigger analysis and see the risk dashboard here.</p>
<button onclick="acquireVsCodeApi().postMessage({command:'analyzeNow'})">Analyze Current File</button>
</body>
</html>`;
    }
    dispose() {
        DashboardPanel.currentPanel = undefined;
        this._panel.dispose();
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d) {
                d.dispose();
            }
        }
    }
}
exports.DashboardPanel = DashboardPanel;
//# sourceMappingURL=dashboardPanel.js.map