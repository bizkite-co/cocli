import logging
from pathlib import Path
from typing import List, Optional
from ..models.tasks import MissionTask, TaskStatus

__all__ = ["TaskIndexManager", "TaskStatus"]

logger = logging.getLogger(__name__)

class TaskIndexManager:
    """
    Manages the docs/issues/mission.usv file.
    Only tracks ACTIVE, PENDING, and DRAFT tasks.
    Completed tasks are moved to filesystem but removed from index.
    """
    def __init__(self, issues_root: Path = Path("docs/issues")):
        self.issues_root = issues_root
        self.index_path = issues_root / "mission.usv"
        self.tasks: List[MissionTask] = []
        self.load()

    def resolve_file(self, slug: str) -> Optional[Path]:
        """Dynamically finds the markdown file for a slug in active queue folders."""
        for folder in ["active", "pending", "draft"]:
            path = self.issues_root / folder
            if not path.exists():
                continue
            # Check exact slug
            exact = path / f"{slug}.md"
            if exact.exists():
                return exact
            # Check with numeric prefix
            for f in path.glob(f"*_{slug}.md"):
                return f
        return None

    def load(self) -> None:
        """Loads tasks from mission.usv preserving file order."""
        if not self.index_path.exists():
            self.tasks = []
            return

        tasks = []
        with open(self.index_path, "r", encoding="utf-8") as f:
            f.readline() # header
            for line in f:
                if not line.strip():
                    continue
                try:
                    task = MissionTask.from_usv(line)
                    tasks.append(task)
                except Exception as e:
                    logger.error(f"Failed to parse task line: {line.strip()}. Error: {e}")
        self.tasks = tasks

    def save(self, wasi_hash: Optional[str] = None) -> None:
        """Saves non-completed tasks to mission.usv in current list order."""
        self.issues_root.mkdir(parents=True, exist_ok=True)
        MissionTask.save_datapackage(self.issues_root, "mission-index", "mission.usv", wasi_hash=wasi_hash)
        
        # Filter: Only keep active queue items in the index
        active_queue = [t for t in self.tasks if t.status != TaskStatus.COMPLETED]
        
        with open(self.index_path, "w", encoding="utf-8") as f:
            f.write(MissionTask.get_header() + "\n")
            for task in active_queue:
                f.write(task.to_usv())

    def sync(self) -> int:
        """
        Discovers new tasks in draft, pending, and active.
        Syncs state and purges deleted or completed tasks from the index.
        """
        found_stems = {}
        for folder in ["active", "pending", "draft"]:
            path = self.issues_root / folder
            if not path.exists():
                continue
            for f in path.glob("*.md"):
                stem = f.stem
                slug = stem.split("_", 1)[1] if "_" in stem and stem.split("_", 1)[0].isdigit() else stem
                found_stems[slug] = folder

        new_tasks_list = []
        changes = 0
        
        # 1. Preserve order of existing tasks that still exist in active queue folders
        for task in self.tasks:
            if task.slug in found_stems:
                folder = found_stems[task.slug]
                status = self._get_status_from_folder(folder)
                if task.status != status:
                    task.status = status
                    changes += 1
                new_tasks_list.append(task)
                del found_stems[task.slug]
            else:
                # Task either completed or deleted from active folders
                changes += 1

        # 2. Append new tasks discovered in active folders
        for slug, folder in found_stems.items():
            new_task = MissionTask(
                slug=slug,
                title=slug.replace("-", " ").title(),
                status=self._get_status_from_folder(folder)
            )
            new_tasks_list.append(new_task)
            changes += 1

        self.tasks = new_tasks_list
        self.update_blocked_states()
        self.save()
        return changes

    def _get_status_from_folder(self, folder: str) -> TaskStatus:
        if folder == "active":
            return TaskStatus.ACTIVE
        if folder == "draft":
            return TaskStatus.DRAFT
        return TaskStatus.PENDING

    def prioritize(self, slug: str, position: int) -> bool:
        idx = -1
        for i, t in enumerate(self.tasks):
            if t.slug == slug:
                idx = i
                break
        
        if idx == -1:
            return False
        
        target_idx = max(0, min(position - 1, len(self.tasks) - 1))
        task = self.tasks.pop(idx)
        self.tasks.insert(target_idx, task)
        self.save()
        return True

    def update_blocked_states(self) -> None:
        """
        Sets tasks to BLOCKED if dependencies are missing from the index.
        (Since we purge COMPLETED from index, missing == completed or nonexistent).
        """
        # We need a way to check if a dependency is completed (filesystem check)
        for task in self.tasks:
            is_blocked = False
            for dep_slug in task.dependencies:
                # If dep exists in active queue, it's not completed -> BLOCKED
                if any(t.slug == dep_slug for t in self.tasks):
                    is_blocked = True
                    break
                
                # If dep NOT in index, verify it exists in completed/
                if not self._is_task_completed(dep_slug):
                    is_blocked = True
                    break
            
            if is_blocked:
                task.status = TaskStatus.BLOCKED
            elif task.status == TaskStatus.BLOCKED:
                # Restore status based on current folder
                task_file = self.resolve_file(task.slug)
                if task_file:
                    task.status = self._get_status_from_folder(task_file.parent.name)

    def _is_task_completed(self, slug: str) -> bool:
        """Checks completed/ directory recursively for the slug."""
        completed_root = self.issues_root / "completed"
        # Check all years/subfolders
        for f in completed_root.rglob(f"*{slug}.md"):
            return True
        return False

    def get_next_task(self) -> Optional[MissionTask]:
        for task in self.tasks:
            if task.status == TaskStatus.ACTIVE:
                return task
        for task in self.tasks:
            if task.status == TaskStatus.PENDING:
                return task
        return None
