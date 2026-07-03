# Data Pipeline

## Overview
Build a batch **Data pipeline** that processes incoming records through a strict, linear sequence of six stages. Each stage consumes the output of the stage immediately before it and cannot begin until that prior stage has completed successfully. The order is fixed: ingest → validate → transform → deduplicate → load → notify.

## Requirements

1. **Ingest** the raw records from the upstream source into a staging area. This is the first stage and has no prerequisites.
2. **Validate** the ingested records against the schema, rejecting malformed rows. Validation runs only on the output of the ingest stage and depends on it.
3. **Transform** the validated records into the canonical internal format. Transformation operates solely on the validated output and depends on the validate stage.
4. **Deduplicate** the transformed records, removing exact and near-duplicate entries. Deduplication runs on the transformed output and depends on the transform stage.
5. **Load** the deduplicated records into the target warehouse. Loading consumes the deduplicated output and depends on the deduplicate stage.
6. **Notify** downstream consumers that fresh data is available. Notification fires only after a successful load and depends on the load stage.

## Notes
The chain is strictly linear: no stage may be reordered or run in parallel with another. A failure at any stage halts every subsequent stage.
