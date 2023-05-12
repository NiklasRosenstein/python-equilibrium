import logging
from abc import abstractmethod
from enum import Enum
from logging import Logger
from typing import Any, ClassVar, Generic

from equilibrium.resource.AdmissionController import AdmissionController
from equilibrium.resource.Resource import Resource
from equilibrium.resource.ResourceController import ResourceController
from equilibrium.resource.ResourceStore import ResourceStore

__all__ = ["CrudResourceController"]


class CrudResourceController(ResourceController, AdmissionController, Generic[Resource.T_Spec, Resource.T_State]):
    """
    A base class for resource controllers that follow a CRUD pattern and may also control admittance.
    """

    spec_type: type[Resource.T_Spec]
    state_type: type[Resource.T_State]
    _logger_name: ClassVar[str]
    log: Logger

    class Status(Enum):
        Deleted = "deleted"

    Deleted = Status.Deleted

    def __init_subclass__(
        cls,
        spec_type: type[Resource.T_Spec],
        state_type: type[Resource.T_State],
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        cls._logger_name = f"{cls.__module__}.{cls.__name__}"
        cls.spec_type = spec_type
        cls.state_type = state_type

    def admit(self, resource: Resource[Resource.T_Spec]) -> Resource[Resource.T_Spec]:
        """
        Test for the admission of the resource into the system. A potentially modified version is returned. An
        exception shall be raised if the resource cannot be admitted to the system. If the previous spec of the
        resource is of interest, it can be retrieved with the #resources manager.
        """

        return resource

    @abstractmethod
    def create(self, resource: Resource[Resource.T_Spec]) -> Resource.T_State:
        """Create the resource. This is called only if *resource* was previously unknown to the system."""

    @abstractmethod
    def read(self, state: Resource.T_State) -> Resource.T_State | Status:
        """Update the known state of the resource. This is called always before #update() and #delete()."""

    @abstractmethod
    def update(self, resource: Resource[Resource.T_Spec], state: Resource.T_State) -> Resource.T_State:
        """Update the state of the managed resource. This embodies the main reconcilation logic."""

    @abstractmethod
    def delete(self, state: Resource.T_State) -> Resource.T_State | Status:
        """
        Delete a resource. This is called if a resource no longer exists in the system. Must return the resource
        state if the deletion is in progress after the call. When the resource is finally deleted, the method
        returns None.
        """

    def _get_logger(self, uri: Resource.URI | None) -> Logger:
        log = logging.getLogger(self._logger_name)
        if uri:
            log = log.getChild(str(uri))
        return log

    def _reconcile_internal(self, lock: ResourceStore.LockID, uri: Resource.URI) -> None:
        log = self._get_logger(uri)
        raw_resource = self.resources.get(lock, uri)
        if raw_resource is None:
            log.warning("Resource %r no longer exists, skipping reconciliation.", uri)
            return

        log.debug("Reconciling resource '%s'.", uri)
        try:
            resource: Resource[Resource.T_Spec] = raw_resource.into(self.spec_type)
            current_state: Resource.T_State | None = (
                resource.get_state(self.state_type) if resource.state is not None else None
            )

            if current_state is not None:
                log.debug("Resource '%s' has state, reading the latest.", uri)
                response = self.read(resource.get_state(self.state_type))
                if response is self.Deleted:
                    current_state = None
                elif not isinstance(response, self.state_type):
                    raise RuntimeError(
                        f"{type(self).__name__}.read() is expected to return an object of type "
                        f"{self.state_type.__name__} or Status.Deleted, got {type(response).__name__} instead."
                    )
                else:
                    current_state = response

            if current_state is None and resource.deletion_marker:
                log.debug(
                    "Resource '%s' is marked for deletion and has no current state, skipping reconciliation.", uri
                )
            elif current_state is None:
                if resource.state is None:
                    log.debug("Resource '%s' is new, creating it.", uri)
                else:
                    log.debug("Resource '%s' was lost, creating it.", uri)

                current_state = self.create(resource)
                if not isinstance(current_state, self.state_type):
                    raise RuntimeError(
                        f"{type(self).__name__}.create() is expected to return an object of type "
                        f"{self.state_type.__name__}, got {type(current_state).__name__} instead."
                    )
            else:
                if resource.deletion_marker:
                    log.debug("Resource '%s' is marked for deletion.", uri)
                    response = self.delete(resource.get_state(self.state_type))
                    if response is self.Deleted:
                        current_state = None
                    elif not isinstance(response, self.state_type):
                        raise RuntimeError(
                            f"{type(self).__name__}.delete() is expected to return an object of type "
                            f"{self.state_type.__name__} or Status.Deleted, got {type(response).__name__} instead."
                        )
                    else:
                        current_state = response
                else:
                    log.debug("Resource '%s' is not marked for deletion, updating it.", uri)
                    current_state = self.update(resource, current_state)
                    if not isinstance(current_state, self.state_type):
                        raise RuntimeError(
                            f"{type(self).__name__}.update() is expected to return an object of type "
                            f"{self.state_type.__name__}, got {type(current_state).__name__} instead."
                        )

            if current_state is None:
                log.debug("Resource '%s' has been deleted.", uri)
                self.resources.delete(lock, uri)
            else:
                log.debug("Resource '%s' has been updated.", uri)
                resource.set_state(self.state_type, current_state)
                self.resources.put(lock, resource.into_generic())

        except Exception:
            log.exception("An unhandled exception occurred reconciling a resource.")

    # ResourceController

    def reconcile(self) -> None:
        self.log = self._get_logger(None)

        namespaces = self.resources.namespaces()
        self.log.info(
            "Reconciling resources of type '%s' (namespaces: %r)",
            self.spec_type.TYPE,
            {ns.metadata.name for ns in namespaces},
        )
        for namespace in namespaces:
            lock_request = self.resources.LockRequest(apiVersion=self.spec_type.API_VERSION, kind=self.spec_type.KIND)
            with self.resources.enter(lock_request) as lock:
                search_request = self.resources.SearchRequest(
                    apiVersion=self.spec_type.API_VERSION,
                    kind=self.spec_type.KIND,
                    namespace=namespace.metadata.name,
                )
                resource_uris = self.resources.search(lock, search_request)

            self.log.debug(
                "Found %d resources of type '%s' in namespace '%s'.",
                len(resource_uris),
                self.spec_type.TYPE,
                namespace.metadata.name,
            )
            for uri in resource_uris:
                lock_request = self.resources.LockRequest.from_uri(uri)
                with self.resources.enter(lock_request) as lock:
                    self._reconcile_internal(lock, uri)

    # AdmissionController

    def admit_resource(self, resource: Resource[Any]) -> Resource[Any]:
        if self.spec_type.check_uri(resource.uri):
            self.log = self._get_logger(resource.uri)
            self.log.debug("Checking for admittance of resource '%s'.", resource.uri)
            return self.admit(resource.into(self.spec_type))
        return resource
