"""Provision Azure Key Vault and grant team / app access.

One-time setup (vault admin):
    python scripts/provision_keyvault.py grant-app --client-id <APP_CLIENT_ID>
    python scripts/provision_keyvault.py grant-team --group "claim-ai-devs"

Seed secrets:
    python scripts/provision_keyvault.py seed --vault-name claim-ai-kv
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import dotenv_values

from app.connectors.secrets import (
    create_provisioning_secret_client,
    env_var_to_secret_name,
    get_key_vault_name,
    get_key_vault_url,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra"
DEFAULT_RESOURCE_GROUP = "claim-ai-rg"
DEFAULT_DEPLOYMENT_NAME = "claimai-keyvault"
SECRETS_USER_ROLE = "Key Vault Secrets User"
SECRETS_OFFICER_ROLE = "Key Vault Secrets Officer"
OBJECT_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check, text=True, capture_output=True)
    if result.returncode != 0 and check:
        print(result.stderr.strip())
        sys.exit(result.returncode)
    return result


def _require_az() -> None:
    try:
        result = _run(["az", "--version"], check=False)
    except FileNotFoundError:
        print("ERROR: Azure CLI (az) is not installed or not on PATH.")
        sys.exit(1)
    if result.returncode != 0:
        print("ERROR: Azure CLI is unavailable.")
        sys.exit(1)


def _vault_scope(*, vault_name: str, resource_group: str) -> str:
    vault_id = _run(
        [
            "az",
            "keyvault",
            "show",
            "--name",
            vault_name,
            "--resource-group",
            resource_group,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    ).stdout.strip()
    if not vault_id:
        print(f"ERROR: Vault '{vault_name}' not found in '{resource_group}'.")
        sys.exit(1)
    return vault_id


def _resolve_group_object_id(group: str) -> str:
    if OBJECT_ID_PATTERN.match(group):
        return group
    result = _run(
        [
            "az",
            "ad",
            "group",
            "show",
            "--group",
            group,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    )
    object_id = result.stdout.strip()
    if not object_id:
        print(f"ERROR: Azure AD group '{group}' not found.")
        sys.exit(1)
    return object_id


def _resolve_app_object_id(client_id: str) -> str:
    result = _run(
        [
            "az",
            "ad",
            "sp",
            "show",
            "--id",
            client_id,
            "--query",
            "id",
            "-o",
            "tsv",
        ]
    )
    object_id = result.stdout.strip()
    if not object_id:
        print(f"ERROR: App registration '{client_id}' not found.")
        sys.exit(1)
    return object_id


def _grant_role(
    *,
    scope: str,
    role: str,
    assignee_object_id: str,
    principal_type: str,
) -> None:
    exists = _run(
        [
            "az",
            "role",
            "assignment",
            "list",
            "--scope",
            scope,
            "--assignee",
            assignee_object_id,
            "--role",
            role,
            "--query",
            "[0].id",
            "-o",
            "tsv",
        ],
        check=False,
    ).stdout.strip()
    if exists:
        print(f"  [skip] {role} already assigned")
        return

    _run(
        [
            "az",
            "role",
            "assignment",
            "create",
            "--role",
            role,
            "--assignee-object-id",
            assignee_object_id,
            "--assignee-principal-type",
            principal_type,
            "--scope",
            scope,
        ]
    )
    print(f"  [ok] {role}")


def grant_team_access(
    *,
    vault_name: str,
    resource_group: str,
    group: str,
    officer: bool,
) -> None:
    _require_az()
    scope = _vault_scope(vault_name=vault_name, resource_group=resource_group)
    group_id = _resolve_group_object_id(group)

    print(f"Granting team group '{group}' access to {vault_name}...")
    _grant_role(
        scope=scope,
        role=SECRETS_USER_ROLE,
        assignee_object_id=group_id,
        principal_type="Group",
    )
    if officer:
        _grant_role(
            scope=scope,
            role=SECRETS_OFFICER_ROLE,
            assignee_object_id=group_id,
            principal_type="Group",
        )
    print("Done. Group members can manage vault secrets via Azure Portal / CLI.")


def grant_app_access(
    *,
    vault_name: str,
    resource_group: str,
    client_id: str,
    managed_identity: bool,
) -> None:
    _require_az()
    scope = _vault_scope(vault_name=vault_name, resource_group=resource_group)

    if managed_identity:
        object_id = client_id
        label = f"managed identity {object_id}"
    else:
        object_id = _resolve_app_object_id(client_id)
        label = f"app registration {client_id}"

    print(f"Granting {label} read access to {vault_name}...")
    _grant_role(
        scope=scope,
        role=SECRETS_USER_ROLE,
        assignee_object_id=object_id,
        principal_type="ServicePrincipal",
    )
    print(
        "Done. Set APP_CLIENT_ID in app/connectors/secrets.py and share the app registration "
        "client secret with the team as AZURE_CLIENT_SECRET (one shared app credential)."
    )


def deploy_keyvault(
    *,
    resource_group: str,
    deployment_name: str,
    location: str | None,
    key_vault_name: str | None,
    team_group_object_id: str | None,
    app_identity_object_id: str | None,
) -> str:
    _require_az()

    _run(
        [
            "az",
            "group",
            "create",
            "--name",
            resource_group,
            "--location",
            location or "australiaeast",
        ]
    )

    parameters = json.loads((INFRA_DIR / "main.parameters.json").read_text(encoding="utf-8"))
    if key_vault_name:
        parameters["parameters"]["keyVaultName"]["value"] = key_vault_name
    if team_group_object_id:
        parameters["parameters"]["teamGroupObjectId"]["value"] = team_group_object_id
    if app_identity_object_id:
        parameters["parameters"]["appIdentityObjectId"]["value"] = app_identity_object_id

    params_file = INFRA_DIR / ".main.parameters.generated.json"
    params_file.write_text(json.dumps(parameters, indent=2), encoding="utf-8")

    deploy_cmd = [
        "az",
        "deployment",
        "group",
        "create",
        "--resource-group",
        resource_group,
        "--name",
        deployment_name,
        "--template-file",
        str(INFRA_DIR / "main.bicep"),
        "--parameters",
        f"@{params_file}",
    ]
    if location:
        deploy_cmd.extend(["--parameters", f"location={location}"])

    _run(deploy_cmd)

    vault_uri = _run(
        [
            "az",
            "deployment",
            "group",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            deployment_name,
            "--query",
            "properties.outputs.keyVaultUri.value",
            "-o",
            "tsv",
        ]
    ).stdout.strip()

    print(f"Key Vault URI: {vault_uri}")
    return vault_uri


def seed_secrets(*, vault_name: str, env_file: Path, dry_run: bool) -> None:
    if not env_file.exists():
        print(f"ERROR: Env file not found: {env_file}")
        sys.exit(1)

    env_values = dotenv_values(env_file)
    seeded = 0
    skipped = 0

    client = None
    if not dry_run:
        vault_url = get_key_vault_url() if vault_name == get_key_vault_name() else f"https://{vault_name}.vault.azure.net/"
        client = create_provisioning_secret_client(vault_url)
        print(f"Seeding vault: {vault_url}")

    for env_var, value in env_values.items():
        secret_name = env_var_to_secret_name(env_var)
        if not value or not str(value).strip():
            print(f"  [skip] {secret_name} ({env_var} empty)")
            skipped += 1
            continue

        if dry_run:
            print(f"  [dry-run] would set {secret_name}")
            seeded += 1
            continue

        assert client is not None
        client.set_secret(secret_name, value)
        print(f"  [ok] {secret_name}")
        seeded += 1

    print(f"Done — {seeded} secret(s) set, {skipped} skipped (empty).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision Azure Key Vault for claim-ai")
    subparsers = parser.add_subparsers(dest="command", required=True)

    grant_team = subparsers.add_parser(
        "grant-team",
        help="Grant an Azure AD group read access (all members can use the app)",
    )
    grant_team.add_argument("--group", required=True, help="Group display name or object ID")
    grant_team.add_argument("--vault-name", default=get_key_vault_name())
    grant_team.add_argument("--resource-group", default=DEFAULT_RESOURCE_GROUP)
    grant_team.add_argument(
        "--officer",
        action="store_true",
        help="Also grant Key Vault Secrets Officer (create/update secrets)",
    )

    grant_app = subparsers.add_parser(
        "grant-app",
        help="Grant the claim-ai app registration or managed identity read access",
    )
    grant_app.add_argument(
        "--client-id",
        required=True,
        help="App registration client ID or managed identity object ID",
    )
    grant_app.add_argument("--vault-name", default=get_key_vault_name())
    grant_app.add_argument("--resource-group", default=DEFAULT_RESOURCE_GROUP)
    grant_app.add_argument(
        "--managed-identity",
        action="store_true",
        help="Treat --client-id as a managed identity object ID",
    )

    deploy_parser = subparsers.add_parser("deploy", help="Deploy Key Vault via Bicep")
    deploy_parser.add_argument("--resource-group", default=DEFAULT_RESOURCE_GROUP)
    deploy_parser.add_argument("--deployment-name", default=DEFAULT_DEPLOYMENT_NAME)
    deploy_parser.add_argument("--location", default="australiaeast")
    deploy_parser.add_argument("--key-vault-name", default=None)
    deploy_parser.add_argument("--team-group", default=None, help="Azure AD group name or ID")
    deploy_parser.add_argument("--app-client-id", default=None, help="App registration client ID")
    deploy_parser.add_argument("--seed", action="store_true")
    deploy_parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")

    seed_parser = subparsers.add_parser("seed", help="Seed secrets into an existing vault")
    seed_parser.add_argument("--vault-name", default=get_key_vault_name())
    seed_parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    seed_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.command == "grant-team":
        grant_team_access(
            vault_name=args.vault_name,
            resource_group=args.resource_group,
            group=args.group,
            officer=args.officer,
        )
    elif args.command == "grant-app":
        grant_app_access(
            vault_name=args.vault_name,
            resource_group=args.resource_group,
            client_id=args.client_id,
            managed_identity=args.managed_identity,
        )
    elif args.command == "deploy":
        team_id = _resolve_group_object_id(args.team_group) if args.team_group else None
        app_id = (
            _resolve_app_object_id(args.app_client_id) if args.app_client_id else None
        )
        vault_uri = deploy_keyvault(
            resource_group=args.resource_group,
            deployment_name=args.deployment_name,
            location=args.location,
            key_vault_name=args.key_vault_name,
            team_group_object_id=team_id,
            app_identity_object_id=app_id,
        )
        if args.seed:
            host = vault_uri.removeprefix("https://").split(".")[0]
            seed_secrets(vault_name=host, env_file=args.env_file, dry_run=False)
    elif args.command == "seed":
        seed_secrets(
            vault_name=args.vault_name,
            env_file=args.env_file,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
