from cocli.application.task_service import TaskService

def test_task_service_create_and_sync(tmp_path):
    issues_root = tmp_path / "issues"
    service = TaskService(issues_root=issues_root)

    # Create task
    res = service.create_task(
        title="Test Task Title",
        slug="test-task-slug",
        body="Description of task.",
    )
    assert res["success"]
    assert res["slug"] == "test-task-slug"
    assert (issues_root / "pending" / "test-task-slug.md").exists()

    # Get all tasks
    tasks = service.get_all_tasks()
    assert len(tasks) == 1
    assert tasks[0].slug == "test-task-slug"
    assert tasks[0].title == "Test Task Title"

    # Start task
    res_start = service.start_task("test-task-slug")
    assert res_start["success"]
    assert not (issues_root / "pending" / "test-task-slug.md").exists()
    assert (issues_root / "active" / "test-task-slug.md").exists()

    # Complete task
    commit_called = []
    def dummy_commit_fn(msg, body):
        commit_called.append((msg, body))

    res_comp = service.complete_task(
        slug="test-task-slug",
        commit_message="Finished test task",
        commit_body="Done.",
        commit_fn=dummy_commit_fn,
    )
    assert res_comp["success"]
    assert commit_called == [("Finished test task", "Done.")]
    assert not (issues_root / "active" / "test-task-slug.md").exists()
    assert (issues_root / "completed" / "2026" / "test-task-slug.md").exists()
