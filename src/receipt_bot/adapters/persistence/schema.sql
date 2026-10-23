CREATE TABLE IF NOT EXISTS receipts (
 id TEXT PRIMARY KEY, owner_id BIGINT NOT NULL, source_key TEXT NOT NULL,
 purchase_date DATE, total NUMERIC(38,0), review_reasons JSONB NOT NULL,
 reportable BOOLEAN NOT NULL, UNIQUE (owner_id, source_key), UNIQUE (owner_id, id),
 CHECK (total >= 0)
);
CREATE TABLE IF NOT EXISTS receipt_items (
 id TEXT PRIMARY KEY, owner_id BIGINT NOT NULL, receipt_id TEXT NOT NULL, position INTEGER NOT NULL,
 item_name TEXT, price NUMERIC(38,0), category JSONB,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL, review_reasons JSONB NOT NULL,
 FOREIGN KEY (owner_id, receipt_id) REFERENCES receipts(owner_id, id),
 UNIQUE (owner_id, id), CHECK (price >= 0)
);
CREATE TABLE IF NOT EXISTS review_tasks (
 id TEXT PRIMARY KEY, owner_id BIGINT NOT NULL, item_id TEXT NOT NULL,
 options JSONB NOT NULL, status TEXT NOT NULL CHECK (status IN ('pending','answered')), answer JSONB,
 FOREIGN KEY (owner_id, item_id) REFERENCES receipt_items(owner_id, id)
);
CREATE TABLE IF NOT EXISTS report_conversations (
 owner_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, state JSONB,
 PRIMARY KEY (owner_id, chat_id)
);
CREATE TABLE IF NOT EXISTS report_events (
 owner_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, event_id TEXT NOT NULL, result JSONB NOT NULL,
 PRIMARY KEY (owner_id, chat_id, event_id),
 FOREIGN KEY (owner_id, chat_id) REFERENCES report_conversations(owner_id, chat_id)
);
