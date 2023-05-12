from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import IO

from equilibrium.resource import Resource, ResourceContext

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


#
# Terraform code generation
#


@dataclass
class ResourceOutput:
    resource_addr: str
    attribute: str

    def __str__(self) -> str:
        return f"{self.resource_addr}.{self.attribute}"


@dataclass
class AwsAccountCreation(Resource.State):
    code: str
    vault_credentials_path: str
    vault_token_resource: ResourceOutput


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
            metadata {{
                "aws_account_name" = "{account.displayName}"
            }}
        }}
        """
    )
    return AwsAccountCreation(
        code=code,
        vault_credentials_path=vault_credentials_path,
        vault_token_resource=ResourceOutput(
            resource_addr=f"vault_token.aws_account_{resource.metadata.name}",
            attribute="client_token",
        ),
    )


def get_workspace_creation_code(context: ResourceContext, resource: Resource[TerraformWorkspace]) -> str:
    """
    Generate the code to create a Terraform workspace.
    """

    account = context.resources.get(resource.spec.accountRef)
    if account.type == AwsAccount.TYPE:
        vault_token_resource = account.get_state(AwsAccountCreation).vault_token_resource
    else:
        raise RuntimeError(f"unsupported account type: {account.type}")

    return dedent(
        f"""
        module "workspace_{resource.metadata.name.replace('-', '_')}" {{
            source = "./modules/terraform_workspace"
            variables = [
                {{
                    name = "VAULT_TOKEN"
                    sensitive = true
                    category = "env"
                    value = {vault_token_resource}
                }}
            ]
        }}
        """
    )


def get_aws_provider_code(resource: Resource[AwsAccount], vault_credentials_path: str) -> str:
    """
    Returns the code that needs to be placed into the Terraform workspace configuration to initialize the AWS
    provider for the AWS account that the workspace is associated with. This assumes that the AWS credentials
    are available in Vault at the path `accounts/aws/<account-name>/credentials`.
    """

    account = resource.spec
    return dedent(
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
    )


def generate_terraform_code(context: ResourceContext, fp: IO[str]) -> None:
    # Generate code for AWS accounts.
    account: Resource[AwsAccount]
    for account in sorted(context.resources.list(AwsAccount), key=lambda a: a.uri):
        creation = get_account_creation_code(account)
        account.set_state(AwsAccountCreation, creation)
        context.resources.put(account, stateful=True)
        print('#\n# AWS account "{}"\n#'.format(account.metadata.name), file=fp)
        print(creation.code, file=fp)

    # Generate code for Terraform workspaces.
    ws: Resource[TerraformWorkspace]
    for ws in context.resources.list(TerraformWorkspace):
        print('#\n# Terraform workspace "{}"\n#'.format(ws.metadata.name), file=fp)
        code = get_workspace_creation_code(context, ws)
        print(code, file=fp)


def main() -> None:
    context = ResourceContext.create(ResourceContext.InMemoryBackend())
    context.resource_types.register(AwsAccount)
    context.resource_types.register(TerraformWorkspace)
    context.load_manifest(Path(__file__).parent / "manifest.yaml")
    generate_terraform_code(context, sys.stdout)


if __name__ == "__main__":
    main()
