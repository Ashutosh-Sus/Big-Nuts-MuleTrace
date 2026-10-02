"""CSV ingestion: column aliasing, validation, normalisation (ARCHITECTURE §3)."""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .config import Config

ALIASES: dict[str, tuple[str, ...]] = {
    "txn_id": ("txn_id", "transaction_id", "txnid", "tx_id", "trans_id", "id", "reference", "ref_id"),
    "timestamp": ("timestamp", "time", "datetime", "date_time", "txn_time", "transaction_time",
                  "txn_timestamp", "ts", "step", "date"),
    "sender_account": ("sender_account", "sender", "from", "from_account", "src", "source",
                       "source_account", "payer", "payer_account", "nameorig", "origin_account",
                       "debit_account", "sender_id"),
    "receiver_account": ("receiver_account", "receiver", "to", "to_account", "dst", "destination",
                         "destination_account", "payee", "payee_account", "namedest",
                         "beneficiary", "beneficiary_account", "credit_account", "receiver_id"),
    "amount": ("amount", "amt", "value", "amount_inr", "transaction_amount", "txn_amount",
               "amount_paid", "amount_received"),
    "currency": ("currency", "ccy", "currency_code", "payment_currency"),
    "channel": ("channel", "type", "txn_type", "payment_format", "mode", "payment_mode"),
    "sender_device_id": ("sender_device_id", "sender_device", "device_id", "device"),
    "sender_ip": ("sender_ip", "sender_ip_address", "ip", "ip_address"),
    "sender_kyc_id": ("sender_kyc_id", "sender_kyc", "kyc_id", "kyc", "kyc_hash"),
    "receiver_device_id": ("receiver_device_id", "receiver_device"),
    "receiver_ip": ("receiver_ip", "receiver_ip_address"),
    "receiver_kyc_id": ("receiver_kyc_id", "receiver_kyc"),
    "sender_account_created": ("sender_account_created", "sender_created_at", "sender_created",
                               "sender_account_open_date", "account_created"),
    "receiver_account_created": ("receiver_account_created", "receiver_created_at", "receiver_created",
                                 "receiver_account_open_date"),
    "sender_balance_before": ("sender_balance_before", "oldbalanceorg", "oldbalanceorig"),
    "sender_balance_after": ("sender_balance_after", "newbalanceorig", "newbalanceorg"),
    "receiver_balance_before": ("receiver_balance_before", "oldbalancedest"),
    "receiver_balance_after": ("receiver_balance_after", "newbalancedest"),
    "label": ("label", "isfraud", "is_fraud", "is_laundering", "fraud", "is_suspicious"),
}
REQUIRED = ("timestamp", "sender_account", "receiver_account", "amount")
OPTIONAL_CAPABILITIES = {
    "device": ("sender_device_id", "receiver_device_id"),
    "ip": ("sender_ip", "receiver_ip"),
    "kyc": ("sender_kyc_id", "receiver_kyc_id"),
    "account_created": ("sender_account_created", "receiver_account_created"),
    "balances": ("sender_balance_before", "sender_balance_after",
                 "receiver_balance_before", "receiver_balance_after"),
    "currency": ("currency",),
    "label": ("label",),
}
SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
_SYMBOL_TO_CODE = {"₹": "INR", "RS": "INR", "RS.": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
_AMOUNT_STRIP = re.compile(r"(?i)^(inr|rs\.?|usd|eur|gbp)|[₹$€£,\s_]")
_DATE_FORMATS = (
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
)
MAX_ERRORS = 200


class IngestError(Exception):
    """Whole-file rejection (HTTP 422)."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {}


@dataclass(slots=True)
class Txn:
    idx: int
    txn_id: str
    ts: int
    sender: str
    receiver: str
    amount: int                      # minor units
    row: int
    channel: str | None = None
    s_device: str | None = None
    s_ip: str | None = None
    s_kyc: str | None = None
    r_device: str | None = None
    r_ip: str | None = None
    r_kyc: str | None = None
    s_created: int | None = None
    r_created: int | None = None
    s_bal_before: int | None = None
    s_bal_after: int | None = None
    r_bal_before: int | None = None
    r_bal_after: int | None = None
    label: str | None = None


@dataclass
class IngestResult:
    txns: list[Txn]
    report: dict = field(default_factory=dict)


def _norm_header(h: str) -> str:
    return re.sub(r"[\s\-]+", "_", h.strip().lstrip("﻿").lower())


def map_columns(headers: list[str]) -> dict[str, int]:
    """Return canonical field -> column index. First alias match wins, in alias order."""
    normed = [_norm_header(h) for h in headers]
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for canon, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normed:
                i = normed.index(alias)
                if i not in used:
                    mapping[canon] = i
                    used.add(i)
                    break
    return mapping


def parse_amount(raw: str) -> int:
    s = _AMOUNT_STRIP.sub("", raw.strip())
    if not s:
        raise ValueError("empty amount")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"unparseable amount '{raw.strip()[:30]}'")
    if not d.is_finite():
        raise ValueError("non-finite amount")
    return int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class TimeParser:
    """Detects the time mode of a column and converts values to epoch seconds."""

    def __init__(self, values: list[str], cfg: Config):
        self.cfg = cfg
        self.tz = timezone(timedelta(minutes=cfg.local_offset_minutes))
        ints = [v.strip() for v in values if v.strip()]
        self.mode = "datetime"
        if ints and all(re.fullmatch(r"-?\d+", v) for v in ints):
            mx = max(int(v) for v in ints)
            if mx < 1_000_000:
                self.mode = "step"
            elif mx >= 1_000_000_000_000:
                self.mode = "epoch_ms"
            else:
                self.mode = "epoch_s"

    def describe(self) -> str:
        if self.mode == "step":
            hours = self.cfg.step_unit_seconds / 3600
            return f"step index (1 step = {hours:g} hour{'s' if hours != 1 else ''})"
        return {"epoch_ms": "epoch milliseconds", "epoch_s": "epoch seconds"}.get(self.mode, "date/time text")

    def parse(self, raw: str) -> int:
        v = raw.strip()
        if not v:
            raise ValueError("empty timestamp")
        if self.mode == "step":
            return self.cfg.step_base_epoch + int(v) * self.cfg.step_unit_seconds
        if self.mode == "epoch_ms":
            return int(v) // 1000
        if self.mode == "epoch_s":
            return int(v)
        return parse_datetime(v, self.tz)


def parse_datetime(v: str, tz: timezone) -> int:
    if re.fullmatch(r"\d{9,10}", v):
        return int(v)
    if re.fullmatch(r"\d{12,13}", v):
        return int(v) // 1000
    dt = None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(v, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        raise ValueError(f"unparseable timestamp '{v[:30]}'")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return int(dt.timestamp())


def _opt(row: list[str], mapping: dict[str, int], key: str) -> str | None:
    i = mapping.get(key)
    if i is None or i >= len(row):
        return None
    v = row[i].strip()
    return v or None


def parse_csv(data: bytes, cfg: Config) -> IngestResult:
    if len(data) > cfg.max_upload_bytes:
        raise IngestError(f"File exceeds {cfg.max_upload_bytes // (1024 * 1024)} MB limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise IngestError("File is empty")
    headers = rows[0]
    body = rows[1:]
    if len(body) > cfg.max_rows:
        raise IngestError(f"File has {len(body)} rows; limit is {cfg.max_rows}")
    mapping = map_columns(headers)
    missing = [f for f in REQUIRED if f not in mapping]
    if missing:
        raise IngestError(
            "Missing required columns: " + ", ".join(missing),
            {"missing": missing, "detected_headers": headers},
        )

    time_parser = TimeParser([r[mapping["timestamp"]] if mapping["timestamp"] < len(r) else "" for r in body], cfg)
    tz = time_parser.tz

    # dominant currency
    cur_counts: Counter[str] = Counter()
    if "currency" in mapping:
        for r in body:
            c = _opt(r, mapping, "currency")
            if c:
                cur_counts[_SYMBOL_TO_CODE.get(c.upper(), c.upper())] += 1
    currency = sorted(cur_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if cur_counts else "INR"

    errors: list[dict] = []
    error_count = 0
    duplicates = 0
    seen: dict[str, tuple] = {}
    parsed: list[Txn] = []

    def reject(rownum: int, reason: str, raw: list[str]) -> None:
        nonlocal error_count
        error_count += 1
        if len(errors) < MAX_ERRORS:
            errors.append({"row": rownum, "reason": reason, "excerpt": ",".join(raw)[:120]})

    for n, r in enumerate(body, start=2):
        try:
            sender = _opt(r, mapping, "sender_account")
            receiver = _opt(r, mapping, "receiver_account")
            if not sender or not receiver:
                raise ValueError("empty account")
            if sender == receiver:
                raise ValueError("self-transfer")
            ts = time_parser.parse(r[mapping["timestamp"]] if mapping["timestamp"] < len(r) else "")
            amount = parse_amount(r[mapping["amount"]] if mapping["amount"] < len(r) else "")
            if amount <= 0:
                raise ValueError("amount must be positive")
            if "currency" in mapping:
                c = _opt(r, mapping, "currency")
                code = _SYMBOL_TO_CODE.get(c.upper(), c.upper()) if c else currency
                if code != currency:
                    raise ValueError(f"minority currency {code} (dataset currency {currency})")

            def created(key: str) -> int | None:
                v = _opt(r, mapping, key)
                return parse_datetime(v, tz) if v else None

            def money(key: str) -> int | None:
                v = _opt(r, mapping, key)
                return parse_amount(v) if v else None

            txn_id = _opt(r, mapping, "txn_id")
            content = (ts, sender, receiver, amount)
            if not txn_id:
                txn_id = "D-" + hashlib.sha1(repr(content).encode()).hexdigest()[:12]
            if txn_id in seen:
                if seen[txn_id] == content:
                    duplicates += 1
                    continue
                raise ValueError(f"conflicting duplicate txn_id {txn_id}")
            seen[txn_id] = content
            parsed.append(Txn(
                idx=0, txn_id=txn_id, ts=ts, sender=sender, receiver=receiver, amount=amount, row=n,
                channel=_opt(r, mapping, "channel"),
                s_device=_opt(r, mapping, "sender_device_id"), s_ip=_opt(r, mapping, "sender_ip"),
                s_kyc=_opt(r, mapping, "sender_kyc_id"),
                r_device=_opt(r, mapping, "receiver_device_id"), r_ip=_opt(r, mapping, "receiver_ip"),
                r_kyc=_opt(r, mapping, "receiver_kyc_id"),
                s_created=created("sender_account_created"), r_created=created("receiver_account_created"),
                s_bal_before=money("sender_balance_before"), s_bal_after=money("sender_balance_after"),
                r_bal_before=money("receiver_balance_before"), r_bal_after=money("receiver_balance_after"),
                label=_opt(r, mapping, "label"),
            ))
        except ValueError as e:
            reject(n, str(e), r)

    parsed.sort(key=lambda t: (t.ts, t.txn_id))
    for i, t in enumerate(parsed):
        t.idx = i

    coverage = {"currency": "currency" in mapping}
    for cap, keys in OPTIONAL_CAPABILITIES.items():
        if cap != "currency":
            attrs = _attrs_for(keys)
            coverage[cap] = any(getattr(t, a) is not None for t in parsed for a in attrs)

    report = {
        "rows_total": len(body),
        "rows_accepted": len(parsed),
        "rows_rejected": error_count,
        "duplicates_dropped": duplicates,
        "errors": errors,
        "column_mapping": {k: headers[v] for k, v in sorted(mapping.items(), key=lambda kv: kv[1])},
        "ignored_columns": [h for i, h in enumerate(headers) if i not in mapping.values()],
        "time_mode": time_parser.mode,
        "time_mode_label": time_parser.describe(),
        "currency": currency,
        "currency_symbol": SYMBOLS.get(currency, currency + " "),
        "coverage": coverage,
        "txn_id_derived": "txn_id" not in mapping,
        "time_start": parsed[0].ts if parsed else None,
        "time_end": parsed[-1].ts if parsed else None,
    }
    return IngestResult(parsed, report)


_FIELD_TO_ATTR = {
    "sender_device_id": "s_device", "receiver_device_id": "r_device",
    "sender_ip": "s_ip", "receiver_ip": "r_ip",
    "sender_kyc_id": "s_kyc", "receiver_kyc_id": "r_kyc",
    "sender_account_created": "s_created", "receiver_account_created": "r_created",
    "sender_balance_before": "s_bal_before", "sender_balance_after": "s_bal_after",
    "receiver_balance_before": "r_bal_before", "receiver_balance_after": "r_bal_after",
    "label": "label",
}


def _attrs_for(keys: tuple[str, ...]) -> list[str]:
    return [_FIELD_TO_ATTR[k] for k in keys if k in _FIELD_TO_ATTR]
