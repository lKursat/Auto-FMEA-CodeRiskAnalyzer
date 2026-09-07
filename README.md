# Auto-FMEA

Real-time, metric-based risk analysis for software projects — triggered automatically every time you save a file in VS Code.

## What it does

Auto-FMEA analyzes your source code on every file save and computes a Risk Priority Number (RPN) for each class using three objective metrics: cyclomatic complexity, dependency impact radius (fan-in/fan-out), and test coverage detection. Results appear instantly as inline diagnostics and in a dedicated dashboard panel.

## Supported languages

- Python (.py) — powered by `ast` and `radon`
- Java (.java) — powered by `javalang`
- C# (.cs) — powered by custom static analysis

## How it works

Auto-FMEA adapts the FMEA (Failure Mode and Effects Analysis) methodology — a standard used in aerospace, automotive, and safety-critical engineering — to software development:

| Parameter | How it is measured |
|---|---|
| Severity | Fan-in: how many other classes depend on this class |
| Occurrence | Cyclomatic complexity of the class |
| Detection | Presence of a corresponding test file |
| **RPN** | **Severity x Occurrence x Detection** |

| RPN Range | Risk Level |
|---|---|
| >= 200 | Critical |
| >= 100 | High |
| >= 50 | Medium |
| < 50 | Low |

## Features

- On-save trigger: analysis runs automatically when you save a .py, .java, or .cs file
- Dependency analysis: detects which classes depend on the modified class, both within the same file and across the project
- Duplicate class detection: flags classes with the same name defined in multiple locations
- Actionable recommendations: at least 3 specific, metric-referenced recommendations per class
- Dashboard panel: risk table, 5x5 risk matrix, project health score, and top risks — accessible via Ctrl+Shift+P > "Auto-FMEA: Show Dashboard"
- Report export: one-click markdown report generation

## Requirements

- VS Code 1.85 or higher
- Python 3.8 or higher
- Node.js 18 or higher

Install the required Python libraries once:

```
pip install radon javalang gitpython
```

## Installation

1. Download the .vsix file from the Releases page
2. Open VS Code
3. Press Ctrl+Shift+P and run "Extensions: Install from VSIX"
4. Select the downloaded .vsix file
5. Reload VS Code

## Usage

1. Open any Python, Java, or C# project as a folder in VS Code
2. Save any source file (Ctrl+S)
3. Auto-FMEA analyzes the file automatically
4. View results in the status bar (bottom right) or open the dashboard with Ctrl+Shift+P > "Auto-FMEA: Show Dashboard"

## License

MIT
