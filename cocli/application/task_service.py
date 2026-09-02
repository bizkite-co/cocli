from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Any, Callable

from cocli.core.tasks import TaskIndexManager, TaskStatus
from cocli.models.tasks import MissionTask

class TaskService:
    def __init__(self, issues_root: Path = Path("docs/issues")):
        self.issues_root = issues_root
        self.manager = TaskIndexManager(issues_root=issues_root)

    def sync_index(self) -> int:
        """Syncs the task index with the filesystem."""
        return self.manager.sync()

    def get_all_tasks(self) -> list[MissionTask]:
        """Returns all non-completed tasks."""
        return self.manager.tasks

    def prioritize_task(self, slug: str, position: int) -> bool:
        """Updates the ordinal position of a task in the index."""
        res = self.manager.prioritize(slug, position)
        if res:
            self.manager.save()
        return res

    def get_next_task(self) -> Optional[MissionTask]:
        """Returns the next startable task."""
        return self.manager.get_next_task()

    def resolve_file(self, slug: str) -> Optional[Path]:
        """Resolves the markdown file path for a task slug."""
        return self.manager.resolve_file(slug)

    def get_markdown_content_with_links(self, path: Path, seen: Optional[set[Path]] = None) -> list[dict[str, str]]:
        """
        Recursively reads a markdown file and extracts its content plus any
        linked local markdown files. Returns list of dicts with 'name' and 'content'.
        """
        if seen is None:
            seen = set()

        abs_path = path.resolve()
        if abs_path in seen or not path.exists():
            return []

        seen.add(abs_path)
        content = path.read_text(encoding="utf-8")
        results = [{"name": path.name, "content": content}]

        # Extract local markdown links: [text](path/to/file.md)
        links = re.findall(r'\[(?:[^\]]+)\]\(([^)]+\.md)\)', content)
        for link in links:
            link_path = (path.parent / link).resolve()
            if link_path.exists():
                results.extend(self.get_markdown_content_with_links(link_path, seen))

        return results

    def start_task(self, slug: Optional[str] = None) -> dict[str, Any]:
        """
        Moves a task to ACTIVE. If slug is None, gets the first pending/draft task.
        Returns a dict indicating success or error status.
        """
        # Find task
        task = None
        if slug:
            # Find by slug or priority index
            for i, t in enumerate(self.manager.tasks):
                if t.slug == slug or str(i + 1) == slug:
                    task = t
                    break
        else:
            # Get first PENDING or DRAFT task
            for t in self.manager.tasks:
                if t.status in [TaskStatus.PENDING, TaskStatus.DRAFT]:
                    task = t
                    break

        if not task:
            return {"success": False, "error": "No startable task found."}

        if task.status == TaskStatus.BLOCKED:
            return {
                "success": False,
                "error": f"Task '{task.slug}' is BLOCKED by {';'.join(task.dependencies)}"
            }

        # Find file
        old_path = self.manager.resolve_file(task.slug)
        if not old_path:
            return {"success": False, "error": f"Requirement file for '{task.slug}' not found."}

        new_rel_name = old_path.name
        if old_path.parent.name == "pending" and "_" in old_path.name:
            new_rel_name = old_path.name.split("_", 1)[1]

        new_path = self.issues_root / "active" / new_rel_name
        new_path.parent.mkdir(parents=True, exist_ok=True)

        old_path.rename(new_path)

        # Update index
        task.status = TaskStatus.ACTIVE
        self.manager.save()

        return {"success": True, "slug": task.slug}

    def create_task(
        self,
        title: str,
        slug: Optional[str] = None,
        body: Optional[str] = None,
        draft: bool = False,
        depends_on: Optional[str] = None,
    ) -> dict[str, Any]:
        """Creates a new task in the mission queue."""
        from cocli.utils.textual_utils import sanitize_id
        if not slug:
            slug = sanitize_id(title)

        if any(t.slug == slug for t in self.manager.tasks) or self.manager._is_task_completed(slug):
            return {"success": False, "error": f"Task with slug '{slug}' already exists."}

        dependencies = []
        warnings = []
        if depends_on:
            dependencies = [d.strip() for d in depends_on.split(",")]
            for dep in dependencies:
                if not any(t.slug == dep for t in self.manager.tasks) and not self.manager._is_task_completed(dep):
                    warnings.append(f"Dependency '{dep}' not found in index or completed history.")

        status = TaskStatus.DRAFT if draft else TaskStatus.PENDING
        folder = "draft" if draft else "pending"
        task_file = self.issues_root / folder / f"{slug}.md"
        task_file.parent.mkdir(parents=True, exist_ok=True)

        markdown_content = f"# {title}\n"
        if body:
            markdown_content += f"\n{body}\n"

        task_file.write_text(markdown_content, encoding="utf-8")

        from cocli.models.tasks import MissionTask
        new_task = MissionTask(
            slug=slug,
            dependencies=dependencies
        )
        new_task.title = title
        new_task.status = status
        self.manager.tasks.append(new_task)
        self.manager.save()

        return {
            "success": True,
            "status": status.value,
            "slug": slug,
            "task_file": task_file,
            "warnings": warnings,
        }

    def complete_task(
        self,
        slug: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_body: Optional[str] = None,
        commit_fn: Optional[Callable[[str, Optional[str]], None]] = None,
    ) -> dict[str, Any]:
        """
        Moves a task to COMPLETED, and executes commit_fn.
        """
        # Find task
        task = None
        if slug:
            for i, t in enumerate(self.manager.tasks):
                if t.slug == slug or str(i + 1) == slug:
                    task = t
                    break
        else:
            # Default to ACTIVE task
            for t in self.manager.tasks:
                if t.status == TaskStatus.ACTIVE:
                    task = t
                    break

        if not task:
            return {"success": False, "error": "No active task to complete."}

        old_path = self.manager.resolve_file(task.slug)
        if not old_path:
            return {"success": False, "error": f"Requirement file for '{task.slug}' not found."}

        # 1. Prepare Git Commit
        if commit_fn and commit_message:
            try:
                commit_fn(commit_message, commit_body)
            except Exception as e:
                return {"success": False, "error": f"Commit failed: {e}"}

        # 2. Update Filesystem and Index
        new_path = self.issues_root / "completed" / "2026" / old_path.name
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(new_path)

        # Removing from index happens automatically on save because we filter by status != COMPLETED
        task.status = TaskStatus.COMPLETED
        self.manager.update_blocked_states()
        self.manager.save()

        return {"success": True, "slug": task.slug}
