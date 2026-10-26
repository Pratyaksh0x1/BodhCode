"""Benchmark script for testing AST extraction and resolution throughput on 2,000 files."""

import sys
import time
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def generate_benchmark_files(count: int = 2000) -> dict[str, bytes]:
    """Generate in-memory TypeScript and TSX files with realistic import and export structures."""
    files: dict[str, bytes] = {}

    # Root tsconfig.json with path aliases
    files["tsconfig.json"] = b"""{
        "compilerOptions": {
            "baseUrl": ".",
            "paths": {
                "@/*": ["src/*"],
                "@components/*": ["src/components/*"]
            }
        }
    }"""

    # Generate files across components, utils, and pages
    for i in range(count):
        dep_id = (i + 1) % count
        comp_id = (i + 2) % count

        if i % 3 == 0:
            path = f"src/components/Comp{i}.tsx"
            content = f"""
import React from "react";
import {{ util{dep_id} }} from "@/utils/util{dep_id}";
import {{ Comp{comp_id} }} from "@components/Comp{comp_id}";
import type {{ CompProps{i} }} from "../types/props";

export interface CompProps{i} {{
    id: number;
    title: string;
}}

export const Comp{i} = (props: CompProps{i}) => {{
    return <div>{{props.title}}</div>;
}};

export default Comp{i};
"""
        elif i % 3 == 1:
            path = f"src/utils/util{i}.ts"
            content = f"""
import path from "node:path";
import {{ util{dep_id} }} from "./util{dep_id}";
import {{ format }} from "lodash/fp";

export const util{i} = (x: number): number => {{
    return x + {i};
}};

export const config{i} = {{
    id: {i},
    name: "util_{i}",
}};
"""
        else:
            path = f"src/pages/Page{i}.tsx"
            content = f"""
import React, {{ useState }} from "react";
import {{ Comp{dep_id} }} from "@/components/Comp{dep_id}";
import {{ util{comp_id} }} from "@/utils/util{comp_id}";

export function Page{i}() {{
    const [state] = useState({i});
    return (
        <main>
            <Comp{dep_id} id={{state}} title="page" />
        </main>
    );
}}
"""
        files[path] = content.encode("utf-8")

    return files


def run_benchmark() -> None:
    file_count = 2000
    print(f"Generating {file_count} benchmark files in memory...")
    files = generate_benchmark_files(file_count)

    print(f"Running analyze_repo_files on {len(files)} files...")
    from app.parser.analyze import analyze_repo_files

    start_time = time.perf_counter()
    results = analyze_repo_files(files)
    elapsed = time.perf_counter() - start_time

    rate = len(results) / elapsed
    print("--------------------------------------------------")
    print(f"Total files analyzed: {len(results)}")
    print(f"Total time elapsed:   {elapsed:.2f} seconds")
    print(f"Throughput rate:      {rate:.1f} files/second")
    print("--------------------------------------------------")
    target_rate = 167.0  # 5,000 files in 30 seconds = ~167 files/sec
    if rate >= target_rate:
        print(f"PASS: {rate:.1f} files/sec exceeds target of {target_rate:.1f} files/sec.")
    else:
        print(f"FAIL: {rate:.1f} files/sec is below target of {target_rate:.1f} files/sec.")


if __name__ == "__main__":
    run_benchmark()
