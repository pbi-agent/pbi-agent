from __future__ import annotations

import argparse

from pbi_agent.auth.cli_flow import (
    run_provider_browser_auth_flow,
    run_provider_device_auth_flow,
)
from pbi_agent.auth.models import (
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_FLOW_METHOD_DEVICE,
    AUTH_MODE_API_KEY,
)
from pbi_agent.auth.service import (
    delete_provider_auth_session,
    get_provider_auth_status,
    import_provider_auth_session,
    provider_auth_flow_methods,
    provider_auth_modes,
    refresh_provider_auth_session,
)
from pbi_agent.auth.usage_limits import (
    ProviderUsageLimits,
    UsageLimitBucket,
    UsageLimitWindow,
    get_provider_usage_limits,
)
from pbi_agent.config import (
    ConfigError,
    ModelProfileConfig,
    ProviderConfig,
    create_model_profile_config,
    create_provider_config,
    delete_model_profile_config,
    delete_provider_config,
    list_model_profile_configs,
    load_internal_config,
    list_provider_configs,
    select_active_model_profile,
    slugify,
    update_maintenance_config,
    update_model_profile_config,
    update_provider_config,
)

from .web import _open_browser_url


def _handle_config_command(args: argparse.Namespace) -> int:  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    if args.config_scope == "providers":
        return _handle_config_providers_command(args)
    if args.config_scope == "profiles":
        return _handle_config_profiles_command(args)
    if args.config_scope == "maintenance":
        return _handle_config_maintenance_command(args)
    raise ConfigError(f"Unknown config scope '{args.config_scope}'.")


def _handle_config_maintenance_command(args: argparse.Namespace) -> int:
    if args.config_action == "show":
        config = load_internal_config().maintenance
        print(f"retention_days: {config.retention_days}")
        return 0
    if args.config_action == "set":
        config, _ = update_maintenance_config(retention_days=args.retention_days)
        print(f"Updated maintenance retention to {config.retention_days} days.")
        return 0
    raise ConfigError(f"Unknown maintenance config action '{args.config_action}'.")


def _handle_config_providers_command(args: argparse.Namespace) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console(width=160)

    if args.config_action == "list":
        providers = list_provider_configs()
        if not providers:
            console.print("[dim]No saved providers.[/dim]")
            return 0
        table = Table(title="Saved Providers", title_style="bold cyan")
        table.add_column("ID", style="green")
        table.add_column("Name")
        table.add_column("Kind", style="yellow")
        table.add_column("Auth Mode", style="yellow")
        table.add_column("Auth Status")
        table.add_column("API Key")
        table.add_column("Responses URL")
        table.add_column("Generic API URL")
        for provider in providers:
            table.add_row(
                provider.id,
                provider.name,
                provider.kind,
                provider.auth_mode,
                _format_provider_auth_status(provider),
                _display_secret(provider.api_key),
                provider.responses_url or "",
                provider.generic_api_url or "",
            )
        console.print(table)
        return 0

    if args.config_action == "create":
        provider, _ = create_provider_config(
            ProviderConfig(
                id=slugify(args.id or args.name),
                name=args.name,
                kind=args.kind,
                auth_mode=args.auth_mode or provider_auth_modes(args.kind)[0],
                api_key=args.provider_api_key or "",
                api_key_env=args.api_key_env,
                responses_url=args.responses_url,
                generic_api_url=args.generic_api_url,
            )
        )
        print(f"Created provider '{provider.id}'.")
        return 0

    if args.config_action == "update":
        provider, _ = update_provider_config(
            args.provider_id,
            name=args.name,
            kind=args.kind,
            auth_mode=args.auth_mode,
            api_key=args.provider_api_key,
            api_key_env=args.api_key_env,
            responses_url=args.responses_url,
            generic_api_url=args.generic_api_url,
        )
        print(f"Updated provider '{provider.id}'.")
        return 0

    if args.config_action == "delete":
        delete_provider_config(args.provider_id)
        print(f"Deleted provider '{slugify(args.provider_id)}'.")
        return 0

    if args.config_action == "auth-status":
        provider = _require_provider_config(args.provider_id)
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-login":
        provider = _require_provider_config(args.provider_id)
        method = args.method
        if method is None:
            supported_methods = provider_auth_flow_methods(
                provider.kind,
                provider.auth_mode,
            )
            if AUTH_FLOW_METHOD_BROWSER in supported_methods:
                method = AUTH_FLOW_METHOD_BROWSER
            elif AUTH_FLOW_METHOD_DEVICE in supported_methods:
                method = AUTH_FLOW_METHOD_DEVICE
            else:
                raise ConfigError(
                    f"Provider '{provider.id}' does not support built-in auth flows."
                )
        if method == AUTH_FLOW_METHOD_BROWSER:
            result = run_provider_browser_auth_flow(
                provider_kind=provider.kind,
                provider_id=provider.id,
                auth_mode=provider.auth_mode,
                open_browser=_open_browser_url,
                on_ready=_print_browser_auth_instructions,
            )
            print(
                f"Connected auth session for '{provider.id}'"
                + (f" ({result.session.email})" if result.session.email else "")
                + "."
            )
            _print_provider_auth_status(provider)
            return 0

        result = run_provider_device_auth_flow(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
            on_start=_print_device_auth_instructions,
        )
        print(
            f"Connected auth session for '{provider.id}'"
            + (f" ({result.session.email})" if result.session.email else "")
            + "."
        )
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-import":
        provider = _require_provider_config(args.provider_id)
        session = import_provider_auth_session(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
            payload={
                "access_token": args.access_token,
                "refresh_token": args.refresh_token,
                "account_id": args.account_id,
                "email": args.email,
                "plan_type": args.plan_type,
                "expires_at": args.expires_at,
                "id_token": args.id_token,
            },
        )
        print(
            f"Imported auth session for '{provider.id}'"
            + (f" ({session.email})" if session.email else "")
            + "."
        )
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-refresh":
        provider = _require_provider_config(args.provider_id)
        session = refresh_provider_auth_session(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        print(
            f"Refreshed auth session for '{provider.id}'"
            + (f" ({session.email})" if session.email else "")
            + "."
        )
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "auth-logout":
        provider = _require_provider_config(args.provider_id)
        removed = delete_provider_auth_session(provider.id)
        if removed:
            print(f"Deleted auth session for '{provider.id}'.")
        else:
            print(f"No stored auth session for '{provider.id}'.")
        _print_provider_auth_status(provider)
        return 0

    if args.config_action == "usage-limits":
        provider = _require_provider_config(args.provider_id)
        _print_provider_usage_limits(get_provider_usage_limits(provider))
        return 0

    raise ConfigError(f"Unknown providers action '{args.config_action}'.")


def _handle_config_profiles_command(args: argparse.Namespace) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    if args.config_action == "list":
        profiles, active_profile_id = list_model_profile_configs()
        if not profiles:
            console.print("[dim]No saved model profiles.[/dim]")
            return 0
        table = Table(title="Saved Model Profiles", title_style="bold cyan")
        table.add_column("ID", style="green")
        table.add_column("Active", style="yellow")
        table.add_column("Name")
        table.add_column("Provider", style="yellow")
        table.add_column("Model")
        table.add_column("Sub-Agent")
        table.add_column("Reasoning")
        for profile in profiles:
            table.add_row(
                profile.id,
                "yes" if profile.id == active_profile_id else "",
                profile.name,
                profile.provider_id,
                profile.model or "",
                profile.sub_agent_model or "",
                profile.reasoning_effort or "",
            )
        console.print(table)
        return 0

    if args.config_action == "create":
        profile, _ = create_model_profile_config(
            ModelProfileConfig(
                id=slugify(args.id or args.name),
                name=args.name,
                provider_id=args.provider_id,
                model=args.model,
                sub_agent_model=args.sub_agent_model,
                reasoning_effort=args.reasoning_effort,
                max_tokens=args.max_tokens,
                service_tier=args.service_tier,
                web_search=args.web_search,
                max_tool_workers=args.max_tool_workers,
                max_retries=args.max_retries,
                compact_threshold=args.compact_threshold,
                compact_tail_turns=args.compact_tail_turns,
                compact_preserve_recent_tokens=args.compact_preserve_recent_tokens,
                compact_tool_output_max_chars=args.compact_tool_output_max_chars,
            )
        )
        print(f"Created model profile '{profile.id}'.")
        return 0

    if args.config_action == "update":
        profile, _ = update_model_profile_config(
            args.profile_id,
            name=args.name,
            provider_id=args.provider_id,
            model=args.model,
            sub_agent_model=args.sub_agent_model,
            reasoning_effort=args.reasoning_effort,
            max_tokens=args.max_tokens,
            service_tier=args.service_tier,
            web_search=args.web_search,
            max_tool_workers=args.max_tool_workers,
            max_retries=args.max_retries,
            compact_threshold=args.compact_threshold,
            compact_tail_turns=args.compact_tail_turns,
            compact_preserve_recent_tokens=args.compact_preserve_recent_tokens,
            compact_tool_output_max_chars=args.compact_tool_output_max_chars,
        )
        print(f"Updated model profile '{profile.id}'.")
        return 0

    if args.config_action == "delete":
        delete_model_profile_config(args.profile_id)
        print(f"Deleted model profile '{slugify(args.profile_id)}'.")
        return 0

    if args.config_action == "select":
        active_id, _ = select_active_model_profile(args.profile_id)
        print(f"Selected default model profile '{active_id}'.")
        return 0

    raise ConfigError(f"Unknown profiles action '{args.config_action}'.")


def _display_secret(value: str) -> str:
    return value and f"{value[:4]}...{value[-4:]}" if value else ""


def _require_provider_config(provider_id: str) -> ProviderConfig:
    normalized_id = slugify(provider_id)
    for provider in list_provider_configs():
        if provider.id == normalized_id:
            return provider
    raise ConfigError(f"Unknown provider ID '{provider_id}'.")


def _provider_auth_status(provider: ProviderConfig):
    return get_provider_auth_status(
        provider_kind=provider.kind,
        provider_id=provider.id,
        auth_mode=provider.auth_mode,
    )


def _format_provider_auth_status(provider: ProviderConfig) -> str:
    if provider.auth_mode == AUTH_MODE_API_KEY:
        if provider.api_key_env:
            return f"env:{provider.api_key_env}"
        if provider.api_key:
            return "configured"
        return "missing"
    status = _provider_auth_status(provider)
    if status.email:
        return f"{status.session_status}:{status.email}"
    if status.plan_type:
        return f"{status.session_status}:{status.plan_type}"
    return status.session_status


def _print_provider_auth_status(provider: ProviderConfig) -> None:
    status = _provider_auth_status(provider)
    print(f"Provider: {provider.id}")
    print(f"Kind: {provider.kind}")
    print(f"Auth mode: {status.auth_mode}")
    print(f"Session status: {status.session_status}")
    print(f"Backend: {status.backend or 'n/a'}")
    print(f"Can refresh: {'yes' if status.can_refresh else 'no'}")
    if status.email:
        print(f"Email: {status.email}")
    if status.account_id:
        print(f"Account ID: {status.account_id}")
    if status.plan_type:
        print(f"Plan: {status.plan_type}")
    if status.expires_at is not None:
        print(f"Expires at: {status.expires_at}")


def _print_provider_usage_limits(usage: ProviderUsageLimits) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(f"Provider: [bold]{usage.provider_id}[/bold]")
    if usage.account_label:
        console.print(f"Account: {usage.account_label}")
    if usage.plan_type:
        console.print(f"Plan: {usage.plan_type}")
    console.print(f"Fetched: {usage.fetched_at}")
    if not usage.buckets:
        console.print("[dim]No usage limits returned.[/dim]")
        return
    table = Table(title="Subscription Usage Limits", title_style="bold cyan")
    table.add_column("Limit")
    table.add_column("Window")
    table.add_column("Used")
    table.add_column("Remaining")
    table.add_column("Reset")
    table.add_column("Status")
    table.add_column("Notes")
    for bucket in usage.buckets:
        windows: list[UsageLimitWindow | None] = list(bucket.windows) or [None]
        for index, window in enumerate(windows):
            table.add_row(
                bucket.label if index == 0 else "",
                window.name if window else "-",
                _format_usage_window_used(window),
                _format_usage_window_remaining(window),
                _format_usage_window_reset(window),
                bucket.status if index == 0 else "",
                _format_usage_bucket_notes(bucket) if index == 0 else "",
            )
    console.print(table)


def _format_usage_window_used(window: UsageLimitWindow | None) -> str:
    if window is None:
        return "-"
    parts: list[str] = []
    if window.used_percent is not None:
        parts.append(f"{window.used_percent:g}%")
    if window.used_requests is not None and window.total_requests is not None:
        parts.append(f"{window.used_requests}/{window.total_requests}")
    return " · ".join(parts) or "-"


def _format_usage_window_remaining(window: UsageLimitWindow | None) -> str:
    if window is None:
        return "-"
    parts: list[str] = []
    if window.remaining_percent is not None:
        parts.append(f"{window.remaining_percent:g}%")
    if window.remaining_requests is not None:
        parts.append(f"{window.remaining_requests} requests")
    return " · ".join(parts) or "-"


def _format_usage_window_reset(window: UsageLimitWindow | None) -> str:
    if window is None:
        return "-"
    if window.reset_at_iso:
        return window.reset_at_iso
    if window.resets_at is not None:
        return str(window.resets_at)
    if window.window_minutes is not None:
        return f"{window.window_minutes}m window"
    return "-"


def _format_usage_bucket_notes(bucket: UsageLimitBucket) -> str:
    notes: list[str] = []
    if bucket.unlimited:
        notes.append("unlimited")
    if bucket.overage_allowed:
        notes.append("overage allowed")
    if bucket.overage_count:
        notes.append(f"overage used: {bucket.overage_count}")
    if bucket.credits:
        if bucket.credits.unlimited:
            notes.append("credits: unlimited")
        elif bucket.credits.balance is not None:
            notes.append(f"credits: {bucket.credits.balance}")
        elif bucket.credits.has_credits is not None:
            notes.append("has credits" if bucket.credits.has_credits else "no credits")
    return ", ".join(notes) or "-"


def _print_browser_auth_instructions(browser_auth) -> None:
    print("Open this URL to complete provider authorization:")
    print(browser_auth.authorization_url)
    print(f"Waiting for callback on {browser_auth.redirect_uri} ...")


def _print_device_auth_instructions(device_auth) -> None:
    print("Open this URL and enter the one-time code to authorize the provider:")
    print(device_auth.verification_url)
    print(f"Code: {device_auth.user_code}")
    print("Waiting for device authorization ...")
