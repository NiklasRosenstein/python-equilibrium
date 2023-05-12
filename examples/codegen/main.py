from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent, indent
from typing import IO

from equilibrium.resource import Resource, ResourceContext
from equilibrium.rules import RulesEngine, collect_rules, get, rule

#
# Abstraction over Resource APIs
#


@dataclass(frozen=True)
class AwsAccount(Resource.Spec, apiVersion="example.com/v1", kind="AwsAccount", namespaced=False):
    displayName: str
    accountEmail: str
    region: str


@dataclass(frozen=True)
class TerraformWorkspace(Resource.Spec, apiVersion="example.com/v1", kind="TerraformWorkspace", namespaced=False):
    accountRef: Resource.URI
    moduleSource: str


#
# Terraform code generation
#

# Account creation module


@dataclass
class ResourceOutput:
    resource_addr: str
    attribute: str

    def __str__(self) -> str:
        return f"{self.resource_addr}.{self.attribute}"


@dataclass(frozen=True)
class AwsAccountCreation:
    code: str
    vault_credentials_path: str
    vault_token_resource: ResourceOutput


@rule
def get_account_creation_code(resource: Resource[AwsAccount]) -> AwsAccountCreation:
    """
    Generates the Terraform code to create an AWS account and store its credentials in Vault, as well as a Vault
    token that can be used to access the account credentials.
    """

    name = resource.metadata.name.replace("-", "_")
    account = resource.spec
    vault_credentials_path = f"accounts/aws/{resource.metadata.name}/credentials"
    code = dedent(
        f"""
        module "aws_account_{name}" {{
            source = "./modules/aws_account"
            account_name = "{account.displayName}"
            account_email = "{account.accountEmail}"
            vault_credentials_path = "{vault_credentials_path}"
        }}

        resource "vault_policy" "aws_account_{name}" {{
            name = "aws_account_{name}"
            policy = <<-EOF
                path "{vault_credentials_path}" {{
                    capabilities = ["read"]
                }}
            EOF
        }}

        resource "vault_token" "aws_account_{name}" {{
            role_name = "aws_account_{name}"
            policies = [vault_policy.aws_account_{name}.name]
            ttl = "32h"
            metadata = {{
                "aws_account_name" = "{account.displayName}"
            }}
        }}
        """
    ).strip()
    return AwsAccountCreation(
        code=code,
        vault_credentials_path=vault_credentials_path,
        vault_token_resource=ResourceOutput(
            resource_addr=f"vault_token.aws_account_{resource.metadata.name}",
            attribute="client_token",
        ),
    )


# Terraform workspace creation module


@dataclass(frozen=True)
class TerraformWorkspaceCreation:
    code: str


@rule
def get_workspace_creation_code(resource: Resource[TerraformWorkspace]) -> TerraformWorkspaceCreation:
    """
    Generate the code to create a Terraform workspace.
    """

    context = get(ResourceContext)
    account = context.resources.get(resource.spec.accountRef)
    if account.type == AwsAccount.TYPE:
        aws_account = account.into(AwsAccount)
        state = get(AwsAccountCreation, {Resource[AwsAccount]: aws_account})
        vault_token_resource = state.vault_token_resource
        module_configuration = get(AwsProviderInitialization, {Resource[AwsAccount]: aws_account}).code
    else:
        raise RuntimeError(f"unsupported account type: {account.type}")

    code = dedent(
        f"""
        module "workspace_{resource.metadata.name.replace('-', '_')}" {{
            source = "./modules/terraform_workspace"
            name = "{resource.metadata.name}"
            variables = [
                {{
                    name = "VAULT_TOKEN"
                    sensitive = true
                    category = "env"
                    value = {vault_token_resource}
                }}
            ]
            module_configuration = <<-EOF
                {indent(module_configuration, " " * 16).lstrip()}

                module "main" {{
                    source = "{resource.spec.moduleSource}"
                    # TODO
                }}
            EOF
        }}
        """
    ).strip()
    return TerraformWorkspaceCreation(code)


# AWS provider initialization


@dataclass
class AwsProviderInitialization:
    code: str


@rule
def get_aws_provider_code(resource: Resource[AwsAccount]) -> AwsProviderInitialization:
    """
    Returns the code that needs to be placed into the Terraform workspace configuration to initialize the AWS
    provider for the AWS account that the workspace is associated with. This assumes that the AWS credentials
    are available in Vault at the path `accounts/aws/<account-name>/credentials`.
    """

    account = resource.spec
    vault_credentials_path = get(AwsAccountCreation, {Resource[AwsAccount]: resource}).vault_credentials_path
    code = dedent(
        f"""
        data "vault_generic_secret" "aws_credentials" {{
            path = "{vault_credentials_path}"
        }}

        provider "aws" {{
            region = "{account.region}"
            access_key = data.vault_generic_secret.aws_credentials.data["access_key"]
            secret_key = data.vault_generic_secret.aws_credentials.data["secret_key"]
            assume_role {{
                role_arn = data.vault_generic_secret.aws_credentials.data["role_arn"]
            }}
        }}
        """
    ).strip()
    return AwsProviderInitialization(code)


# Terraform code generation


def generate_terraform_code(fp: IO[str]) -> None:
    context = get(ResourceContext)

    # Generate code for AWS accounts.
    account: Resource[AwsAccount]
    for account in sorted(context.resources.list(AwsAccount), key=lambda a: a.uri):
        creation = get(AwsAccountCreation, {Resource[AwsAccount]: account})
        print('\n#\n# AWS account "{}"\n#\n'.format(account.metadata.name), file=fp)
        print(creation.code, file=fp)

    # Generate code for Terraform workspaces.
    ws: Resource[TerraformWorkspace]
    for ws in context.resources.list(TerraformWorkspace):
        print('\n#\n# Terraform workspace "{}"\n#\n'.format(ws.metadata.name), file=fp)
        code = get(TerraformWorkspaceCreation, {Resource[TerraformWorkspace]: ws}).code
        print(code, file=fp)


def main() -> None:
    context = ResourceContext.create(ResourceContext.InMemoryBackend())
    context.resource_types.register(AwsAccount)
    context.resource_types.register(TerraformWorkspace)
    context.load_manifest(Path(__file__).parent / "manifest.yaml")

    engine = RulesEngine(collect_rules(), [context])
    engine.hashsupport.register(Resource, lambda r: hash(r.uri))
    with engine.as_current():
        generate_terraform_code(sys.stdout)


if __name__ == "__main__":
    main()
