import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';

export interface BenchmarkFile {
    path: string;
    type: string;
}

export interface BenchmarkExpected {
    answer_contains: string[];
    source_contains: string[];
}

export interface BenchmarkCase {
    id: string;
    title: string;
    files: BenchmarkFile[];
    question: string;
    expected: BenchmarkExpected;
    tags?: string[];
}

export interface BenchmarkConfig {
    version: number;
    name: string;
    description?: string;
    defaults: {
        timeout_ms: number;
        require_citation: boolean;
        language: string;
    };
    cases: BenchmarkCase[];
}

export function loadBenchmark(filePath: string): BenchmarkConfig {
    const absolutePath = path.resolve(process.cwd(), filePath);
    if (!fs.existsSync(absolutePath)) {
        throw new Error(`Benchmark file not found at: ${absolutePath}`);
    }

    const fileContents = fs.readFileSync(absolutePath, 'utf8');
    const config = yaml.load(fileContents) as BenchmarkConfig;

    if (!config || !config.cases || !Array.isArray(config.cases)) {
        throw new Error(`Invalid benchmark format in: ${filePath}`);
    }

    return config;
}

export function normalizeUnits(text: string): string {
    if (!text) return text;
    // Regex tìm [Số] [Khoảng trắng tùy chọn] [Đơn vị]
    // Hỗ trợ số thập phân (dấu phẩy hoặc chấm)
    return text.replace(/(\d+(?:[.,]\d+)?)\s*([a-zA-Z%]+)/g, '$1 $2').trim();
}
