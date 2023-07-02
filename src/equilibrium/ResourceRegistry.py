import logging
from contextlib import ExitStack
from typing import Any, TypeVar, overload

from equilibrium.AdmissionController import AdmissionController
from equilibrium.ControllerRegistry import ControllerRegistry
from equilibrium.NotSet import NotSet
from equilibrium.Resource import GenericResource, Resource
from equilibrium.ResourceStore import ResourceStore
from equilibrium.ResourceTypeRegistry import ResourceTypeRegistry
from equilibrium.ServiceRegistry import ServiceRegistry
from equilibrium.types import HashableMapping

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ResourceRegistry:
    """
    A high-level interface to the resource store, which can controls resource admission.
    """

    def __init__(
        self,
        store: ResourceStore,
        resource_types: ResourceTypeRegistry,
        controllers: ControllerRegistry,
        services: ServiceRegistry,
        default_namespace: str,
    ) -> None:
        self._store = store
        self._resource_types = resource_types
        self._controllers = controllers
        self._services = services
        self._default_namespace = default_namespace

    @property
    def store(self) -> ResourceStore:
        """
        Return the underlying resource store. It should be used by controllers when requiring more fine grained
        control over the resource store in a highly contested environment where many controllers concurrently
        need to access resources.
        """

        return self._store

    @overload
    def get(self, uri: Resource.URI) -> GenericResource:
        ...

    @overload
    def get(self, uri: Resource.URI, default: T) -> GenericResource | T:
        ...

    def get(self, uri: Resource.URI, default: T | NotSet = NotSet.Value) -> GenericResource | T:
        """
        Get a resource by full URI.
        """

        with self._store.enter(self._store.LockRequest.from_uri(uri)) as lock:
            result = self._store.get(lock, uri)
        if result is None:
            if default is NotSet.Value:
                raise Resource.NotFound(uri)
            return default
        return result

    def put(
        self,
        resource: Resource[Any],
        stateful: bool = False,
        existing_lock: ResourceStore.LockID | None = None,
    ) -> Resource[Any]:
        """
        Put a resource into the resource store. This will trigger the admission controllers. Any admission controller
        may complain about the resource, mutate it and raise an exception if necessary. This exception will propagate
        to the caller of #put().

        Note that this method does not permit a resource which has state unless the *stateful* flag is set to True.
        This method should only be used to update a resource's metadata and spec. The state will be inherited from
        existing resource, if it exists.

        If the *stateful* flag is set to True, the state of the resource will be committed to the resource store.
        Note that this also means that if the specified *resource* has no state, but the store currently does store
        a state for the resource, that state will be deleted.

        :param resource: The resource to put into the store.
        :param stateful: Allow writing the resource including its state into the store. This should only be used
                         when updating a resource's state.
        :param existing_lock: If an existing lock in the underlying #ResourceStore is already held by the caller,
                              it should be passed along to avoid acquiring a new lock.
        """

        if not stateful and resource.state is not None:
            raise ValueError("Cannot put a resource with state into the resource store")

        resource_spec = self._resource_types.get(resource.type)
        if resource_spec is None:
            raise ValueError(f"Unknown resource type: {resource.apiVersion}/{resource.kind}")

        # Ensure that we have the resource in its deserialized (i.e. non-generic) form.
        uri = resource.uri
        resource = resource.into(resource_spec)

        # Validate the resource spec.
        try:
            resource.spec.validate()
        except Exception as e:
            raise Resource.ValidationFailed(resource.uri, e) from e

        # Give the resource the default namespace.
        if uri.namespace is None and resource_spec.NAMESPACED:
            resource.metadata = resource.metadata.with_namespace(self._default_namespace)
            uri = resource.uri
        resource_spec.check_uri(resource.uri, do_raise=True)

        # Check for admission errors.
        resource = self._controllers.admit(AdmissionController.Context(self, self._services), resource)

        with ExitStack() as exit_stack:
            if existing_lock is None:
                lock = exit_stack.enter_context(self._store.enter(self._store.LockRequest.from_uri(uri)))
            else:
                lock = existing_lock

            if not stateful:
                # Inherit the state of an existing resource, if it exists.
                existing_resource = self._store.get(lock, uri)
                resource.state = existing_resource.state if existing_resource else None

            logger.debug("Putting resource '%s'.", uri)
            self._store.put(lock, resource.into_generic())

        return resource

    def delete(self, uri: Resource.URI, *, do_raise: bool = True, force: bool = False) -> bool:
        """
        Mark a resource as deleted. A controller must take care of actually removing it from the system.
        If *force* is True, the resource will be removed from the store immediately. If the resource is not found,
        a #Resource.NotFound error will be raised.

        If *do_raise* is False, this method will return False if the resource was not found.
        """

        with self._store.enter(self._store.LockRequest.from_uri(uri)) as lock:
            resource = self._store.get(lock, uri)
            if resource is None:
                logger.info("Could not delete Resource '%s', not found.", uri)
                if do_raise:
                    raise Resource.NotFound(uri)
                return False
            if force:
                logger.info("Force deleting resource '%s'.", uri)
                self._store.delete(lock, uri)
            elif resource.deletion_marker is None:
                logger.info("Marking resource '%s' as deleted.", uri)
                resource.deletion_marker = Resource.DeletionMarker()
                self._store.put(lock, resource)
            else:
                logger.info("Resource '%s' is already marked as deleted.", uri)
            return True

    def search(
        self,
        *,
        apiVersion: str | None = None,
        kind: str | None = None,
        namespace: str | None = "",
        name: str | None = None,
        labels: HashableMapping[str, str] | None = None,
    ) -> list[Resource.URI]:
        """
        Search for resources of the given type. If *namespace* is `""`, all namespaces and unnamespaced resources will
        be searched. If *namespace* is `None`, only unnamespaced resources will be searched. If *name* is given, only
        resources with that name will be returned.
        """

        with self._store.enter(self._store.LockRequest(apiVersion, kind, namespace, name)) as lock:
            return list(
                self._store.search(
                    lock,
                    self._store.SearchRequest(
                        apiVersion,
                        kind,
                        namespace,
                        name,
                        labels,
                    ),
                )
            )

    def list(
        self,
        spec_type: type[Resource.T_Spec],
        *,
        namespace: str | None = "",
        name: str | None = None,
        labels: HashableMapping[str, str] | None = None,
    ) -> list[Resource[Resource.T_Spec]]:
        """
        Combines #search() and #get() to return a list of resources of the given type.
        """

        with self._store.enter(self._store.LockRequest(spec_type.API_VERSION, spec_type.KIND, namespace, name)) as lock:
            uris = self._store.search(
                lock,
                self._store.SearchRequest(
                    spec_type.API_VERSION,
                    spec_type.KIND,
                    namespace,
                    name,
                    labels,
                ),
            )
            result = []
            for uri in uris:
                resource = self._store.get(lock, uri)
                if resource is not None:
                    result.append(resource.into(spec_type))
        return result
