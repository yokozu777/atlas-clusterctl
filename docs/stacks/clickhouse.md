# ClickHouse

Phase `clickhouse` runs `atlas-clickhouse` after provision and init.

Inventory groups: `ch_keeper` (3), `ch_cluster` (4, host vars `clickhouse_shard` and `clickhouse_replica`), `ch_lbs` (1).
