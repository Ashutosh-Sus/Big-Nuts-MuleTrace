"""Ingestion edge cases (ARCHITECTURE §3)."""
import pytest

from muletrace.config import DEFAULT
from muletrace.ingest import IngestError, parse_amount, parse_csv


def ingest(text: str, bom: bool = False):
    data = text.encode("utf-8")
    return parse_csv((b"\xef\xbb\xbf" if bom else b"") + data, DEFAULT)


def test_amount_formats_to_minor_units():
    assert parse_amount("₹1,20,000.50") == 12_000_050
    assert parse_amount("Rs. 4500") == 450_000
    assert parse_amount("INR 99.999") == 10_000          # rounds half-up to paise
    assert parse_amount("$1,234.5") == 123_450
    with pytest.raises(ValueError):
        parse_amount("twelve")


def test_bom_crlf_quoted_commas_and_extra_columns():
    text = ('txn_id,timestamp,from,to,amount,notes\r\n'
            'T1,2024-03-01 10:00:00,A,B,"1,500.00","rent, march"\r\n'
            'T2,01-03-2024 10:05,B,C,1490,\r\n')
    r = ingest(text, bom=True)
    assert r.report["rows_accepted"] == 2
    assert [t.amount for t in r.txns] == [150_000, 149_000]
    assert "notes" in r.report["ignored_columns"]
    assert r.txns[1].ts - r.txns[0].ts == 300


def test_step_mode_is_not_epoch_seconds():
    text = "step,nameOrig,nameDest,amount,isFraud\n1,A,B,100,0\n2,B,C,99,1\n"
    r = ingest(text)
    assert r.report["time_mode"] == "step"
    assert r.txns[1].ts - r.txns[0].ts == 3600
    assert r.report["coverage"]["label"] is True


def test_epoch_milliseconds_and_seconds():
    ms = ingest("timestamp,sender,receiver,amount\n1709280000000,A,B,10\n1709280060000,B,C,9\n")
    assert ms.report["time_mode"] == "epoch_ms" and ms.txns[1].ts - ms.txns[0].ts == 60
    s = ingest("timestamp,sender,receiver,amount\n1709280000,A,B,10\n1709280060,B,C,9\n")
    assert s.report["time_mode"] == "epoch_s"


def test_row_level_rejections_and_duplicates():
    text = ("txn_id,timestamp,sender_account,receiver_account,amount\n"
            "T1,2024-03-01 10:00,A,B,100\n"
            "T1,2024-03-01 10:00,A,B,100\n"          # exact duplicate
            "T1,2024-03-01 10:00,A,B,999\n"          # conflicting duplicate
            "T4,not a time,A,B,100\n"
            "T5,2024-03-01 10:00,A,A,100\n"
            "T6,2024-03-01 10:00,A,B,-5\n"
            "T7,2024-03-01 10:00,,B,5\n")
    r = ingest(text)
    rep = r.report
    assert rep["rows_accepted"] == 1 and rep["duplicates_dropped"] == 1 and rep["rows_rejected"] == 5
    reasons = [e["reason"] for e in rep["errors"]]
    assert any("conflicting" in x for x in reasons) and any("self-transfer" in x for x in reasons)
    assert all(e["row"] >= 2 for e in rep["errors"])


def test_dominant_currency_and_minority_rejection():
    text = ("timestamp,sender,receiver,amount,currency\n"
            "2024-03-01 10:00,A,B,10,USD\n2024-03-01 10:01,B,C,10,USD\n2024-03-01 10:02,C,D,10,EUR\n")
    r = ingest(text)
    assert r.report["currency"] == "USD" and r.report["currency_symbol"] == "$"
    assert r.report["rows_accepted"] == 2
    assert "minority currency" in r.report["errors"][0]["reason"]


def test_missing_required_columns_and_empty_file():
    with pytest.raises(IngestError) as e:
        ingest("a,b\n1,2\n")
    assert set(e.value.detail["missing"]) == {"timestamp", "sender_account", "receiver_account", "amount"}
    with pytest.raises(IngestError):
        ingest("")


def test_header_only_file_has_no_transactions():
    r = ingest("timestamp,sender,receiver,amount\n")
    assert r.txns == [] and r.report["rows_total"] == 0


def test_derived_txn_ids_are_stable():
    text = "timestamp,sender,receiver,amount\n2024-03-01 10:00,A,B,10\n"
    assert ingest(text).txns[0].txn_id == ingest(text).txns[0].txn_id
    assert ingest(text).report["txn_id_derived"]
