from __future__ import annotations

import io
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterator, Literal, Sequence, overload

PathLike = os.PathLike[str] | str


@dataclass
class _Directory:
    entries: dict[str, io.BytesIO | _Directory] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f'_Directory(entries.keys()={list(self.entries.keys())})'


class VirtualFilesystem:
    """
    Store generated files in memory before commiting them to disk at once.
    """

    def __init__(self, cwd: PathLike) -> None:
        self.cwd = Path(cwd)
        self.root = _Directory()

    def _full_path(self, path: PathLike) -> Path:
        return Path(os.path.normpath(self.cwd / path))

    def _get_entry(self, prefix: Path, parts: Sequence[str], parent: _Directory) -> io.BytesIO | _Directory:
        assert isinstance(prefix, Path)
        assert isinstance(parent, _Directory)
        if parts[0] == '/':
            parts = parts[1:]
        if not parts:
            return parent
        if parts[0] not in parent.entries:
            raise FileNotFoundError(prefix / parts[0])
        entry = parent.entries[parts[0]]
        if len(parts) > 1:
            if not isinstance(entry, _Directory):
                raise NotADirectoryError(prefix / parts[0])
            return self._get_entry(prefix / parts[0], parts[1:], entry)
        return entry

    def _mkdir(self, prefix: Path, parts: Sequence[str], parent: _Directory, parents: bool, exist_ok: bool) -> _Directory:
        print("mkdir", prefix, parts, parent, exist_ok)
        if parts[0] == '/':
            parts = parts[1:]
        if not parts:
            return parent

        entry = parent.entries.get(parts[0])
        if entry is not None and not isinstance(entry, _Directory):
            raise NotADirectoryError(prefix / parts[0])

        is_last = len(parts) == 1
        if entry is None and is_last or parents:
            entry = parent.entries[parts[0]] = _Directory()
        elif entry is not None:
            if not exist_ok:
                raise FileExistsError(prefix / parts[0])
        else:
            assert entry is None
            assert not is_last
            raise NotADirectoryError(prefix)
        if is_last:
            return entry
        return self._mkdir(prefix / parts[0], parts[1:], entry, parents, exist_ok)

    def iterdir(self, path: PathLike) -> Iterator[Path]:
        original_path = Path(path)
        path = self._full_path(path)
        entry = self._get_entry(Path("/"), path.parts, self.root)
        if isinstance(entry, _Directory):
            return (original_path / k for k in entry.entries.keys())
        raise NotADirectoryError(original_path)

    def mkdir(self, path: PathLike, *, parents: bool = False, exist_ok: bool = False) -> None:
        path = self._full_path(path)
        self._mkdir(Path("/"), path.parts, self.root, parents, exist_ok)

    def is_file(self, path: PathLike) -> bool:
        try:
            return not isinstance(self._get_entry(Path("/"), self._full_path(path).parts, self.root), _Directory)
        except (FileNotFoundError, NotADirectoryError):
            return False

    def is_dir(self, path: PathLike) -> bool:
        try:
            return isinstance(self._get_entry(Path("/"), self._full_path(path).parts, self.root), _Directory)
        except (FileNotFoundError, NotADirectoryError):
            return False

    @overload
    def open(  # type: ignore[misc]  # TODO(@niklas.rosenstein): Not sure what's wrong here with Mypy :(
        self,
        path: PathLike,
        mode: Literal["rb", "wb", "ab"] = "rb",
    ) -> io.BufferedIOBase:
        ...

    @overload
    def open(
        self,
        path: PathLike,
        mode: Literal["r", "w", "a"] = "r",
        encoding: str = "utf-8",
    ) -> io.TextIOBase:
        ...

    def open(
        self,
        path: PathLike,
        mode: Literal["r", "w", "a"] |  Literal["rb", "wb", "ab"] = "r",
        encoding: str = "utf-8",
    ) -> io.TextIOBase | io.BufferedIOBase:
        original_path = Path(path)
        path = self._full_path(path)

        if "r" in mode:
            if mode not in ("r", "rb"):
                raise ValueError(f"Invalid mode '{mode}'.")
            entry = self._get_entry(Path("/"), path.parts, self.root)
            if not isinstance(entry, io.BytesIO):
                raise FileNotFoundError(original_path.parent)
            fp = entry
            fp.seek(0, io.SEEK_SET)

        else:
            entry = self._get_entry(Path("/"), path.parent.parts, self.root)
            if not isinstance(entry, _Directory):
                raise NotADirectoryError(original_path.parent)
            if mode in ("w", "wb"):
                fp = entry.entries[path.name] = io.BytesIO()
            elif mode in ("a", "ab"):
                if path not in entry.entries:
                    fp = entry.entries[path.name] = io.BytesIO()
                else:
                    sub = entry.entries[path.name]
                    if isinstance(sub, _Directory):
                        raise IsADirectoryError(original_path)
                    fp = sub
                fp.seek(0, io.SEEK_END)
            else:
                raise ValueError(f"Invalid mode '{mode}'.")

        # We don't actually want our BytesIO to be closed.
        fp.close = lambda: None  # type: ignore[assignment]

        if "b" not in mode:
            return io.TextIOWrapper(fp, encoding=encoding)
        return fp
