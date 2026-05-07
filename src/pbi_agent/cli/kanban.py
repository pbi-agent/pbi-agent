from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pbi_agent.config import ConfigError, slugify
from pbi_agent.session_store import (
    KanbanStageConfigRecord,
    KanbanTaskRecord,
    SessionStore,
)
from pbi_agent.workspace_context import current_workspace_context


def _handle_kanban_command(args: argparse.Namespace) -> int:
    if args.kanban_action == "create":
        return _handle_kanban_create_command(args)
    if args.kanban_action == "list":
        return _handle_kanban_list_command(args)
    print(f"Error: unknown kanban action {args.kanban_action!r}", file=sys.stderr)
    return 2


def _handle_kanban_create_command(args: argparse.Namespace) -> int:
    title = args.title.strip()
    prompt = args.desc.strip()
    if not title:
        print("Error: --title cannot be empty.", file=sys.stderr)
        return 2
    if not prompt:
        print("Error: --desc cannot be empty.", file=sys.stderr)
        return 2

    workspace_context = current_workspace_context()
    workspace_root = workspace_context.execution_root
    directory_key = workspace_context.directory_key
    project_dir = args.project_dir.strip() or "."
    try:
        _validate_kanban_project_dir(workspace_root, project_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    with SessionStore() as store:
        stages = store.list_kanban_stage_configs(directory_key)
        stage = _resolve_kanban_stage(args.lane, stages)
        if stage is None:
            available = ", ".join(f"{item.name} ({item.stage_id})" for item in stages)
            print(
                f"Error: unknown Kanban lane/stage {args.lane!r}. "
                f"Available stages: {available}",
                file=sys.stderr,
            )
            return 2
        record = store.create_kanban_task(
            directory=directory_key,
            title=title,
            prompt=prompt,
            stage=stage.stage_id,
            project_dir=project_dir,
            session_id=args.session_id,
        )

    if args.json_output:
        payload = _kanban_task_payload(record, stage_name=stage.name)
        print(json.dumps(payload, sort_keys=True))
        return 0

    print(f"Created Kanban task {record.task_id} in {stage.name}: {record.title}")
    return 0


def _handle_kanban_list_command(args: argparse.Namespace) -> int:
    workspace_context = current_workspace_context()
    directory_key = workspace_context.directory_key
    with SessionStore() as store:
        stages = store.list_kanban_stage_configs(directory_key)
        stage_filter = _resolve_kanban_stage_filter(args.stage, stages)
        if args.stage is not None and args.stage.strip() and stage_filter is None:
            available = ", ".join(f"{item.name} ({item.stage_id})" for item in stages)
            print(
                f"Error: unknown Kanban lane/stage {args.stage!r}. "
                f"Available stages: {available}",
                file=sys.stderr,
            )
            return 2
        tasks = store.list_kanban_tasks(directory_key)

    stage_names = {stage.stage_id: stage.name for stage in stages}
    if stage_filter is not None:
        tasks = [task for task in tasks if task.stage == stage_filter.stage_id]

    if args.json_output:
        payload = [
            _kanban_task_payload(
                task,
                stage_name=stage_names.get(task.stage, task.stage),
            )
            for task in tasks
        ]
        print(json.dumps(payload, sort_keys=True))
        return 0

    if not tasks:
        if stage_filter is None:
            print("No Kanban tasks found.")
        else:
            print(
                f"No Kanban tasks found in {stage_filter.name} ({stage_filter.stage_id})."
            )
        return 0

    for index, task in enumerate(tasks):
        if index:
            print()
        _print_kanban_task_detail(
            task, stage_name=stage_names.get(task.stage, task.stage)
        )
    return 0


def _resolve_kanban_stage(
    lane: str | None,
    stages: list[KanbanStageConfigRecord],
) -> KanbanStageConfigRecord | None:
    if not stages:
        return None
    if lane is None or not lane.strip():
        return stages[0]
    return _match_kanban_stage(lane, stages)


def _resolve_kanban_stage_filter(
    stage_filter: str | None,
    stages: list[KanbanStageConfigRecord],
) -> KanbanStageConfigRecord | None:
    if stage_filter is None or not stage_filter.strip():
        return None
    return _match_kanban_stage(stage_filter, stages)


def _match_kanban_stage(
    requested_value: str,
    stages: list[KanbanStageConfigRecord],
) -> KanbanStageConfigRecord | None:
    requested = requested_value.strip()
    requested_slug = _kanban_slug_or_none(requested)
    for stage in stages:
        candidates = {
            stage.stage_id,
            stage.name,
        }
        for value in (stage.stage_id, stage.name):
            value_slug = _kanban_slug_or_none(value)
            if value_slug is not None:
                candidates.add(value_slug)
        if requested in candidates or (
            requested_slug is not None and requested_slug in candidates
        ):
            return stage
        lower_candidates = {candidate.lower() for candidate in candidates}
        if requested.lower() in lower_candidates or (
            requested_slug is not None and requested_slug.lower() in lower_candidates
        ):
            return stage
    return None


def _kanban_task_payload(
    record: KanbanTaskRecord,
    *,
    stage_name: str,
) -> dict[str, object]:
    return {
        "task_id": record.task_id,
        "directory": record.directory,
        "title": record.title,
        "prompt": record.prompt,
        "stage": record.stage,
        "stage_name": stage_name,
        "position": record.position,
        "project_dir": record.project_dir,
        "session_id": record.session_id,
        "model_profile_id": record.model_profile_id,
        "run_status": record.run_status,
        "last_result_summary": record.last_result_summary,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "last_run_started_at": record.last_run_started_at,
        "last_run_finished_at": record.last_run_finished_at,
        "image_attachments": [
            {
                "upload_id": attachment.upload_id,
                "name": attachment.name,
                "mime_type": attachment.mime_type,
                "byte_count": attachment.byte_count,
                "preview_url": attachment.preview_url,
            }
            for attachment in record.image_attachments
        ],
    }


def _print_kanban_task_detail(record: KanbanTaskRecord, *, stage_name: str) -> None:
    print(f"Task ID: {record.task_id}")
    print(f"Title: {record.title}")
    print(f"Prompt: {record.prompt}")
    print(f"Stage: {stage_name} ({record.stage})")
    print(f"Position: {record.position}")
    print(f"Project dir: {record.project_dir}")
    print(f"Session ID: {record.session_id or '-'}")
    print(f"Model profile ID: {record.model_profile_id or '-'}")
    print(f"Run status: {record.run_status}")
    print(f"Last result summary: {record.last_result_summary or '-'}")
    print(f"Created at: {record.created_at}")
    print(f"Updated at: {record.updated_at}")
    print(f"Last run started at: {record.last_run_started_at or '-'}")
    print(f"Last run finished at: {record.last_run_finished_at or '-'}")
    print(f"Image attachments: {len(record.image_attachments)}")


def _kanban_slug_or_none(value: str) -> str | None:
    try:
        return slugify(value)
    except ConfigError:
        return None


def _validate_kanban_project_dir(workspace_root: Path, project_dir: str) -> None:
    target = (workspace_root / project_dir).resolve()
    try:
        target.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(
            f"Project directory must be inside the workspace: {target}"
        ) from exc
    if not target.exists():
        raise FileNotFoundError(f"Project directory does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {target}")
