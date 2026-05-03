# Service Layer Instructions

## Principles

1.  **Statelessness**: The service layer is stateless by contract. No `@lru_cache`, no module-level dicts, no class-with-state. Services are pure functions that take ports as parameters and return immutable results.
2.  **Functions over Classes**: Services are implemented as functions, not classes, unless state encapsulation is genuinely required (rare).
3.  **Dependency Injection**: Services accept ports (Protocols) as parameters. They never construct concrete adapters.
4.  **Isolation**: Service layer files have no I/O imports (no `streamlit`, `requests`, `yfinance`). They may import from `app.domain` and `app.ports`.
5.  **Failure Handling**: Service errors are caught at the boundary of the service (e.g., per-ticker isolation), ensuring a single failure doesn't abort the entire operation.
6.  **No Internal Logging**: Services should not use `print()` or `logging`. Error information should be returned via domain models (e.g., `staleness_reason`).

## Caching Strategy

The system uses a two-cache architecture:
- **Adapter Layer**: Caches network/IO results (e.g., `YfinanceAdapter` has a TTL cache).
- **UI Layer**: Caches computation results (e.g., Streamlit's `@st.cache_data`).
- **Service Layer**: Remains stateless between these two layers to ensure predictable invalidation.

## Invalidation

The single entry point for invalidation is the UI's "Refresh" button, which calls service-layer wrappers to clear adapter caches and then clears the UI cache.
