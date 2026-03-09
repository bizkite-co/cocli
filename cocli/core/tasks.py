import logging
from pathlib import Path
from typing import List, Optional
from ..models.tasks import MissionTask, TaskStatus

__all__ = ["TaskIndexManager", "TaskStatus"]

logger = logging.getLogger(__name__)

class TaskIndexManager:
    """
    Manages the docs/issues/mission.usv file.
    Handles prioritization (via file order), dependencies, and state syncing.
    """
    def __init__(self, issues_root: Path = Path("docs/issues")):
        self.issues_root = issues_root
        self.index_path = issues_root / "mission.usv"
        self.tasks: List[MissionTask] = []
        self.load()

    def load(self) -> None:
        """Loads tasks from mission.usv preserving file order."""
        if not self.index_path.exists():
            self.tasks = []
            return

        tasks = []
        with open(self.index_path, "r", encoding="utf-8") as f:
            # Skip header
            f.readline()
            for line in f:
                if not line.strip():
                    continue
                try:
                    task = MissionTask.from_usv(line)
                    tasks.append(task)
                except Exception as e:
                    logger.error(f"Failed to parse task line: {line.strip()}. Error: {e}")
        self.tasks = tasks

    def save(self) -> None:
        """Saves tasks to mission.usv in current list order."""
        self.issues_root.mkdir(parents=True, exist_ok=True)
        # Ensure co-located datapackage
        MissionTask.save_datapackage(self.issues_root, "mission-index", "mission.usv")
        
        with open(self.index_path, "w", encoding="utf-8") as f:
            f.write(MissionTask.get_header() + "\n")
            for task in self.tasks:
                f.write(task.to_usv())

    def sync(self) -> int:
        """
        Scans filesystem folders and ensures the index is up to date.
        Discovers new tasks and removes stale ones.
        """
        found_files = {}
        for folder in ["pending", "active", "completed/2026"]:
            path = self.issues_root / folder
            if not path.exists():
                continue
            for f in path.glob("*.md"):
                found_files[f.stem] = f

        new_tasks_list = []
        changes = 0
        
        # 1. Preserve order of existing tasks that still exist on disk
        for task in self.tasks:
            # Find the disk stem (it might have a numeric prefix)
            stem_found = None
            for stem in found_files:
                slug = stem
                if "_" in stem and stem.split("_", 1)[0].isdigit():
                    slug = stem.split("_", 1)[1]
                if slug == task.slug:
                    stem_found = stem
                    break
            
            if stem_found:
                rel_path = str(found_files[stem_found].relative_to(self.issues_root))
                status = self._get_status_from_path(rel_path)
                if task.status != status or task.file_path != rel_path:
                    task.status = status
                    task.file_path = rel_path
                    changes += 1
                new_tasks_list.append(task)
                del found_files[stem_found]
            else:
                # Task file was deleted
                changes += 1

        # 2. Append new tasks at the end
        sorted_new_stems = sorted(found_files.keys())
        for stem in sorted_new_stems:
            slug = stem
            if "_" in stem and stem.split("_", 1)[0].isdigit():
                slug = stem.split("_", 1)[1]
            
            rel_path = str(found_files[stem].relative_to(self.issues_root))
            new_task = MissionTask(
                slug=slug,
                title=slug.replace("-", " ").title(),
                status=self._get_status_from_path(rel_path),
                file_path=rel_path
            )
            new_tasks_list.append(new_task)
            changes += 1

        self.tasks = new_tasks_list
        self.update_blocked_states()
        self.save()
        return changes

    def _get_status_from_path(self, rel_path: str) -> TaskStatus:
        if "active" in rel_path:
            return TaskStatus.ACTIVE
        if "completed" in rel_path:
            return TaskStatus.COMPLETED
        return TaskStatus.PENDING

    def prioritize(self, slug: str, position: int) -> bool:
        """Moves a task to a new ordinal position (1-based)."""
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
        """Automatically sets tasks to BLOCKED if dependencies are incomplete."""
        status_map = {t.slug: t.status for t in self.tasks}
        for task in self.tasks:
            if task.status == TaskStatus.COMPLETED:
                continue
                
            is_blocked = False
            for dep_slug in task.dependencies:
                if status_map.get(dep_slug) != TaskStatus.COMPLETED:
                    is_blocked = True
                    break
            
            if is_blocked:
                task.status = TaskStatus.BLOCKED
            elif task.status == TaskStatus.BLOCKED:
                task.status = TaskStatus.PENDING

    def get_next_task(self) -> Optional[MissionTask]:
        """Returns the first non-completed, non-blocked task."""
        for task in self.tasks:
            if task.status == TaskStatus.ACTIVE:
                return task
        for task in self.tasks:
            if task.status == TaskStatus.PENDING:
                return task
        return None
