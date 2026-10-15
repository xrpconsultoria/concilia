import sqlite3
from pathlib import Path


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript('''
        CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY, name TEXT NOT NULL, tax_id TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES clients(id),
            name TEXT NOT NULL, number TEXT NOT NULL, bank_code INTEGER NOT NULL, default_in INTEGER NOT NULL DEFAULT 106,
            default_out INTEGER NOT NULL DEFAULT 106);
        CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
            kind TEXT NOT NULL, pattern TEXT NOT NULL, direction TEXT NOT NULL, code INTEGER NOT NULL,
            UNIQUE(account_id,kind,pattern,direction,code));
        CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
            source_hash TEXT NOT NULL, filename TEXT NOT NULL, layout TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
            warnings TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id,source_hash,start,end));
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, batch_id INTEGER NOT NULL REFERENCES batches(id),
            date TEXT NOT NULL, book_date TEXT, description TEXT NOT NULL, cents INTEGER NOT NULL, document TEXT NOT NULL,
            code INTEGER NOT NULL, reason TEXT NOT NULL, duplicate INTEGER NOT NULL DEFAULT 0,
            include_row INTEGER NOT NULL DEFAULT 1, reviewed INTEGER NOT NULL DEFAULT 0);
    ''')
    columns = {row[1] for row in db.execute("PRAGMA table_info(batches)")}
    if "exported_at" not in columns:
        db.execute("ALTER TABLE batches ADD COLUMN exported_at TEXT")
        db.commit()
    return db
