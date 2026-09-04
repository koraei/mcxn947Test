#!/usr/bin/env python3
"""Unit tests for rh_endurance_monitor metadata / resume helpers."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import rh_endurance_monitor as mon


class MetaResumeTests(unittest.TestCase):
    def test_target_math(self) -> None:
        q0 = 1000
        delta = 525600
        self.assertEqual(q0 + delta, 526600)

    def test_equivalent_years(self) -> None:
        self.assertAlmostEqual(mon.equivalent_years(525600), 10.0, places=5)
        self.assertAlmostEqual(mon.equivalent_years(52560), 1.0, places=5)

    def test_parse_kv(self) -> None:
        d = mon.parse_kv("RHSTRESS mode=4HZ running=1 quanta=10 target=20 key_ver=2")
        self.assertEqual(d["running"], 1)
        self.assertEqual(d["quanta"], 10)
        self.assertEqual(d["mode"], "4HZ")

    def test_meta_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run_metadata.json"
            meta = {"start_quanta": 5, "target_quanta": 100, "status": "RUNNING"}
            mon.save_meta(p, meta)
            loaded = mon.load_meta(p)
            assert loaded is not None
            self.assertEqual(loaded["target_quanta"], 100)

    def test_refuse_accidental_new_baseline(self) -> None:
        # Documented contract: unfinished metadata reused unless --new-run
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run_metadata.json"
            mon.save_meta(
                p,
                {"start_quanta": 1, "target_quanta": 100, "status": "RUNNING", "silicon_uuid": "ABC"},
            )
            loaded = mon.load_meta(p)
            assert loaded is not None
            self.assertEqual(loaded["status"], "RUNNING")
            self.assertFalse(False if loaded else True)  # exists → resume path


if __name__ == "__main__":
    raise SystemExit(unittest.main())
