"""
run.py
------
Command-line runner for testing the full DDR pipeline
without the Streamlit UI.

Usage:
    python run.py --inspection path/to/inspection.pdf --thermal path/to/thermal.pdf
"""

import argparse
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pdf_parser import parse_documents
from llm_client import generate_ddr_json
from report_builder import build_ddr_report


def main():
    parser = argparse.ArgumentParser(description="DDR Report Generator CLI")
    parser.add_argument("--inspection", required=True, help="Path to Inspection Report PDF")
    parser.add_argument("--thermal", required=True, help="Path to Thermal Report PDF")
    parser.add_argument("--output", default="output", help="Output directory (default: ./output)")
    parser.add_argument(
        "--model",
        default="llama-3.3-70b-versatile",
        help="Groq model to use (default: llama-3.3-70b-versatile)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.inspection):
        print(f"Error: Inspection PDF not found: {args.inspection}")
        sys.exit(1)
    if not os.path.exists(args.thermal):
        print(f"Error: Thermal PDF not found: {args.thermal}")
        sys.exit(1)
    if not os.getenv("GROQ_API_KEY"):
        print("Error: GROQ_API_KEY environment variable not set.")
        print("Set it with: export GROQ_API_KEY=your_key_here")
        sys.exit(1)

    images_dir = os.path.join(args.output, "extracted_images")

    print("\n══════════════════════════════════════")
    print("  DDR Report Generator")
    print("══════════════════════════════════════")

    # Step 1: Parse PDFs
    print("\n[1/3] Parsing PDFs...")
    parsed = parse_documents(args.inspection, args.thermal, images_dir)
    print(f"  Inspection text: {len(parsed['inspection_text'])} characters")
    print(f"  Thermal text: {len(parsed['thermal_text'])} characters")
    print(f"  Images extracted: {len(parsed['image_records'])}")

    # Step 2: Generate DDR JSON
    print(f"\n[2/3] Generating DDR with {args.model}...")
    ddr_data = generate_ddr_json(
        parsed["inspection_text"],
        parsed["thermal_text"],
        parsed["image_inventory"],
        model=args.model,
    )

    # Save JSON for reference
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(args.output, f"ddr_raw_{timestamp}.json")
    os.makedirs(args.output, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(ddr_data, f, indent=2)
    print(f"  Raw JSON saved to: {json_path}")

    # Print summary
    summary = ddr_data.get("property_issue_summary", {})
    print(f"\n  Issues found: {summary.get('total_issues_found', 0)} total")
    print(f"    Critical: {summary.get('critical_count', 0)}")
    print(f"    Moderate: {summary.get('moderate_count', 0)}")
    print(f"    Minor:    {summary.get('minor_count', 0)}")

    # Step 3: Build report
    print(f"\n[3/3] Building DDR report...")
    output_path = os.path.join(args.output, f"DDR_Report_{timestamp}.docx")
    build_ddr_report(ddr_data, parsed["image_records"], output_path)

    print("\n══════════════════════════════════════")
    print(f"  Done! Report saved to:")
    print(f"  {output_path}")
    print("══════════════════════════════════════\n")


if __name__ == "__main__":
    main()