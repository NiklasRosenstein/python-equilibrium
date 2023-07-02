import tempfile
import unittest
from pathlib import Path

from equilibrium.JsonResourceStore import JsonResourceStore
from equilibrium.Namespace import Namespace
from equilibrium.Resource import Resource
from equilibrium.ResourceStore_test import ResourceStoreTestSuite


class JsonResourceStoreTest(ResourceStoreTestSuite, unittest.TestCase):
    store: JsonResourceStore

    # TestCase overrides

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = self.create_store(Path(self.tempdir.name))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    # Helpers

    @staticmethod
    def create_store(tempdir: Path) -> JsonResourceStore:
        store = JsonResourceStore(tempdir)
        with store.enter(store.LockRequest()) as lock:
            store.put(lock, Namespace.create_resource("default"))
            store.put(lock, Namespace.create_resource("foobar", labels={"spam": "eggs"}))
            store.put(
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
            store.put(
                lock,
                Resource(
                    "apps/v1", "MultiResource", Resource.Metadata("foobar", "my-multi"), {"spam": "bar"}, None, None
                ),
            )
        return store

    # ResourceStoreTestSuite overrides

    def check_namespace_is_persisted(self, namespace: str) -> bool:
        return (self.store._directory / namespace).exists()

    def test__delete__last_entry(self) -> None:
        super().test__delete__last_entry()
        assert self.store._directory.exists()

    # Tests

    def test__namespaces__property_is_cached(self) -> None:
        assert self.store._namespaces is self.store._namespaces
