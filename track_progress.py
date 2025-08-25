import os
import subprocess
import sys

def get_commit_info():
    commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    commit_msg = subprocess.check_output(["git", "log", "-1", "--pretty=%B"]).decode().strip()
    return commit_hash, commit_msg

def count_added_lines(commit_hash):
    diff_output = subprocess.check_output(["git", "diff", f"{commit_hash}~1", commit_hash])
    added_lines = sum(1 for line in diff_output.decode().splitlines() if line.startswith("+") and not line.startswith("+++"))
    return added_lines

def main():
    commit_hash, commit_msg = get_commit_info()
    added_lines = count_added_lines(commit_hash)

    tracker_dir = os.path.join(os.getcwd(), "progress_tracker")
    os.makedirs(tracker_dir, exist_ok=True)

    filename = f"{commit_hash[:7]}_{commit_msg.replace(' ', '_')}.txt"
    filepath = os.path.join(tracker_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Commit: {commit_hash}\n")
        f.write(f"Message: {commit_msg}\n")
        f.write(f"Lines added: {added_lines}\n")

    print(f"[ProgressTracker] {filename} written with {added_lines} added lines.")

if __name__ == "__main__":
    main()
