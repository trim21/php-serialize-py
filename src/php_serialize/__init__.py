"""
This file is copied and modified from https://github.com/mitsuhiko/phpserialize

Licensed under bsd 3-clause license
<https://github.com/mitsuhiko/phpserialize/blob/master/LICENSE>

Copyright 2021-2022 by Trim21 <trim21.me@gmail.com>
Copyright 2007-2016 by Armin Ronacher.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Any

from typing_extensions import Buffer

COMPILED = Path(__file__).suffix in (".pyd", ".so")

__all__ = (
    "dict_to_list",
    "loads",
    "dumps",
    "PHPSerializeError",
    "COMPILED",
)


def loads(data: Buffer | str) -> Any:
    """Read a PHP-serialized object hierarchy from a string.  Characters in the
    string past the object's representation are ignored.  On Python 3 the
    string must be a bytestring.
    """
    with BytesIO(__ensure_binary(data)) as fp:
        return Decoder(fp).decode()


def dict_to_list(d: dict[int, Any]) -> list[Any]:
    """Converts an ordered dict into a list."""
    # make sure it's a dict, that way dict_to_list can be used as an
    # array_hook.
    try:
        return [d[x] for x in range(len(d))]
    except KeyError as e:  # pragma: no cover
        raise ValueError("dict is not a sequence") from e


class PHPSerializeError(Exception):
    """Bencode encode error."""


def dumps(value: Any, /) -> bytes:
    """Encode value into the phpserialize format."""
    with BytesIO() as r:
        __encode(value, r, set())
        return r.getvalue()


class Decoder:
    def __init__(self, fp: BytesIO) -> None:
        self.fp = fp

    def __expect(self, e: bytes) -> None:
        v = self.fp.read(len(e))
        if v != e:  # pragma: no cover
            raise ValueError(f"failed expectation, expected {e!r} got {v!r}")

    def __read_until(self, delim: bytes) -> bytes:
        buf = []
        while 1:
            char = self.fp.read(1)
            if char == delim:
                break
            if not char:  # pragma: no cover
                raise ValueError("unexpected end of stream")
            buf.append(char)
        return b"".join(buf)

    def __load_array(self) -> list[Any]:
        item_count = int(self.__read_until(b":"))

        self.__expect(b"{")

        result = []

        for _ in range(item_count):
            key = self.__decode()
            value = self.__decode()
            result.append((key, value))

        self.__expect(b"}")
        return result

    def __decode(self) -> Any:
        opcode = self.fp.read(1)
        if opcode == b"N":
            self.__expect(b";")
            return None
        if opcode in b"idb":
            self.__expect(b":")
            data = self.__read_until(b";")
            if opcode == b"i":
                return int(data)
            if opcode == b"d":
                return float(data)
            return data != b"0"
        if opcode == b"s":
            self.__expect(b":")
            length = int(self.__read_until(b":"))
            self.__expect(b'"')
            s = self.fp.read(length).decode()
            self.__expect(b'"')
            self.__expect(b";")
            return s
        if opcode == b"a":
            self.__expect(b":")
            return dict(self.__load_array())
        if opcode in (b"O", b"C"):
            raise ValueError("deserialize php object is not allowed")
        raise ValueError(f"unexpected opcode {opcode!r}")  # pragma: no cover

    def decode(self) -> Any:
        val = self.__decode()
        if self.fp.read(1):
            raise ValueError("extra data")
        return val


def __encode(value: Any, r: BytesIO, seen: set[int]) -> None:
    if isinstance(value, str):
        return __encode_bytes(value.encode("utf8"), r)

    if isinstance(value, int):
        return __encode_int(value, r)

    if isinstance(value, float):
        r.write(f"d:{value};".encode())
        return None

    if isinstance(value, bytes):
        return __encode_bytes(value, r)

    if isinstance(value, bool):
        if value:
            r.write(b"b:1;")
        else:
            r.write(b"b:0;")
        return None

    if value is None:
        r.write(b"N;")
        return None

    i = id(value)
    if isinstance(value, (dict, OrderedDict, MappingProxyType)):
        if i in seen:
            raise PHPSerializeError(f"circular reference found {value!r}")
        seen.add(i)
        __encode_mapping(value, r, seen)
        seen.remove(i)
        return None

    if isinstance(value, (list, tuple)):
        if i in seen:
            raise PHPSerializeError(f"circular reference found {value!r}")
        seen.add(i)

        r.write(f"a:{len(value)}:{{".encode())
        for index, item in enumerate(value):
            __encode_int(index, r)
            __encode(item, r, seen)
        r.write(b"}")

        seen.remove(i)
        return None

    if isinstance(value, bytearray):
        __encode_bytes(bytes(value), r)
        return None

    raise TypeError(f"type '{type(value)!r}' not supported")


def __encode_int(value: int, r: BytesIO) -> None:
    r.write(b"i:")
    # will handle bool and enum.IntEnum
    r.write(str(int(value)).encode())
    r.write(b";")


def __encode_bytes(x: bytes, r: BytesIO) -> None:
    r.write(b"s:")
    r.write(str(len(x)).encode())
    r.write(b':"')
    r.write(x)
    r.write(b'";')


def __encode_mapping(x: Mapping[Any, Any], r: BytesIO, seen: set[int]) -> None:
    r.write(b"a:")
    r.write(str(len(x)).encode())
    r.write(b":{")

    # force all keys to bytes, because str and bytes are incomparable
    for k, v in x.items():
        __encode_bytes(__key_to_binary(k), r)
        __encode(v, r, seen)

    r.write(b"}")


def __check_duplicated_keys(s: list[tuple[bytes, object]]) -> None:
    last_key: bytes = s[0][0]
    for current, _ in s[1:]:
        if last_key == current:
            raise PHPSerializeError(
                f"find duplicated keys {last_key!r} and {current.decode()}"
            )
        last_key = current


def __key_to_binary(key: Any) -> bytes:
    if isinstance(key, bytes):
        return key

    if isinstance(key, str):
        return key.encode()

    if isinstance(key, int):
        return str(key).encode()

    if key is None:
        return b""

    raise TypeError(f"expected value as dict key {key!r}")


def __ensure_binary(s: str | Buffer) -> Buffer:
    if isinstance(s, str):
        return s.encode()
    return s
