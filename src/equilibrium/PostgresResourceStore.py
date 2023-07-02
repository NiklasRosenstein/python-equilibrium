import logging
from dataclasses import dataclass

import psycopg2

from equilibrium.Namespace import Namespace
from equilibrium.Resource import GenericResource, Resource
from equilibrium.ResourceStore import ResourceStore

logger = logging.getLogger(__name__)
LockRequest = ResourceStore.LockRequest
LockID = ResourceStore.LockID
SearchRequest = ResourceStore.SearchRequest
URI = Resource.URI


class PostgresResourceStore(ResourceStore):
    """
    This is an implementation of a resource store that stores data in a PostgreSQL tables.
    """

    CURRENT_SCHEMA_VERSION = 1

    @dataclass
    class ConnectionParams:
        user: str
        password: str
        host: str
        dbname: str
        port: int = 5432

    def __init__(self, params: ConnectionParams, table_name: str) -> None:
        self._db = psycopg2.connect(
            host=params.host,
            port=params.port,
            dbname=params.dbname,
            user=params.user,
            password=params.password,
        )
        self._table_name = table_name

    def initialize(self) -> None:
        """
        Creates the table and indices for storing Equlibrium resources if it does not exist.
        """

        cursor = self._db.cursor()

        # Ensure that a table to track the schema version exists.
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table_name}_schema_version (
                version INTEGER NOT NULL
            )
            """
        )

        # Ensure that the current schema version matches the expected schema version. If no version is stored, it
        # means that the table has not been initialized yet.
        cursor.execute(
            f"""
            SELECT version FROM {self._table_name}_schema_version
            """
        )
        if row := cursor.fetchone():
            version = row[0]
            if version != self.CURRENT_SCHEMA_VERSION:
                raise RuntimeError(f"Schema version mismatch: expected {self.CURRENT_SCHEMA_VERSION}, got {version}")
        else:
            cursor.execute(
                f"""
                INSERT INTO {self._table_name}_schema_version (version)
                VALUES ({self.CURRENT_SCHEMA_VERSION})
                """
            )

        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                apiVersion TEXT NOT NULL,
                kind TEXT NOT NULL,
                namespace TEXT,
                name TEXT NOT NULL,
                annotations JSONB NOT NULL,
                labels JSONB NOT NULL,
                spec JSONB NOT NULL,
                state JSONB NOT NULL,
                deletion_timestamp TIMESTAMP WITH TIME ZONE,
                PRIMARY KEY (apiVersion, kind, namespace, name)
            )
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self._table_name}_apiVersion_idx ON {self._table_name} (apiVersion)
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self._table_name}_kind_idx ON {self._table_name} (kind)
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self._table_name}_namespace_idx ON {self._table_name} (namespace)
            """
        )
        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self._table_name}_name_idx ON {self._table_name} (name)
            """
        )
        self._db.commit()
        cursor.close()

    def drop(self) -> None:
        """
        Drops all tables managed by this resource store. Careful, this actually drops all your data.
        """

        cursor = self._db.cursor()
        logger.info("Dropping table %s", self._table_name)
        cursor.execute(f"DROP TABLE IF EXISTS {self._table_name}")
        logger.info("Dropping table %s_schema_version", self._table_name)
        cursor.execute(f"DROP TABLE IF EXISTS {self._table_name}_schema_version")
        self._db.commit()
        cursor.close()

    # ResourceStore overrides

    def acquire_lock(self, request: LockRequest) -> LockID | None:
        return super().acquire_lock(request)

    def release_lock(self, lock: LockID) -> None:
        super().release_lock(lock)

    def check_lock(self, lock: LockID, *, valid_for: float | None = None) -> bool:
        return super().check_lock(lock, valid_for=valid_for)

    def namespaces(self) -> list[Resource[Namespace]]:
        return super().namespaces()

    def search(self, lock: LockID, request: SearchRequest) -> list[URI]:
        return super().search(lock, request)

    def get(self, lock: LockID, uri: URI) -> GenericResource | None:
        return super().get(lock, uri)

    def put(self, lock: LockID, resource: GenericResource) -> None:
        return super().put(lock, resource)

    def delete(self, lock: LockID, uri: URI) -> bool:
        return super().delete(lock, uri)
