from typing import Any, Callable

Hasher = Callable[[Any], int]


class HashSupport:
    """
    A helper class that supports in hashing objects. Usually it just defaults to the native #hash() function, but
    some otherwise unhashable types can be made hashable by providing a custom hash function.
    """

    def __init__(self) -> None:
        self._custom_hashers: dict[type, Hasher] = {}

    def register(self, type_: type, hash_function: Hasher) -> None:
        """
        Register a custom hash function for the given type.
        """

        self._custom_hashers[type_] = hash_function

    def __call__(self, obj: Any) -> int:
        """
        Hash the given object.
        """

        try:
            hash_func = self._custom_hashers[type(obj)]
        except KeyError:
            hash_func = hash
        return hash_func(obj)
