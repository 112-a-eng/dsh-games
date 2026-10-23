# -*- coding: utf-8 -*-
"""SQLite 持久层：科目、凭证、分录、期初余额、系统设置。

对外只暴露和领域模型交互的方法，界面层不直接写 SQL。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime

from . import config as C
from .models import Account, Entry, Voucher

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS accounts (
    code       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    direction  TEXT NOT NULL,
    group_name TEXT NOT NULL,
    parent     TEXT,
    is_leaf    INTEGER NOT NULL DEFAULT 1,
    custom     INTEGER NOT NULL DEFAULT 0,
    enabled    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS vouchers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    number      TEXT NOT NULL,
    memo        TEXT NOT NULL DEFAULT '',
    attachments INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'draft',
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_id   INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
    line_no      INTEGER NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    account_code TEXT NOT NULL,
    debit        INTEGER NOT NULL DEFAULT 0,
    credit       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_voucher ON entries(voucher_id);
CREATE INDEX IF NOT EXISTS idx_entries_account ON entries(account_code);
CREATE TABLE IF NOT EXISTS opening (
    account_code TEXT PRIMARY KEY,
    amount       INTEGER NOT NULL DEFAULT 0
);
"""


def today_str() -> str:
    return date.today().isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self.setdefault("schema_version", str(C.SCHEMA_VERSION))
        self.setdefault("company", "演示公司")
        self.setdefault("start_date", date.today().replace(month=1, day=1).isoformat())
        self.setdefault("currency", "人民币")
        self.conn.commit()
        self.seed_accounts()

    # ------------------------------------------------------------ 基础
    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def setdefault(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
                          (key, value))

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
        self.conn.commit()

    @property
    def company(self) -> str:
        return self.get_meta("company", "演示公司")

    @property
    def start_date(self) -> str:
        return self.get_meta("start_date", today_str())

    # ------------------------------------------------------------ 科目
    def seed_accounts(self) -> None:
        count = self.conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
        if count:
            return
        self.conn.executemany(
            "INSERT INTO accounts(code, name, category, direction, group_name, "
            "parent, is_leaf, custom, enabled) VALUES (?,?,?,?,?,?,?,?,1)",
            [(a.code, a.name, a.category, a.direction, a.group, _parent_of(a.code),
              int(a.is_leaf), int(a.custom)) for a in C.STANDARD_ACCOUNTS])
        self.conn.commit()

    def _row_to_account(self, row) -> Account:
        return Account(row["code"], row["name"], row["category"], row["direction"],
                       row["group_name"], bool(row["is_leaf"]),
                       bool(row["custom"]), bool(row["enabled"]))

    def list_accounts(self, include_disabled: bool = False) -> list:
        sql = "SELECT * FROM accounts"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY code"
        return [self._row_to_account(r) for r in self.conn.execute(sql).fetchall()]

    def get_account(self, code: str) -> Account | None:
        row = self.conn.execute("SELECT * FROM accounts WHERE code = ?", (code,)).fetchone()
        return self._row_to_account(row) if row else None

    def account_exists(self, code: str) -> bool:
        return self.conn.execute("SELECT 1 FROM accounts WHERE code = ?", (code,)).fetchone() is not None

    def add_account(self, acc: Account) -> None:
        self.conn.execute(
            "INSERT INTO accounts(code, name, category, direction, group_name, "
            "parent, is_leaf, custom, enabled) VALUES (?,?,?,?,?,?,?,?,?)",
            (acc.code, acc.name, acc.category, acc.direction, acc.group,
             _parent_of(acc.code), int(acc.is_leaf), int(acc.custom), int(acc.enabled)))
        self._refresh_leaf(_parent_of(acc.code))
        self.conn.commit()

    def update_account(self, acc: Account) -> None:
        self.conn.execute(
            "UPDATE accounts SET name=?, category=?, direction=?, group_name=?, "
            "is_leaf=?, enabled=? WHERE code=?",
            (acc.name, acc.category, acc.direction, acc.group,
             int(acc.is_leaf), int(acc.enabled), acc.code))
        self.conn.commit()

    def delete_account(self, code: str) -> None:
        parent = _parent_of(code)
        self.conn.execute("DELETE FROM accounts WHERE code = ?", (code,))
        self._refresh_leaf(parent)
        self.conn.commit()

    def account_has_entries(self, code: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM entries WHERE account_code = ? LIMIT 1", (code,)).fetchone() is not None

    def _refresh_leaf(self, code: str | None) -> None:
        if not code or not self.account_exists(code):
            return
        has_child = self.conn.execute(
            "SELECT 1 FROM accounts WHERE parent = ? LIMIT 1", (code,)).fetchone() is not None
        self.conn.execute("UPDATE accounts SET is_leaf = ? WHERE code = ?",
                          (0 if has_child else 1, code))

    # ------------------------------------------------------------ 凭证
    def next_voucher_number(self, day: str) -> str:
        """按「记-月份-序号」生成凭证号，例如 记-3-0007。"""
        month = int(day[5:7])
        prefix = "记-%d-" % month
        row = self.conn.execute(
            "SELECT number FROM vouchers WHERE number LIKE ? ORDER BY number DESC LIMIT 1",
            (prefix + "%",)).fetchone()
        seq = 1
        if row:
            try:
                seq = int(row["number"].rsplit("-", 1)[1]) + 1
            except (ValueError, IndexError):
                seq = self.conn.execute(
                    "SELECT COUNT(*) AS n FROM vouchers WHERE number LIKE ?",
                    (prefix + "%",)).fetchone()["n"] + 1
        return "%s%04d" % (prefix, seq)

    def save_voucher(self, v: Voucher) -> int:
        """新增或更新凭证，返回凭证 id。"""
        now = datetime.now().isoformat(timespec="seconds")
        if v.voucher_id:
            vid = v.voucher_id
            self.conn.execute(
                "UPDATE vouchers SET date=?, number=?, memo=?, attachments=?, "
                "status=?, source=? WHERE id=?",
                (v.date, v.number, v.memo, v.attachments, v.status, v.source, vid))
            self.conn.execute("DELETE FROM entries WHERE voucher_id = ?", (vid,))
        else:
            cur = self.conn.execute(
                "INSERT INTO vouchers(date, number, memo, attachments, status, source, "
                "created_at) VALUES (?,?,?,?,?,?,?)",
                (v.date, v.number, v.memo, v.attachments, v.status, v.source, now))
            vid = cur.lastrowid
            v.voucher_id = vid
        rows = [(vid, i, e.summary, e.account_code, int(e.debit), int(e.credit))
                for i, e in enumerate(v.entries, start=1)]
        self.conn.executemany(
            "INSERT INTO entries(voucher_id, line_no, summary, account_code, debit, credit) "
            "VALUES (?,?,?,?,?,?)", rows)
        self.conn.commit()
        return vid

    def _load_entries(self, vid: int) -> list:
        rows = self.conn.execute(
            "SELECT e.*, a.name AS acc_name FROM entries e "
            "LEFT JOIN accounts a ON a.code = e.account_code "
            "WHERE e.voucher_id = ? ORDER BY e.line_no", (vid,)).fetchall()
        out = []
        for r in rows:
            out.append(Entry(r["account_code"], r["summary"], r["debit"],
                             r["credit"], r["line_no"], r["acc_name"] or ""))
        return out

    def _row_to_voucher(self, row) -> Voucher:
        v = Voucher(row["date"], [], row["number"], row["memo"], row["attachments"],
                    row["id"], row["status"], row["source"])
        v.entries = self._load_entries(row["id"])
        return v

    def get_voucher(self, vid: int) -> Voucher | None:
        row = self.conn.execute("SELECT * FROM vouchers WHERE id = ?", (vid,)).fetchone()
        return self._row_to_voucher(row) if row else None

    def list_vouchers(self, start: str | None = None, end: str | None = None,
                      keyword: str | None = None, account: str | None = None,
                      status: str | None = None) -> list:
        where, args = [], []
        if start:
            where.append("date >= ?")
            args.append(start)
        if end:
            where.append("date <= ?")
            args.append(end)
        if status:
            where.append("status = ?")
            args.append(status)
        if keyword:
            where.append("(number LIKE ? OR memo LIKE ? OR id IN "
                         "(SELECT voucher_id FROM entries WHERE summary LIKE ?))")
            like = "%" + keyword + "%"
            args += [like, like, like]
        if account:
            where.append("id IN (SELECT voucher_id FROM entries WHERE account_code = ?)")
            args.append(account)
        sql = "SELECT * FROM vouchers"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date DESC, id DESC"
        return [self._row_to_voucher(r) for r in self.conn.execute(sql, args).fetchall()]

    def delete_voucher(self, vid: int) -> None:
        self.conn.execute("DELETE FROM vouchers WHERE id = ?", (vid,))
        self.conn.commit()

    def set_voucher_status(self, vid: int, status: str) -> None:
        self.conn.execute("UPDATE vouchers SET status = ? WHERE id = ?", (status, vid))
        self.conn.commit()

    def count_vouchers(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"]

    # ------------------------------------------------------------ 期初余额
    def get_openings(self) -> dict:
        rows = self.conn.execute("SELECT account_code, amount FROM opening").fetchall()
        return {r["account_code"]: r["amount"] for r in rows if r["amount"]}

    def set_opening(self, code: str, amount: int) -> None:
        if amount == 0:
            self.conn.execute("DELETE FROM opening WHERE account_code = ?", (code,))
        else:
            self.conn.execute(
                "INSERT INTO opening(account_code, amount) VALUES (?, ?) "
                "ON CONFLICT(account_code) DO UPDATE SET amount = excluded.amount",
                (code, int(amount)))
        self.conn.commit()

    def replace_openings(self, mapping: dict) -> None:
        self.conn.execute("DELETE FROM opening")
        rows = [(c, int(a)) for c, a in mapping.items() if int(a) != 0]
        self.conn.executemany("INSERT INTO opening(account_code, amount) VALUES (?, ?)", rows)
        self.conn.commit()

    # ------------------------------------------------------------ 分录级查询
    def iter_posted_entries(self, start: str | None = None, end: str | None = None,
                            upto: str | None = None, account: str | None = None):
        """按日期区间读取已过账分录，联同凭证号/日期一起返回。"""
        where = ["v.status = 'posted'"]
        args = []
        if upto:
            where.append("v.date <= ?")
            args.append(upto)
        if start:
            where.append("v.date >= ?")
            args.append(start)
        if end:
            where.append("v.date <= ?")
            args.append(end)
        if account:
            where.append("e.account_code = ?")
            args.append(account)
        sql = ("SELECT v.date, v.number, v.id AS vid, e.line_no, e.summary, "
               "e.account_code, e.debit, e.credit FROM entries e "
               "JOIN vouchers v ON v.id = e.voucher_id WHERE " + " AND ".join(where) +
               " ORDER BY v.date, v.id, e.line_no")
        return self.conn.execute(sql, args).fetchall()


def _parent_of(code: str) -> str | None:
    if len(code) > 4:
        return code[:-2]
    return None