from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from pretrend.pipeline.text.adapters.sec_edgar import SECEdgarAdapter


def _make_filings_block(entries: list[dict]) -> dict:
    block = {
        "form": [],
        "filingDate": [],
        "accessionNumber": [],
        "primaryDocument": [],
    }
    for e in entries:
        block["form"].append(e["form"])
        block["filingDate"].append(e["filingDate"])
        block["accessionNumber"].append(e["accession"])
        block["primaryDocument"].append(e["primaryDoc"])
    return block


class TestIterAllFilings:
    def test_recent_only_no_files(self) -> None:
        adapter = SECEdgarAdapter(seed_tickers=["AAPL"])
        recent = _make_filings_block(
            [
                {
                    "form": "8-K",
                    "filingDate": "2024-01-15",
                    "accession": "0001-24-000001",
                    "primaryDoc": "doc.htm",
                }
            ]
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"filings": {"recent": recent, "files": []}}

        with patch.object(adapter, "_get", return_value=mock_resp):
            results = list(adapter._iter_all_filings(320193))

        assert results == [("8-K", "2024-01-15", "0001-24-000001", "doc.htm")]

    def test_recent_plus_one_page(self) -> None:
        adapter = SECEdgarAdapter(seed_tickers=["AAPL"])
        recent = _make_filings_block(
            [
                {
                    "form": "10-K",
                    "filingDate": "2024-01-20",
                    "accession": "0001-24-000010",
                    "primaryDoc": "10k.htm",
                }
            ]
        )
        page_block = _make_filings_block(
            [
                {
                    "form": "8-K",
                    "filingDate": "2010-06-15",
                    "accession": "0001-10-000001",
                    "primaryDoc": "8k.htm",
                },
                {
                    "form": "10-Q",
                    "filingDate": "2010-03-10",
                    "accession": "0001-10-000002",
                    "primaryDoc": "10q.htm",
                },
            ]
        )
        main_resp = MagicMock()
        main_resp.json.return_value = {
            "filings": {
                "recent": recent,
                "files": [
                    {
                        "name": "CIK0000320193-submissions-001.json",
                        "filingCount": 2,
                        "filingFrom": "2010-03-10",
                        "filingTo": "2010-06-15",
                    }
                ],
            }
        }
        page_resp = MagicMock()
        page_resp.json.return_value = page_block

        def mock_get(url: str):
            if "submissions-001" in url:
                return page_resp
            return main_resp

        with patch.object(adapter, "_get", side_effect=mock_get):
            results = list(adapter._iter_all_filings(320193))

        assert len(results) == 3
        assert {r[0] for r in results} == {"10-K", "8-K", "10-Q"}

    def test_page_fetch_failure_skips(self) -> None:
        adapter = SECEdgarAdapter(seed_tickers=["AAPL"])
        recent = _make_filings_block(
            [
                {
                    "form": "8-K",
                    "filingDate": "2024-01-15",
                    "accession": "0001-24-000001",
                    "primaryDoc": "doc.htm",
                }
            ]
        )
        main_resp = MagicMock()
        main_resp.json.return_value = {
            "filings": {
                "recent": recent,
                "files": [
                    {
                        "name": "CIK0000320193-submissions-001.json",
                        "filingCount": 500,
                        "filingFrom": "2006-01-01",
                        "filingTo": "2015-03-11",
                    }
                ],
            }
        }

        def mock_get(url: str):
            if "submissions-001" in url:
                return None
            return main_resp

        with patch.object(adapter, "_get", side_effect=mock_get):
            results = list(adapter._iter_all_filings(320193))

        assert len(results) == 1

    def test_outside_date_range_page_skipped(self) -> None:
        adapter = SECEdgarAdapter(seed_tickers=["AAPL"])
        recent = _make_filings_block([])
        main_resp = MagicMock()
        main_resp.json.return_value = {
            "filings": {
                "recent": recent,
                "files": [
                    {
                        "name": "CIK0000320193-submissions-001.json",
                        "filingCount": 500,
                        "filingFrom": "1994-01-26",
                        "filingTo": "2015-03-11",
                    }
                ],
            }
        }

        with patch.object(adapter, "_get", return_value=main_resp) as mock_get:
            results = list(
                adapter._iter_all_filings(
                    320193,
                    start_dt=date(2020, 1, 1),
                    end_dt=date(2020, 12, 31),
                )
            )

        assert results == []
        assert mock_get.call_count == 1


class TestFetchFilingsForCikPaginated:
    def test_old_filings_from_pagination_included(self) -> None:
        adapter = SECEdgarAdapter(seed_tickers=["AAPL"])
        recent = _make_filings_block(
            [
                {
                    "form": "8-K",
                    "filingDate": "2024-01-15",
                    "accession": "0001-24-000001",
                    "primaryDoc": "doc.htm",
                }
            ]
        )
        page_block = _make_filings_block(
            [
                {
                    "form": "8-K",
                    "filingDate": "2010-06-15",
                    "accession": "0001-10-000001",
                    "primaryDoc": "8k.htm",
                }
            ]
        )
        main_resp = MagicMock()
        main_resp.json.return_value = {
            "filings": {
                "recent": recent,
                "files": [
                    {
                        "name": "CIK0000320193-submissions-001.json",
                        "filingCount": 1,
                        "filingFrom": "2010-06-15",
                        "filingTo": "2010-06-15",
                    }
                ],
            }
        }
        page_resp = MagicMock()
        page_resp.json.return_value = page_block
        download_resp = MagicMock()
        download_resp.text = "<html>Filing body</html>"

        def mock_get(url: str):
            if "submissions-001" in url:
                return page_resp
            if "Archives" in url:
                return download_resp
            return main_resp

        with patch.object(adapter, "_get", side_effect=mock_get):
            docs = list(
                adapter._fetch_filings_for_cik(
                    "AAPL",
                    320193,
                    date(2010, 1, 1),
                    date(2010, 12, 31),
                )
            )

        assert len(docs) == 1
        assert docs[0]["title"] == "AAPL 8-K 2010-06-15"
        assert docs[0]["body"] == "<html>Filing body</html>"
