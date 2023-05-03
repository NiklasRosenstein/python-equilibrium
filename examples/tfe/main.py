"""
An example reconciler for managing Terraform Cloud/Enterprise workspaces.
"""

import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import pyterprise  # type: ignore[import]
import pyterprise.exceptions  # type: ignore[import]
import pyterprise.organization  # type: ignore[import]
import pyterprise.workspace  # type: ignore[import]
from rich.logging import RichHandler

from equilibrium.core.Context import Context
from equilibrium.core.CrudResourceController import CrudResourceController
from equilibrium.core.Namespace import Namespace
from equilibrium.core.Resource import Resource

TERRAFORM_VERSION_REGEX = r"^(latest|[0-9]+\.[0-9]+\.[0-9]+)$"
TERRAFORM_TAG_REGEX = r"^[a-zA-Z0-9\-\:]+$"


@dataclass
class ExecutionMode(Enum):
    Remote = "Remote"
    Local = "Local"


@dataclass
class WorkflowType(Enum):
    #: Use the API-driven run workflow which uploads a configuration to the workspace via the API.
    ApiDriven = "ApiDriven"

    #: Use a CLI-driven run workflow which allows users to run `terraform apply` locally.
    CliDriven = "CliDriven"

    #: Use a VCS-driven run workflow where the workspace is linked to a VCS repository.
    VcsDriven = "VcsDriven"


@dataclass
class AutoApplyType(Enum):
    #: Never automatically apply plans.
    Never = "Never"

    #: Apply normal plans automatically, but not destroy plans.
    Default = "Default"

    #: Only apply plans that do not destroy or recreate resources.
    NonDestrutiveOnly = "NonDestrutiveOnly"

    #: Apply all plans automatically, including destroy plans.
    All = "All"


@dataclass
class Variable:
    class Category(Enum):
        Terraform = "Terraform"
        Env = "Env"

    name: str
    value: str
    sensitive: bool = False
    category: Category = Category.Terraform
    hcl: bool = False


@dataclass
class VariableSelect:
    #: The name of the variable to select from the resource.
    name: str

    #: The name of the variable to assign in the current workspace. If this is not specified, the *name* will be used.
    #: If the variable selected is an environment variable and an alias is specified, the variable will by default
    #: be converted to a Terraform variable unless the *category* is set to `Env`.
    alias: str | None = None

    #: Override the category that the variable will be assigned to. If this is not specified, the category will be
    #: inherited from the variable selected, unless an *alias* is specified, in which case the category defaults to
    #: `Terraform`.
    category: Variable.Category | None = None

    def get_category(self, source_category: Variable.Category) -> Variable.Category:
        if self.category is not None:
            return self.category
        if self.alias is not None:
            return Variable.Category.Terraform
        return source_category


@dataclass(frozen=True)
class VariablesFrom(Resource.URI):
    """
    Select variables from another resources to assign to a workspace. If no variables are selected, all variables
    are selected.
    """

    #: A list of variables to select from the resource and the alias to assign them in the current workspace.
    #: If a variable is selected only by name, the name will be used as the alias, and the variable category
    #: will be inherited.
    select: list[VariableSelect] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderFrom(Resource.URI):
    """
    Similar to #VariablesFrom, but selects providers from another resource to assign to a workspace.
    """

    #: The provider source. Example: `hashicorp/aws`. The referenced resource must be able to provide a configuration
    #: for this type of provider.
    source: str

    #: The name of the provider. If this is not specified, the name of the provider will be derived from the source.
    providerName: str | None = None

    #: Give the provider an alias. This can be used to distinguish between multiple providers of the same type.
    alias: str | None = None


@dataclass
class Provider:
    """
    Represents a provider configuration.
    """

    name: str
    source: str
    version: str | None
    config: str
    variables: list[Variable]

    def get_requirement(self) -> str:
        if self.version:
            return f'{self.name} = {{ source = "{self.source}", version = "{self.version}" }}'
        else:
            return f'{self.name} = {{ source = "{self.source}" }}'


@dataclass
class TfeOrganization(Resource.Spec, apiVersion="example.com/v1", kind="TfeOrganization"):
    pass


@dataclass
class TfeWorkspace(Resource.Spec, apiVersion="example.com/v1", kind="TfeWorkspace"):
    #: The name of the workspace. If this is not specified, it will be derived from the name and namespace of
    #: the resource, or the name that is already given to the workspace.
    name: str | None = None

    #: The organization to create the Terraform workspace in.
    organization: str | None = None

    #: Description of the Terraform workspace.
    description: str = ""

    #: The execution mode of the workspace. This can only be set to "Local" for the CLI-driven workflow type.
    executionMode: ExecutionMode = ExecutionMode.Remote

    #: The type of workflow to use for the workspace.
    workflow: WorkflowType = WorkflowType.ApiDriven

    #: The module configuration for the Terraform workspace. This can only be set for the API workflow and
    #: cannot be combined with #moduleSource and #moduleVersion. This is a map of filenames to content.
    moduleConfiguration: dict[str, str] | None = None

    #: The source module for the Terraform workspace. This can only be set for the API workflow.
    moduleSource: str | None = None

    #: The module version. This can only be set for the CLI and API workflow types.
    moduleVersion: str | None = None

    #: The VCS repository to link to the workspace. This can only be set for the VCS workflow type. This must
    #: be in the form `<vcs>/<org>/<repo>[//<subdirectory>][?branch=<branch>]`. For example,
    #: `gitlab/ExampleOrg/infrastructure`. The `<vcs>` must be the name of the VCS registration in Terraform
    #: Enterprise, not the hostname of the VCS provider. The `<subdirectory>` is optional and can be used to specify
    #: a subdirectory within the repository to use as the root of the workspace. If this is not specified, the root of
    #: the repository will be used.
    vcsRepo: str | None = None

    #: Permit speculative plans in the VCS-driven workflow. Defaults to `True`.`
    speculativePlan: bool | None = None

    #: The Terraform version to use for the workspace. This must be a version that is installed on the Terraform
    #: Enterprise instance. If this is not specified, the default version will be used. Can be set to `latest` to
    #: use the latest version of Terraform always. If this is set to `None`, the latest version will be used on
    #: workspace creation and not be updated subsequently. If `autoQueue` is set to `True`, a version change will
    #: trigger a plan.
    terraformVersion: str | None = "latest"

    #: Automatically queue a plan when the workspace is created or updated. This is only relevant for the API-
    #: and VCS-driven workflows. If the workspace depends on another workspace, it will only be queued if the
    #: other workspaces have been successfully applied in their latest configuration.
    autoQueue: bool = False

    #: Apply mode.
    autoApply: AutoApplyType = AutoApplyType.NonDestrutiveOnly

    #: Enable drift assessments on the workspace. This can only be enabled for the VCS- and API-driven workflows.
    enableDriftAssessment: bool = False

    #: Permit the queueing of destroy plans for this workspace when the resource is deleted. If this is disabled,
    #: the resource will block until the workspace state is empty before it is removed from Terraform Enterprise.
    allowDestroyPlan: bool = False

    #: Force destry the workspace when the resource is removed. This will not queue a destroy plan and you will
    #: loose control over the resources that are managed by the workspace.
    forceDestroy: bool = False

    #: A list of tags to apply to the workspace. The reconciler may apply additional tags.
    tags: list[str] = field(default_factory=list)

    #: The name of the Terraform Enterprise project to assign the workspace to.
    project: str | None = None

    #: Whether structure run output is enabled.
    structuredRunOutputEnabled: bool = True

    #: The ID of the SSH Key in the organization that the workspace should use when cloning modules via Git.
    #: This can only be set in the remote execution mode.
    sshKey: str | None = None

    #: A list of variables to assign to the workspace. This can only be set for the remote execution mode.
    variables: list[Variable] = field(default_factory=list)

    #: A list of references to other resources that provide variables for the workspace. This can only be set
    #: for the remote execution mode. The other resources must be compatible providers of workspace variables.
    variablesFrom: list[VariablesFrom] = field(default_factory=list)

    #: A list of references to other resources that provide variables and provider initialization for the
    #: workspace. This can only be set for the remote execution mode. The other resources must be a compatible
    #: provider of workspace variables. This can only be set for the remote execution mode and API-driven
    #: workflow.
    providersFrom: list[ProviderFrom] = field(default_factory=list)

    #: Allow taking ownership of an existing workspace instead of erroring when the workspace already exists.
    takeOwnership: bool = False

    def get_working_directory(self) -> str | None:
        if self.vcsRepo is None:
            return None
        return self.vcsRepo.partition("//")[-1].partition("?")[0] or None

    # Resource.Spec

    def validate(self) -> None:
        # Validate the resource specification.
        match self.executionMode:
            case ExecutionMode.Local:
                assert self.workflow == WorkflowType.CliDriven, "workflow must be CliDriven in local execution mode."
                assert self.sshKey is None, "sshKey cannot be set for local execution mode."
                assert not self.variables, "variables cannot be set for local execution mode."
                assert not self.variablesFrom, "variablesFrom cannot be set for local execution mode."
                assert not self.providersFrom, "providersFrom cannot be set for local execution mode."
        match self.workflow:
            case WorkflowType.ApiDriven:
                if self.moduleConfiguration is not None:
                    assert self.moduleSource is None, "moduleSource cannot be combined with moduleConfiguration"
                    assert self.moduleVersion is None, "moduleVersion cannot be combined with moduleConfiguration"
                else:
                    assert (
                        self.moduleSource is not None
                    ), "moduleSource or moduleConfiguration must be set for API-driven workflows."
                assert self.vcsRepo is None, "vcsRepo must not be set for API-driven workflows."
                assert self.speculativePlan is None, "speculativePlan must not be set for CLI-driven workflows."
            case WorkflowType.CliDriven:
                assert self.moduleConfiguration is None, "moduleConfiguration must not be set for CLI-driven workflows."
                assert self.moduleSource is None, "moduleSource must not be set for CLI-driven workflows."
                assert self.moduleVersion is None, "moduleVersion must not be set for CLI-driven workflows."
                assert self.vcsRepo is None, "vcsRepo must not be set for CLI-driven workflows."
                assert self.speculativePlan is None, "speculativePlan must not be set for CLI-driven workflows."
                assert (
                    self.enableDriftAssessment is False
                ), "enableDriftAssessment cannot be set for CLI-driven workflows."
            case WorkflowType.VcsDriven:
                assert self.moduleConfiguration is None, "moduleConfiguration must not be set for VCS-driven workflows."
                assert self.moduleSource is None, "moduleSource must not be set for VCS-driven workflows."
                assert self.moduleVersion is None, "moduleVersion must not be set for VCS-driven workflows."
                assert self.vcsRepo is not None, "vcsRepo must be set for VCS-driven workflows."
        assert self.terraformVersion is None or re.match(
            TERRAFORM_VERSION_REGEX, self.terraformVersion
        ), "terraformVersion must be a valid Terraform version or `latest`."
        for tag in self.tags:
            assert re.match(TERRAFORM_TAG_REGEX, tag), f"tag {tag!r} is not a valid Terraform workspace tag."
        if self.providersFrom:
            assert self.workflow == WorkflowType.ApiDriven, "providersFrom can only be set for API-driven workflows."

        # Validate variable names don't overlap. We assume providers can generate unique variable names.
        variables: set[str] = set()
        for variable in self.variables:
            assert variable.name not in variables, f"variable {variable.name!r} is defined multiple times."
            variables.add(variable.name)
        for variablesFrom in self.variablesFrom:
            for variable_select in variablesFrom.select:
                assert (
                    variable_select.name not in variables
                ), f"variable {variable_select.name!r} is defined multiple times."
                variables.add(variable_select.name)


@dataclass
class TfeWorkspaceState(Resource.State):
    class Status(Enum):
        #: The last workspace creation or update was not successful.
        Invalid = "Invalid"

        #: The workspace is in good state and matches the last spec.
        Ok = "Ok"

        #: The workspace configuration has been updated but no plan has been queued yet. This is only relevant for
        #: the API- and VCS-driven workflows.
        ConfigDriftDetected = "ConfigDriftDetected"

        #: The workspace is waiting for another workspace that is a dependency to successfully apply.
        WaitingForDependency = "WaitingForDependency"

        #: The workspace state has drifted. This state is only set if #enableDriftAssessment is set to `True`.
        ResourceDriftDetected = "ResourceDriftDetected"

        #: The workspace is currently planning for applying.
        Planning = "Planning"

        #: The workspace is waiting for confirmation of a plan.
        PendingApproval = "PendingApproval"

        #: The workspace is currently applying.
        Applying = "Applying"

        #: The workspace is currently planning a destroy.
        PlanningDestroy = "PlanningDestroy"

        #: The workspace is waiting for confirmation of a destroy plan.
        PendingDestroyApproval = "PendingDestroyApproval"

        #: The workspace is currently destroying.
        Destroying = "Destroying"

        #: An error occurred while planning, applying or destroying.
        Errored = "Errored"

    organization: str
    workspaceName: str
    workspaceId: str | None
    status: Status | None = None
    lastUpdatedAt: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TfeWorkspaceController(
    CrudResourceController[TfeWorkspace, TfeWorkspaceState],
    spec_type=TfeWorkspace,
    state_type=TfeWorkspaceState,
):
    token: str
    url: str = "https://app.terraform.io"
    defaultOrganization: str | None = None
    defaultTags: list[str] = field(default_factory=lambda: ["equilibrium-managed"])

    def __post_init__(self) -> None:
        self._client = pyterprise.Client()
        self._client.init(token=self.token, url=self.url)

    def _get_workspace_name(self, resource: Resource[TfeWorkspace]) -> str:
        return resource.spec.name or f"{resource.metadata.namespace}-{resource.metadata.name}"

    def _get_organization(self, name: str | None) -> pyterprise.organization.Organization:
        name = name or self.defaultOrganization
        if name is None:
            orgs = self._client.list_organizations()
            if len(orgs) != 1:
                raise ValueError("No organization specified and multiple organizations available.")
            return orgs[0]
        return self._client.set_organization(name)

    def _get_tf_version(self, terraform_version: str | None) -> str:
        # TODO(@NiklasRosenstein): Query TFE for available TF versions.
        return "1.4.5"  # Latest we know today

    def _update_workspace(self, workspace: pyterprise.workspace.Workspace, spec: TfeWorkspace) -> None:
        # Check if the workspace tags need updating.
        # TODO(@NiklasRosenstein): Not supported by Pyterprise.
        # tags = set(spec.tags + self.defaultTags)
        # if tags != set(workspace.tags):
        #     pass
        pass

    def _update_state(self, workspace: pyterprise.workspace.Workspace, state: TfeWorkspaceState) -> None:
        state.organization = workspace.organization_name
        state.workspaceId = workspace.id
        state.lastUpdatedAt = datetime.now(timezone.utc)
        # TODO(@NiklasRosenstein): Set state status

    # CrudResourceController

    def create(self, resource: Resource[TfeWorkspace]) -> TfeWorkspaceState:
        spec = resource.spec

        organization = self._get_organization(spec.organization)
        workspace_name = self._get_workspace_name(resource)
        try:
            workspace: pyterprise.workspace.Workspace = organization.create_workspace(
                name=workspace_name,
                tf_version=self._get_tf_version(spec.terraformVersion),
                working_directory="",
                auto_apply=False,
                queue_all_runs=False,
                vcs_repo=None,
                trigger_prefixes=[],
            )
        except pyterprise.exceptions.APIException:
            if spec.takeOwnership:
                self.log.info("Taking ownership of existing workspace '%s'", workspace_name)
                workspace = organization.get_workspace(workspace_name)
            else:
                self.log.info("Workspace '%s' already exists", workspace_name)
                return TfeWorkspaceState(
                    organization.name,
                    workspace_name,
                    None,
                    status=TfeWorkspaceState.Status.Invalid,
                )
        try:
            self._update_workspace(workspace, spec)
            state = TfeWorkspaceState(organization.name, workspace_name, workspace.id)
            self._update_state(workspace, state)
            return state
        except Exception:
            self.log.exception("An unhandled exception occurred creating workspace '%s'", workspace_name)
            return TfeWorkspaceState(
                organization.name,
                workspace_name,
                None,
                status=TfeWorkspaceState.Status.Invalid,
            )

    def read(self, state: TfeWorkspaceState) -> TfeWorkspaceState | CrudResourceController.Status:
        organization = self._get_organization(state.organization)
        workspace = organization.get_workspace(state.workspaceName)
        self._update_state(workspace, state)
        return state

    def update(self, resource: Resource[TfeWorkspace], state: TfeWorkspaceState) -> TfeWorkspaceState:
        organization = self._get_organization(state.organization)
        workspace = organization.get_workspace(state.workspaceName)
        self._update_workspace(workspace, resource.spec)
        self._update_state(workspace, state)
        return state

    def delete(self, state: TfeWorkspaceState) -> TfeWorkspaceState | CrudResourceController.Status:
        self.log.info("Pending deletion of TFE workspace: ", state.organization, state.workspaceId)
        return state


class TfeResourceVariablesService(ABC):
    @abstractmethod
    def get_variables(self, uri: Resource.URI) -> list[Variable]:
        raise NotImplementedError(f"{self.__class__.__name__}.get_provider() is not implemented.")


class TfeResourceProviderService(ABC):
    @abstractmethod
    def get_provider(self, config: ProviderFrom) -> Provider:
        raise NotImplementedError(f"{self.__class__.__name__}.get_provider() is not implemented.")


def main() -> None:
    logging.basicConfig(
        level="NOTSET", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)]
    )
    ctx = Context.create(Context.JsonBackend("data"))
    ctx.resource_types.register(TfeWorkspace)
    ctx.controllers.register(TfeWorkspaceController(token=os.environ["TFE_TOKEN"]))
    ctx.resources.put(Namespace.create_resource("default"))
    ctx.resources.put(
        Resource.create(
            Resource.Metadata("default", "test"),
            TfeWorkspace(
                moduleSource="hashicorp/consul/aws",
                moduleVersion="0.0.1",
                takeOwnership=True,
            ),
        )
    )
    ctx.controllers.reconcile()


if __name__ == "__main__":
    main()
