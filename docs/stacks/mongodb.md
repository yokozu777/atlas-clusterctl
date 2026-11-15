# MongoDB

Phase `mongodb` runs `atlas-mongodb` after provision and init.

Inventory group: `mongo_cluster` (3). Each host sets `mongodb_data_disk`. The first sorted host is the preferred initial primary.
