-- Disposable Task 7.17J stores only; never a node database migration.
CREATE TABLE authority (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    namespace BLOB NOT NULL, manifest BLOB NOT NULL, agreement BLOB NOT NULL,
    test_catalogue BLOB NOT NULL
);
CREATE TABLE blobs (
    digest TEXT PRIMARY KEY CHECK(length(digest)=64),
    kind TEXT NOT NULL CHECK(kind IN ('block','signed','pv','q4','manifest','agreement',
        'policy','validation','slot','receipt','marker','state','event','fault')),
    raw BLOB NOT NULL
);
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY CHECK(sequence>0),
    event_id TEXT NOT NULL UNIQUE REFERENCES blobs(digest),
    state_id TEXT NOT NULL REFERENCES blobs(digest)
);
CREATE TABLE head (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    record BLOB NOT NULL
);
CREATE TABLE slots (
    namespace_id TEXT NOT NULL, height INTEGER NOT NULL CHECK(height>0),
    round INTEGER NOT NULL CHECK(round>=0),
    purpose TEXT NOT NULL CHECK(purpose IN ('propose','prevote','precommit')),
    slot_id TEXT NOT NULL REFERENCES blobs(digest),
    PRIMARY KEY(namespace_id,height,round,purpose)
);
CREATE TABLE outbox (
    namespace_id TEXT NOT NULL, height INTEGER NOT NULL, round INTEGER NOT NULL,
    purpose TEXT NOT NULL, signed_id TEXT NOT NULL UNIQUE REFERENCES blobs(digest),
    PRIMARY KEY(namespace_id,height,round,purpose),
    FOREIGN KEY(namespace_id,height,round,purpose)
        REFERENCES slots(namespace_id,height,round,purpose)
);
