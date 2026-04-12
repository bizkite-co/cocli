import shutil
from pathlib import Path

# Setup dummy structure
src = Path("src")
src.mkdir(exist_ok=True)
(src / "file.txt").write_text("hello")
dst = Path("dst")
dst.mkdir(exist_ok=True)

# Test copytree
shutil.copytree(src, dst, dirs_exist_ok=True)
print(f"Content of dst: {list(dst.iterdir())}")
