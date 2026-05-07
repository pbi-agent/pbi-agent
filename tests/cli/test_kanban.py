from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pbi_agent import cli
from pbi_agent.session_store import KanbanStageConfigSpec, SessionStore


class KanbanCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace_env_patch = patch.dict(
            os.environ,
            {
                "PBI_AGENT_WORKSPACE_KEY": "",
                "PBI_AGENT_WORKSPACE_DISPLAY_PATH": "",
                "PBI_AGENT_SANDBOX": "",
            },
            clear=False,
        )
        self._workspace_env_patch.start()
        self.addCleanup(self._workspace_env_patch.stop)

    def test_parser_exposes_kanban_create_help(self) -> None:
        parser = cli.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        kanban_parser = subparsers.choices["kanban"]
        kanban_subparsers = next(
            action
            for action in kanban_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        help_text = kanban_subparsers.choices["create"].format_help()

        self.assertIn("usage: pbi-agent kanban create", help_text)
        self.assertIn("--title TITLE", help_text)
        self.assertIn("--desc DESC", help_text)
        self.assertIn("--lane LANE", help_text)

    def test_parser_exposes_kanban_list_help(self) -> None:
        parser = cli.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        kanban_parser = subparsers.choices["kanban"]
        kanban_subparsers = next(
            action
            for action in kanban_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        help_text = kanban_subparsers.choices["list"].format_help()

        self.assertIn("usage: pbi-agent kanban list", help_text)
        self.assertIn("--stage STAGE", help_text)
        self.assertIn("--json", help_text)

    def test_create_persists_task_without_provider_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with (
                    patch.dict(os.environ, {"PBI_AGENT_API_KEY": ""}, clear=False),
                    patch("sys.stdout", stdout),
                ):
                    rc = cli.main(
                        [
                            "kanban",
                            "create",
                            "--title",
                            "Refactor API endpoint",
                            "--desc",
                            "Improve endpoint performance.",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            self.assertIn("Created Kanban task", stdout.getvalue())
            with SessionStore() as store:
                tasks = store.list_kanban_tasks(str(root.resolve()).lower())
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].title, "Refactor API endpoint")
            self.assertEqual(tasks[0].prompt, "Improve endpoint performance.")
            self.assertEqual(tasks[0].stage, "backlog")

    def test_create_uses_workspace_key_env_for_task_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(
                    os.environ,
                    {"PBI_AGENT_WORKSPACE_KEY": "/host/Project"},
                    clear=False,
                ):
                    rc = cli.main(
                        [
                            "kanban",
                            "create",
                            "--title",
                            "Sandbox task",
                            "--desc",
                            "Persist with host workspace identity.",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            with SessionStore() as store:
                tasks = store.list_kanban_tasks("/host/project")
                internal_tasks = store.list_kanban_tasks(str(root.resolve()).lower())
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].title, "Sandbox task")
            self.assertEqual(internal_tasks, [])

    def test_create_resolves_lane_by_name_and_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with SessionStore() as store:
                    store.replace_kanban_stage_configs(
                        str(root.resolve()).lower(),
                        stages=[
                            KanbanStageConfigSpec(stage_id="backlog", name="Backlog"),
                            KanbanStageConfigSpec(
                                stage_id="in-progress", name="In Progress"
                            ),
                            KanbanStageConfigSpec(stage_id="done", name="Done"),
                        ],
                    )
                rc = cli.main(
                    [
                        "kanban",
                        "create",
                        "--title",
                        "Ship command",
                        "--desc",
                        "Create task from CLI.",
                        "--lane",
                        "In Progress",
                    ]
                )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            with SessionStore() as store:
                tasks = store.list_kanban_tasks(str(root.resolve()).lower())
            self.assertEqual(tasks[0].stage, "in-progress")

    def test_create_json_output_is_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with patch("sys.stdout", stdout):
                    rc = cli.main(
                        [
                            "kanban",
                            "create",
                            "--title",
                            "JSON task",
                            "--desc",
                            "Machine readable output.",
                            "--json",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["title"], "JSON task")
            self.assertEqual(payload["stage"], "backlog")
            self.assertEqual(payload["stage_name"], "Backlog")
            self.assertTrue(payload["task_id"])

    def test_create_rejects_non_sluggable_unknown_lane_with_available_stages(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stderr = io.StringIO()
            try:
                os.chdir(root)
                with patch("sys.stderr", stderr):
                    rc = cli.main(
                        [
                            "kanban",
                            "create",
                            "--title",
                            "Bad lane",
                            "--desc",
                            "Should not persist.",
                            "--lane",
                            "!!!",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 2)
            self.assertIn("unknown Kanban lane/stage", stderr.getvalue())
            self.assertIn("Backlog (backlog)", stderr.getvalue())
            with SessionStore() as store:
                tasks = store.list_kanban_tasks(str(root.resolve()).lower())
            self.assertEqual(tasks, [])

    def test_create_rejects_empty_title_or_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stderr = io.StringIO()
            try:
                os.chdir(root)
                with patch("sys.stderr", stderr):
                    title_rc = cli.main(
                        [
                            "kanban",
                            "create",
                            "--title",
                            " ",
                            "--desc",
                            "Body",
                        ]
                    )
                    desc_rc = cli.main(
                        [
                            "kanban",
                            "create",
                            "--title",
                            "Title",
                            "--desc",
                            " ",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(title_rc, 2)
            self.assertEqual(desc_rc, 2)
            self.assertIn("--title cannot be empty", stderr.getvalue())
            self.assertIn("--desc cannot be empty", stderr.getvalue())

    def test_create_rejects_project_dir_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            root.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            original_cwd = Path.cwd()
            stderr = io.StringIO()
            try:
                os.chdir(root)
                with patch("sys.stderr", stderr):
                    rc = cli.main(
                        [
                            "kanban",
                            "create",
                            "--title",
                            "Outside",
                            "--desc",
                            "Reject path.",
                            "--project-dir",
                            str(outside),
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 2)
            self.assertIn("inside the workspace", stderr.getvalue())
            with SessionStore() as store:
                tasks = store.list_kanban_tasks(str(root.resolve()).lower())
            self.assertEqual(tasks, [])

    def test_list_outputs_all_relevant_task_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with SessionStore() as store:
                    store.create_kanban_task(
                        directory=str(root.resolve()).lower(),
                        title="List task",
                        prompt="Show every useful field.",
                        stage="backlog",
                        project_dir=".",
                        session_id="session-123",
                        model_profile_id="profile-123",
                    )
                with (
                    patch.dict(os.environ, {"PBI_AGENT_API_KEY": ""}, clear=False),
                    patch("sys.stdout", stdout),
                ):
                    rc = cli.main(["kanban", "list"])
            finally:
                os.chdir(original_cwd)

            output = stdout.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("Task ID:", output)
            self.assertIn("Title: List task", output)
            self.assertIn("Prompt: Show every useful field.", output)
            self.assertIn("Stage: Backlog (backlog)", output)
            self.assertIn("Position:", output)
            self.assertIn("Project dir: .", output)
            self.assertIn("Session ID: session-123", output)
            self.assertIn("Model profile ID: profile-123", output)
            self.assertIn("Run status: idle", output)
            self.assertIn("Last result summary: -", output)
            self.assertIn("Created at:", output)
            self.assertIn("Updated at:", output)
            self.assertIn("Last run started at: -", output)
            self.assertIn("Last run finished at: -", output)
            self.assertIn("Image attachments: 0", output)

    def test_list_filters_tasks_by_stage_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with SessionStore() as store:
                    store.replace_kanban_stage_configs(
                        str(root.resolve()).lower(),
                        stages=[
                            KanbanStageConfigSpec(stage_id="backlog", name="Backlog"),
                            KanbanStageConfigSpec(
                                stage_id="in-progress", name="In Progress"
                            ),
                            KanbanStageConfigSpec(stage_id="done", name="Done"),
                        ],
                    )
                    store.create_kanban_task(
                        directory=str(root.resolve()).lower(),
                        title="Backlog task",
                        prompt="Not listed.",
                        stage="backlog",
                    )
                    store.create_kanban_task(
                        directory=str(root.resolve()).lower(),
                        title="Progress task",
                        prompt="Listed.",
                        stage="in-progress",
                    )
                with patch("sys.stdout", stdout):
                    rc = cli.main(["kanban", "list", "--stage", "In Progress"])
            finally:
                os.chdir(original_cwd)

            output = stdout.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("Title: Progress task", output)
            self.assertIn("Stage: In Progress (in-progress)", output)
            self.assertNotIn("Backlog task", output)

    def test_list_json_output_contains_all_task_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with SessionStore() as store:
                    record = store.create_kanban_task(
                        directory=str(root.resolve()).lower(),
                        title="JSON list task",
                        prompt="Show machine-readable fields.",
                        stage="backlog",
                    )
                with patch("sys.stdout", stdout):
                    rc = cli.main(["kanban", "list", "--json"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(len(payload), 1)
            task = payload[0]
            self.assertEqual(task["task_id"], record.task_id)
            self.assertEqual(task["directory"], str(root.resolve()).lower())
            self.assertEqual(task["title"], "JSON list task")
            self.assertEqual(task["prompt"], "Show machine-readable fields.")
            self.assertEqual(task["stage"], "backlog")
            self.assertEqual(task["stage_name"], "Backlog")
            self.assertIn("position", task)
            self.assertEqual(task["project_dir"], ".")
            self.assertIsNone(task["session_id"])
            self.assertIsNone(task["model_profile_id"])
            self.assertEqual(task["run_status"], "idle")
            self.assertEqual(task["last_result_summary"], "")
            self.assertIn("created_at", task)
            self.assertIn("updated_at", task)
            self.assertIsNone(task["last_run_started_at"])
            self.assertIsNone(task["last_run_finished_at"])
            self.assertEqual(task["image_attachments"], [])

    def test_list_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stderr = io.StringIO()
            try:
                os.chdir(root)
                with patch("sys.stderr", stderr):
                    rc = cli.main(["kanban", "list", "--stage", "!!!"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 2)
            self.assertIn("unknown Kanban lane/stage", stderr.getvalue())
            self.assertIn("Backlog (backlog)", stderr.getvalue())
