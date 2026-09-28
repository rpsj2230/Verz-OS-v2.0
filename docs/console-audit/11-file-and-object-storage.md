### File and object storage

- **Screens:** `/storage`
- **Tables:** none
- **Installation values:** `INSTALL_OBJECT_STORE_URL`, `INSTALL_OBJECT_STORE_PREFIX`, `INSTALL_OBJECT_STORE_BACKEND`
- **Measured here:** 1 routes, 0 called by no screen; 0 write routes, 0 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/storage` | `/storage` |

- **Gap.** A bucket's retention and the store's address are read and never changed. Open leaf `M27.8.15`.
