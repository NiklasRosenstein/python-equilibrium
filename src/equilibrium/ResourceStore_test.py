from abc import ABC, abstractmethod
from threading import Thread

from pytest import raises

from equilibrium.Namespace import Namespace
from equilibrium.Resource import Resource
from equilibrium.ResourceStore import ResourceStore

URI = Resource.URI
LockID = ResourceStore.LockID


class ResourceStoreTestSuite(ABC):
    """
    Common tests that all #ResourceStore implementations should satisfy.
    """

    store: ResourceStore

    def setUp(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            self.store.put(lock, Namespace.create_resource("default").into_generic())
            self.store.put(lock, Namespace.create_resource("foobar", labels={"spam": "eggs"}).into_generic())
            self.store.put(
                lock,
                Resource(
                    "v1",
                    "MyResource",
                    Resource.Metadata("default", "my-resource", labels={"foo": "bar"}),
                    {},
                    None,
                    {"state": "active"},
                ),
            )
            self.store.put(
                lock,
                Resource(
                    "apps/v1", "MultiResource", Resource.Metadata("foobar", "my-multi"), {"spam": "bar"}, None, None
                ),
            )

    def test__enter__permits_reentry(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock1, self.store.enter(self.store.LockRequest()) as lock2:
            assert lock1 == lock2

    def test__enter__does_not_permit_reentry_from_another_thread(self) -> None:
        with self.store.enter(self.store.LockRequest()):
            success = False

            def _thread() -> None:
                nonlocal success
                with raises(TimeoutError):
                    with self.store.enter(self.store.LockRequest(timeout=0.5)):
                        pass
                success = True

            thread = Thread(target=_thread)
            thread.start()
            thread.join()
            assert success, "Thread did not raise TimeoutError"

    def test__enter__immediately_returns_when_block_is_false(self) -> None:
        with self.store.enter(self.store.LockRequest()):
            success = False

            def _thread() -> None:
                nonlocal success
                with raises(TimeoutError):
                    with self.store.enter(self.store.LockRequest(block=False)) as lock:
                        assert lock is None
                success = True

            thread = Thread(target=_thread)
            thread.start()
            thread.join()
            assert success, "Thread did not raise TimeoutError"

    def test__get(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert self.store.get(lock, URI("v1", "MyResource", "default", "my-resource")) == Resource(
                "v1",
                "MyResource",
                Resource.Metadata("default", "my-resource", labels={"foo": "bar"}),
                {},
                None,
                {"state": "active"},
            )

    def test__search__all(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert set(self.store.search(lock, self.store.SearchRequest())) == {
                URI("v1", "Namespace", None, "default"),
                URI("v1", "Namespace", None, "foobar"),
                URI("v1", "MyResource", "default", "my-resource"),
                URI("apps/v1", "MultiResource", "foobar", "my-multi"),
            }

    def test__search__by_apiVersion(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert set(self.store.search(lock, self.store.SearchRequest(apiVersion="v1"))) == {
                URI("v1", "Namespace", None, "default"),
                URI("v1", "Namespace", None, "foobar"),
                URI("v1", "MyResource", "default", "my-resource"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(apiVersion="apps/v1"))) == {
                URI("apps/v1", "MultiResource", "foobar", "my-multi"),
            }

    def test__search__by_kind(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert set(self.store.search(lock, self.store.SearchRequest(kind="Namespace"))) == {
                URI("v1", "Namespace", None, "default"),
                URI("v1", "Namespace", None, "foobar"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(kind="MyResource"))) == {
                URI("v1", "MyResource", "default", "my-resource"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(kind="MultiResource"))) == {
                URI("apps/v1", "MultiResource", "foobar", "my-multi"),
            }

    def test__search__by_namespace(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert set(self.store.search(lock, self.store.SearchRequest(namespace=None))) == {
                URI("v1", "Namespace", None, "default"),
                URI("v1", "Namespace", None, "foobar"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(namespace="default"))) == {
                URI("v1", "MyResource", "default", "my-resource"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(namespace="foobar"))) == {
                URI("apps/v1", "MultiResource", "foobar", "my-multi"),
            }

    def test__search__by_name(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert set(self.store.search(lock, self.store.SearchRequest(name="default"))) == {
                URI("v1", "Namespace", None, "default"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(name="my-resource"))) == {
                URI("v1", "MyResource", "default", "my-resource"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(name="my-multi"))) == {
                URI("apps/v1", "MultiResource", "foobar", "my-multi"),
            }

    def test__search__by_labels(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert set(self.store.search(lock, self.store.SearchRequest(labels={"spam": "eggs"}))) == {
                URI("v1", "Namespace", None, "foobar"),
            }
            assert set(self.store.search(lock, self.store.SearchRequest(labels={"foo": "bar"}))) == {
                URI("v1", "MyResource", "default", "my-resource"),
            }
            assert set(
                self.store.search(lock, self.store.SearchRequest(namespace="default", labels={"foo": "bar"}))
            ) == {
                URI("v1", "MyResource", "default", "my-resource"),
            }
            assert (
                set(self.store.search(lock, self.store.SearchRequest(namespace="foobar", labels={"foo": "bar"})))
                == set()
            )

    def test__delete(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert self.store.delete(lock, URI("v1", "MyResource", "default", "my-resource"))
            assert set(self.store.search(lock, self.store.SearchRequest())) == {
                URI("v1", "Namespace", None, "default"),
                URI("v1", "Namespace", None, "foobar"),
                URI("apps/v1", "MultiResource", "foobar", "my-multi"),
            }
            assert self.store.get(lock, URI("v1", "MyResource", "default", "my-resource")) is None

            # Entry already deleted
            assert not self.store.delete(lock, URI("v1", "MyResource", "default", "my-resource"))

    def test__delete__last_entry(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert self.check_namespace_is_persisted("foobar")
            assert self.store.delete(lock, URI("apps/v1", "MultiResource", "foobar", "my-multi"))
            assert set(self.store.search(lock, self.store.SearchRequest())) == {
                URI("v1", "Namespace", None, "default"),
                URI("v1", "Namespace", None, "foobar"),
                URI("v1", "MyResource", "default", "my-resource"),
            }
            assert not self.check_namespace_is_persisted("foobar")

    def test__delete__cannot_delete_nonempty_namespace(self) -> None:
        with self.store.enter(self.store.LockRequest()) as lock:
            assert self.check_namespace_is_persisted("default")
            with raises(self.store.NamespaceNotEmpty):
                self.store.delete(lock, URI("v1", "Namespace", None, "default"))
            self.store.delete(lock, URI("v1", "MyResource", "default", "my-resource"))
            assert self.store.delete(lock, URI("v1", "Namespace", None, "default"))
            assert not any(self.store.search(lock, self.store.SearchRequest(namespace="default")))
            assert set(self.store.search(lock, self.store.SearchRequest())) == {
                URI("v1", "Namespace", None, "foobar"),
                URI("apps/v1", "MultiResource", "foobar", "my-multi"),
            }

    # Assertion callbacks

    @abstractmethod
    def check_namespace_is_persisted(self, namespace: str) -> bool:
        pass
