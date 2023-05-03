from pathlib import Path

from equilibrium.codegen.VirtualFilesystem import VirtualFilesystem
from pytest import raises


def test__Path__parts_on_absolute_path() -> None:
    assert Path("/foo/bar").parts == ("/", "foo", "bar")


def test__VirtualFilesystem__iterdir__fresh_vfs_is_empty() -> None:
    vfs = VirtualFilesystem("/")
    assert not any(vfs.iterdir("."))
    vfs = VirtualFilesystem(".")
    assert not any(vfs.iterdir("."))
    vfs = VirtualFilesystem("/foo")
    assert not any(vfs.iterdir("."))


def test__VirtualFilesystem__iterdir__create_file_in_directory() -> None:
    vfs = VirtualFilesystem("/foo")
    vfs.mkdir(".")

    assert not any(vfs.iterdir("."))
    with vfs.open("foo", "w") as fp:
        fp.write("Hello World!")
    assert list(vfs.iterdir(".")) == [Path("foo")]
    with vfs.open("bar", "w") as fp:
        fp.write("Hello World!")
    assert sorted(vfs.iterdir(".")) == [Path("bar"), Path("foo")]

    with vfs.open("spam/baz", "w") as fp:
        fp.write("Hello World!")
    assert sorted(vfs.iterdir(".")) == [Path("bar"), Path("foo"), Path("spam")]
    assert sorted(vfs.iterdir("spam")) == [Path("spam/baz")]


def test__VirtualFilesystem__open__cannot_create_file_under_file() -> None:
    vfs = VirtualFilesystem("/foo")
    with raises(FileNotFoundError):
        any(vfs.iterdir("."))
    vfs.mkdir("/foo")
    assert list(vfs.iterdir(".")) == []

    with vfs.open("foo", "w") as fp:
        fp.write("Hello World!")
    assert list(vfs.iterdir(".")) == [Path("foo")]
    assert list(vfs.iterdir("/foo")) == [Path("/foo/foo")]
    assert vfs.open("/foo/foo", "r").read() == "Hello World!"

    with raises(NotADirectoryError):
        with vfs.open("foo/bar", "w") as fp:
            fp.write("Hello World!")
    with raises(NotADirectoryError):
        vfs.mkdir("foo")
