import logging
import unittest
from uuid import uuid4

from equilibrium.PostgresResourceStore import PostgresResourceStore
from equilibrium.ResourceStore_test import ResourceStoreTestSuite

logger = logging.getLogger(__name__)


class PostgresResourceStoreTest(ResourceStoreTestSuite, unittest.TestCase):
    store: PostgresResourceStore

    # TestCase overrides

    def setUp(self) -> None:
        self.store = self.create_store()

    def tearDown(self) -> None:
        self.store.drop()

    # Helpers

    @staticmethod
    def create_store() -> PostgresResourceStore:
        params = PostgresResourceStore.ConnectionParams(
            user="postgres",
            password="alpine",
            host="localhost",
            dbname="postgres",
            port=5432,
        )
        table_name = "equilibrium_" + str(uuid4())[:8]
        logger.info("Using table name: %s", table_name)
        store = PostgresResourceStore(params, table_name)
        store.initialize()
        return store
