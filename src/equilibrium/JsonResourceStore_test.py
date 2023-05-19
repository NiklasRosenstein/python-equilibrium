import tempfile
from pathlib import Path
from threading import Thread
from typing import Iterator

import pytest

from equilibrium.JsonResourceStore import JsonResourceStore
from equilibrium.Namespace import Namespace
from equilibrium.Resource import Resource

LockID = JsonResourceStore.LockID


@pytest.fixture
def tempdir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sut(tempdir: Path) -> JsonResourceStore:
    mgr = JsonResourceStore(tempdir)
    with mgr.enter(mgr.LockRequest()) as lock:
        mgr.put(lock, Namespace.create_resource("default"))
        mgr.put(lock, Namespace.create_resource("foobar", labels={"spam": "eggs"}))
        mgr.put(
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
        mgr.put(
            lock,
            Resource("apps/v1", "MultiResource", Resource.Metadata("foobar", "my-multi"), {"spam": "bar"}, None, None),
        )
    return mgr


@pytest.fixture
def lock(sut: JsonResourceStore) -> Iterator[LockID]:
    with sut.enter(sut.LockRequest()) as lock:
        yield lock


def test__JsonResourceStore___namespaces__property_is_cached(sut: JsonResourceStore, lock: LockID) -> None:
    assert sut._namespaces is sut._namespaces


def test__JsonResourceStore__enter__permits_reentry(sut: JsonResourceStore, lock: LockID) -> None:
    with sut.enter(sut.LockRequest()) as new_lock:
        assert new_lock == lock


def test__JsonResourceStore__enter__does_not_permit_reentry_from_another_thread(
    sut: JsonResourceStore, lock: LockID
) -> None:
    success = False

    def _thread() -> None:
        nonlocal success
        with pytest.raises(TimeoutError):
            with sut.enter(sut.LockRequest(timeout=0.5)):
                pass
        success = True

    thread = Thread(target=_thread)
    thread.start()
    thread.join()
    assert success, "Thread did not raise TimeoutError"


def test__JsonResourceStore__enter__immediately_returns_when_block_is_false(
    sut: JsonResourceStore, lock: LockID
) -> None:
    success = False

    def _thread() -> None:
        nonlocal success
        with pytest.raises(TimeoutError):
            with sut.enter(sut.LockRequest(block=False)) as lock:
                assert lock is None
        success = True

    thread = Thread(target=_thread)
    thread.start()
    thread.join()
    assert success, "Thread did not raise TimeoutError"


def test__JsonResourceStore__get(sut: JsonResourceStore, lock: LockID) -> None:
    assert sut.get(lock, Resource.URI("v1", "MyResource", "default", "my-resource")) == Resource(
        "v1",
        "MyResource",
        Resource.Metadata("default", "my-resource", labels={"foo": "bar"}),
        {},
        None,
        {"state": "active"},
    )


def test__JsonResourceStore__search__all(sut: JsonResourceStore, lock: LockID) -> None:
    assert set(sut.search(lock, sut.SearchRequest())) == {
        Resource.URI("v1", "Namespace", None, "default"),
        Resource.URI("v1", "Namespace", None, "foobar"),
        Resource.URI("v1", "MyResource", "default", "my-resource"),
        Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"),
    }


def test__JsonResourceStore__search__by_apiVersion(sut: JsonResourceStore, lock: LockID) -> None:
    assert set(sut.search(lock, sut.SearchRequest(apiVersion="v1"))) == {
        Resource.URI("v1", "Namespace", None, "default"),
        Resource.URI("v1", "Namespace", None, "foobar"),
        Resource.URI("v1", "MyResource", "default", "my-resource"),
    }
    assert set(sut.search(lock, sut.SearchRequest(apiVersion="apps/v1"))) == {
        Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"),
    }


def test__JsonResourceStore__search__by_kind(sut: JsonResourceStore, lock: LockID) -> None:
    assert set(sut.search(lock, sut.SearchRequest(kind="Namespace"))) == {
        Resource.URI("v1", "Namespace", None, "default"),
        Resource.URI("v1", "Namespace", None, "foobar"),
    }
    assert set(sut.search(lock, sut.SearchRequest(kind="MyResource"))) == {
        Resource.URI("v1", "MyResource", "default", "my-resource"),
    }
    assert set(sut.search(lock, sut.SearchRequest(kind="MultiResource"))) == {
        Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"),
    }


def test__JsonResourceStore__search__by_namespace(sut: JsonResourceStore, lock: LockID) -> None:
    assert set(sut.search(lock, sut.SearchRequest(namespace=None))) == {
        Resource.URI("v1", "Namespace", None, "default"),
        Resource.URI("v1", "Namespace", None, "foobar"),
    }
    assert set(sut.search(lock, sut.SearchRequest(namespace="default"))) == {
        Resource.URI("v1", "MyResource", "default", "my-resource"),
    }
    assert set(sut.search(lock, sut.SearchRequest(namespace="foobar"))) == {
        Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"),
    }


def test__JsonResourceStore__search__by_name(sut: JsonResourceStore, lock: LockID) -> None:
    assert set(sut.search(lock, sut.SearchRequest(name="default"))) == {
        Resource.URI("v1", "Namespace", None, "default"),
    }
    assert set(sut.search(lock, sut.SearchRequest(name="my-resource"))) == {
        Resource.URI("v1", "MyResource", "default", "my-resource"),
    }
    assert set(sut.search(lock, sut.SearchRequest(name="my-multi"))) == {
        Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"),
    }


def test__JsonResourceStore__search__by_labels(sut: JsonResourceStore, lock: LockID) -> None:
    assert set(sut.search(lock, sut.SearchRequest(labels={"spam": "eggs"}))) == {
        Resource.URI("v1", "Namespace", None, "foobar"),
    }
    assert set(sut.search(lock, sut.SearchRequest(labels={"foo": "bar"}))) == {
        Resource.URI("v1", "MyResource", "default", "my-resource"),
    }
    assert set(sut.search(lock, sut.SearchRequest(namespace="default", labels={"foo": "bar"}))) == {
        Resource.URI("v1", "MyResource", "default", "my-resource"),
    }
    assert set(sut.search(lock, sut.SearchRequest(namespace="foobar", labels={"foo": "bar"}))) == set()


def test__JsonResourceStore__delete(sut: JsonResourceStore, lock: LockID) -> None:
    assert sut.delete(lock, Resource.URI("v1", "MyResource", "default", "my-resource"))
    assert set(sut.search(lock, sut.SearchRequest())) == {
        Resource.URI("v1", "Namespace", None, "default"),
        Resource.URI("v1", "Namespace", None, "foobar"),
        Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"),
    }
    assert sut.get(lock, Resource.URI("v1", "MyResource", "default", "my-resource")) is None

    # Entry already deleted
    assert not sut.delete(lock, Resource.URI("v1", "MyResource", "default", "my-resource"))


def test__JsonResourceStore__delete__last_entry(sut: JsonResourceStore, lock: LockID) -> None:
    assert (sut._directory / "foobar").exists()
    assert sut.delete(lock, Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"))
    assert set(sut.search(lock, sut.SearchRequest())) == {
        Resource.URI("v1", "Namespace", None, "default"),
        Resource.URI("v1", "Namespace", None, "foobar"),
        Resource.URI("v1", "MyResource", "default", "my-resource"),
    }
    assert not (sut._directory / "foobar").exists()
    assert sut._directory.exists()


def test__JsonResourceStore__delete__cannot_delete_nonempty_namespace(sut: JsonResourceStore, lock: LockID) -> None:
    assert (sut._directory / "default").exists()
    with pytest.raises(sut.NamespaceNotEmpty):
        sut.delete(lock, Resource.URI("v1", "Namespace", None, "default"))
    sut.delete(lock, Resource.URI("v1", "MyResource", "default", "my-resource"))
    assert sut.delete(lock, Resource.URI("v1", "Namespace", None, "default"))
    assert not any(sut.search(lock, sut.SearchRequest(namespace="default")))
    assert set(sut.search(lock, sut.SearchRequest())) == {
        Resource.URI("v1", "Namespace", None, "foobar"),
        Resource.URI("apps/v1", "MultiResource", "foobar", "my-multi"),
    }
