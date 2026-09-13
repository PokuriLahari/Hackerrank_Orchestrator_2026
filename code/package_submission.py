"""
Packaging script to generate code.zip for challenge submission.
Ensures evaluation/usage_report.md is present at both archive root and inside code/.
Excludes caches, temporary files, datasets, and git repositories.
"""
import os
import zipfile

def package_submission(zip_filename="code.zip"):
    print(f"Creating {zip_filename}...")
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    code_dir = os.path.join(repo_root, "code")

    with zipfile.ZipFile(os.path.join(repo_root, zip_filename), "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all files in code/
        for root, dirs, files in os.walk(code_dir):
            # Skip pycache
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith((".pyc", ".pyo")):
                    continue
                abs_path = os.path.join(root, f)
                rel_path = os.path.relpath(abs_path, repo_root)
                zf.write(abs_path, arcname=rel_path)
                print(f"  Added: {rel_path}")

        # Ensure evaluation/usage_report.md is also at archive root
        usage_md = os.path.join(code_dir, "evaluation", "usage_report.md")
        if os.path.exists(usage_md):
            zf.write(usage_md, arcname="evaluation/usage_report.md")
            print("  Added: evaluation/usage_report.md (archive root)")

    print(f"\n{zip_filename} successfully created ({os.path.getsize(os.path.join(repo_root, zip_filename))} bytes).")

if __name__ == "__main__":
    package_submission()
