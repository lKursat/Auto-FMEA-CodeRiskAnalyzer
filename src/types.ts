/**
 * types.ts — Shared TypeScript Interfaces
 * =========================================
 * Mirror the JSON schema returned by the Python analysis engine.
 */

export interface ClassInfo {
    name: string;
    line_start: number;
    line_end: number;
    cyclomatic_complexity: number;
    fan_in: number;
    fan_out: number;
    affected_classes: string[];
    test_file_found: boolean;
    severity: number;
    occurrence: number;
    detection: number;
    rpn: number;
    risk_level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
    recommendations: string[];
    last_analyzed: string;
    git_churn?: number;
    churn_bonus?: number;
    git_available?: boolean;
}

export interface ProjectSummary {
    total_classes_analyzed: number;
    average_rpn: number;
    project_health_score: number;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    top_risks: string[];
    all_classes: AllClassEntry[];
}

export interface AllClassEntry {
    name: string;
    file: string;
    severity: number;
    occurrence: number;
    detection: number;
    rpn: number;
    risk_level: string;
    last_analyzed: string;
}

export interface AnalysisResult {
    file: string;
    language: string;
    classes: ClassInfo[];
    project_summary: ProjectSummary;
    history?: HistoryEntry[];
    error?: string;
}

export interface HistoryEntry {
    timestamp: string;
    file: string;
    classes: {
        name: string;
        rpn: number;
        severity: number;
        occurrence: number;
        detection: number;
        risk_level: string;
    }[];
}
