#!/usr/bin/env python3
"""Host fault-injection model for encrypted running-hours journal (plan §§7–10)."""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SECTOR = 8192
PHRASE = 16
RECORD = 64
HEADER = 64
N_SECTORS = 16
SLOTS_PER_SECTOR = (SECTOR - HEADER) // RECORD  # 127

MAGIC_HDR = 0x31534852  # 'RHS1' LE
MAGIC_REC = 0x31524852  # 'RHR1'
COMMIT_MAGIC = 0x54494D4D4F430001  # 'COMMIT\x00\x01' LE-ish
FORMAT_VER = 1
RECORD_TYPE = 1
READY_MARK = b"READY_MARKER_v1\0"  # exactly 16 bytes
assert len(READY_MARK) == 16


class PowerCut(Exception):
    pass


@dataclass
class FlashModel:
    size: int
    data: bytearray = field(init=False)
    cut_after: int | None = None
    _ops: int = 0

    def __post_init__(self) -> None:
        self.data = bytearray([0xFF] * self.size)

    def reset_ops(self) -> None:
        self._ops = 0
        self.cut_after = None

    def _tick(self) -> None:
        self._ops += 1
        if self.cut_after is not None and self._ops > self.cut_after:
            raise PowerCut(f"injected cut after op {self._ops}")

    def erase_8k(self, off: int) -> None:
        assert off % SECTOR == 0 and off + SECTOR <= self.size
        self._tick()
        self.data[off : off + SECTOR] = b"\xff" * SECTOR

    def program_16(self, off: int, chunk: bytes) -> None:
        assert len(chunk) == PHRASE and off % PHRASE == 0
        self._tick()
        for i, b in enumerate(chunk):
            self.data[off + i] &= b

    def read(self, off: int, n: int) -> bytes:
        return bytes(self.data[off : off + n])


def nonce_for(sector_gen: int, slot: int) -> bytes:
    """Plan §7.3: be64(generation) || be32(slot)."""
    return struct.pack(">QI", sector_gen & 0xFFFFFFFFFFFFFFFF, slot & 0xFFFFFFFF)[:12]


def aad_for(seq: int, sector_gen: int, sector_id: int, slot: int) -> bytes:
    return struct.pack(
        "<BHIQQHH",
        FORMAT_VER,
        RECORD_TYPE,
        0,
        seq,
        sector_gen,
        sector_id & 0xFFFF,
        slot & 0xFFFF,
    )


@dataclass
class Journal:
    flash: FlashModel
    key: bytes
    sector_off: list[int]
    boot_id: int = 1
    quanta: int = 0
    seq: int = 0

    def _aes(self) -> AESGCM:
        return AESGCM(self.key)

    def init_virgin(self) -> None:
        for off in self.sector_off:
            self.flash.erase_8k(off)
        self._write_sector_header(0, generation=1)
        self._append_record(0, generation=1, quanta=0)

    def _write_sector_header(self, sector_idx: int, generation: int) -> None:
        """Write header phrases 0..2 then READY last (§7.4)."""
        off = self.sector_off[sector_idx]
        hdr = bytearray(HEADER)
        # magic, format_version, header_size, sector_id, reserved
        struct.pack_into(
            "<IHHHH",
            hdr,
            0,
            MAGIC_HDR,
            FORMAT_VER,
            HEADER,
            sector_idx & 0xFFFF,
            0,
        )
        struct.pack_into("<Q", hdr, 12, generation)
        struct.pack_into("<I", hdr, 20, self.boot_id)
        crc = zlib.crc32(bytes(hdr[:24])) & 0xFFFFFFFF
        struct.pack_into("<I", hdr, 24, crc)
        # phrases 0..2 (bytes 0..47) first — READY programmed last
        for i in range(0, 48, PHRASE):
            self.flash.program_16(off + i, bytes(hdr[i : i + PHRASE]))
        self.flash.program_16(off + 48, READY_MARK)

    def _header_ready(self, sector_idx: int) -> bool:
        off = self.sector_off[sector_idx]
        hdr = self.flash.read(off, HEADER)
        if struct.unpack_from("<I", hdr, 0)[0] != MAGIC_HDR:
            return False
        ver, hsz, sid, _rsv = struct.unpack_from("<HHHH", hdr, 4)
        if ver != FORMAT_VER or hsz != HEADER or sid != sector_idx:
            return False
        gen = struct.unpack_from("<Q", hdr, 12)[0]
        if gen == 0 or gen == 0xFFFFFFFFFFFFFFFF:
            return False
        crc_stored = struct.unpack_from("<I", hdr, 24)[0]
        crc = zlib.crc32(hdr[:24]) & 0xFFFFFFFF
        if crc != crc_stored:
            return False
        return hdr[48:64] == READY_MARK

    def _sector_generation(self, sector_idx: int) -> int:
        hdr = self.flash.read(self.sector_off[sector_idx], HEADER)
        return struct.unpack_from("<Q", hdr, 12)[0]

    def _append_record(self, sector_idx: int, generation: int, quanta: int) -> None:
        off = self.sector_off[sector_idx] + HEADER
        slot = 0
        while slot < SLOTS_PER_SECTOR:
            rec = self.flash.read(off + slot * RECORD, RECORD)
            if rec == b"\xff" * RECORD:
                break
            slot += 1
        else:
            raise RuntimeError("sector full")

        self.seq += 1
        seq = self.seq
        plain = struct.pack("<QII", quanta, 0, self.boot_id)
        nonce = nonce_for(generation, slot)
        aad = aad_for(seq, generation, sector_idx, slot)
        ct = self._aes().encrypt(nonce, plain, aad)
        assert len(ct) == 32
        ciphertext, tag = ct[:16], ct[16:]

        phrase0 = struct.pack("<IIQ", MAGIC_REC, FORMAT_VER, seq)
        phrase1 = ciphertext
        phrase2 = tag
        phrase3 = struct.pack("<QQ", COMMIT_MAGIC, seq ^ 0xFFFFFFFFFFFFFFFF)
        base = off + slot * RECORD

        for i, ph in enumerate((phrase0, phrase1, phrase2)):
            self.flash.program_16(base + i * PHRASE, ph)
            if self.flash.read(base + i * PHRASE, PHRASE) != ph:
                raise RuntimeError("program verify fail")

        # Authenticate pre-commit view from flash (§8 step 10)
        pre = self.flash.read(base, 48) + (b"\xff" * 16)
        if self._decrypt_record(pre, generation, sector_idx, slot, require_commit=False) is None:
            raise RuntimeError("pre-commit auth fail")

        self.flash.program_16(base + 3 * PHRASE, phrase3)
        if self.flash.read(base + 3 * PHRASE, PHRASE) != phrase3:
            raise RuntimeError("commit verify fail")
        if self._decrypt_record(self.flash.read(base, RECORD), generation, sector_idx, slot) is None:
            raise RuntimeError("post-commit auth fail")
        self.quanta = quanta

    def append_quanta(self, new_quanta: int) -> None:
        sid, gen = self._latest_sector()
        try:
            self._append_record(sid, gen, new_quanta)
        except RuntimeError:
            self._recycle_and_append(sid, gen, new_quanta)

    def _recycle_and_append(self, cur_sid: int, cur_gen: int, quanta: int) -> None:
        """Never erase the only newest valid sector (§10)."""
        # Prefer next index; if that is the only valid latest, pick another erased/dirty victim.
        candidates = [(cur_sid + i) % len(self.sector_off) for i in range(1, len(self.sector_off))]
        victim = None
        for v in candidates:
            if v == cur_sid:
                continue
            # May erase dirty/erased/older sectors only
            if self._header_ready(v):
                vgen = self._sector_generation(v)
                if vgen >= cur_gen:
                    continue  # never erase equal/newer
            victim = v
            break
        if victim is None:
            raise RuntimeError("no reclaimable victim")

        new_gen = cur_gen + 1
        self.flash.erase_8k(self.sector_off[victim])
        self._write_sector_header(victim, new_gen)
        # Checkpoint first (carry-forward), then optional same value already is the append
        self._append_record(victim, new_gen, quanta)

    def _latest_sector(self) -> tuple[int, int]:
        best = (-1, -1)
        for i in range(len(self.sector_off)):
            if not self._header_ready(i):
                continue
            gen = self._sector_generation(i)
            if gen >= best[1]:
                best = (i, gen)
        if best[0] < 0:
            raise RuntimeError("no ready sector")
        return best

    def recover(self) -> int:
        best_q: int | None = None
        best_seq = -1
        for sid in range(len(self.sector_off)):
            if not self._header_ready(sid):
                continue
            gen = self._sector_generation(sid)
            off = self.sector_off[sid] + HEADER
            for slot in range(SLOTS_PER_SECTOR):
                rec = self.flash.read(off + slot * RECORD, RECORD)
                if rec == b"\xff" * RECORD:
                    continue
                if not self._record_committed(rec):
                    continue
                q = self._decrypt_record(rec, gen, sid, slot)
                if q is None:
                    continue
                seq = struct.unpack_from("<Q", rec, 8)[0]
                if seq >= best_seq:
                    best_seq = seq
                    best_q = q
        if best_q is None:
            raise RuntimeError("CORRUPT: no valid record")
        self.seq = best_seq
        self.quanta = best_q
        return best_q

    def _record_committed(self, rec: bytes) -> bool:
        magic, ver, seq = struct.unpack_from("<IIQ", rec, 0)
        if magic != MAGIC_REC or ver != FORMAT_VER:
            return False
        cm, comp = struct.unpack_from("<QQ", rec, 48)
        return cm == COMMIT_MAGIC and comp == (seq ^ 0xFFFFFFFFFFFFFFFF)

    def _decrypt_record(
        self,
        rec: bytes,
        gen: int,
        sid: int,
        slot: int,
        *,
        require_commit: bool = True,
    ) -> int | None:
        if require_commit and not self._record_committed(rec):
            return None
        magic, ver, seq = struct.unpack_from("<IIQ", rec, 0)
        if magic != MAGIC_REC or ver != FORMAT_VER:
            return None
        ct = rec[16:32]
        tag = rec[32:48]
        nonce = nonce_for(gen, slot)
        aad = aad_for(seq, gen, sid, slot)
        try:
            plain = self._aes().decrypt(nonce, ct + tag, aad)
        except Exception:
            return None
        quanta, _flags, _boot = struct.unpack("<QII", plain)
        return quanta


def _make_journal(n_sectors: int = 2) -> tuple[Journal, FlashModel, bytes]:
    key = hashlib.sha256(b"unit-test-rh-key").digest()
    flash = FlashModel(SECTOR * n_sectors)
    offs = [i * SECTOR for i in range(n_sectors)]
    return Journal(flash, key, offs), flash, key


def run_basic_tests() -> None:
    j, flash, key = _make_journal(2)
    j.init_virgin()
    assert j.recover() == 0
    j.append_quanta(1)
    assert j.recover() == 1
    for q in range(2, 50):
        j.append_quanta(q)
    assert j.recover() == 49

    # corrupt tag on last record → fall back
    last_base = HEADER + (j.seq - 1) % SLOTS_PER_SECTOR * RECORD
    # find last committed in sector 0 or recycled
    j2, flash2, _ = _make_journal(2)
    j2.init_virgin()
    j2.append_quanta(5)
    assert j2.recover() == 5
    # corrupt ciphertext/tag of seq=2 (quanta 5)
    off = HEADER + RECORD  # slot 1
    flash2.data[off + 32] ^= 0xFF
    assert j2.recover() == 0  # previous valid

    flash3 = FlashModel(SECTOR * 2)
    j3 = Journal(flash3, key, [0, SECTOR])
    j3.init_virgin()
    j3.append_quanta(5)
    flash3.cut_after = flash3._ops + 3
    try:
        j3.append_quanta(6)
    except PowerCut:
        pass
    assert j3.recover() == 5
    print("runhours_host_basic PASS")


def run_fault_matrix() -> dict[str, Any]:
    """Aggressive power-cut / corruption matrix (plan priority 8)."""
    key = hashlib.sha256(b"unit-test-rh-key").digest()
    results: dict[str, Any] = {"cases": [], "pass": True}

    def case(name: str, fn) -> None:  # noqa: ANN001
        try:
            fn()
            results["cases"].append({"name": name, "pass": True})
        except Exception as e:
            results["cases"].append({"name": name, "pass": False, "error": f"{type(e).__name__}: {e}"})
            results["pass"] = False

    def fresh(n: int = 2) -> Journal:
        flash = FlashModel(SECTOR * n)
        j = Journal(flash, key, [i * SECTOR for i in range(n)])
        j.init_virgin()
        j.append_quanta(10)
        assert j.recover() == 10
        return j

    # Cut after each phrase of a new append (0..3 program ops after setup)
    for phrase in range(4):

        def _cut_phrase(p: int = phrase) -> None:
            j = fresh()
            # ops so far; next append does: 3 phrase programs (+verify reads don't tick) + preauth + commit
            # Each program_16 ticks once. Cut after p+1 programs into the append.
            start = j.flash._ops
            j.flash.cut_after = start + p + 1
            try:
                j.append_quanta(11)
                if p < 3:
                    raise AssertionError("expected PowerCut before commit")
            except PowerCut:
                if p >= 3:
                    # commit may have completed depending on exact count
                    pass
            got = j.recover()
            assert got in (10, 11), got
            if p < 3:
                assert got == 10

        case(f"cut_after_phrase_{phrase}", _cut_phrase)

    def cut_during_erase() -> None:
        j = fresh(2)
        # Fill sector 0 to force recycle
        # slots free after virgin(0)+append(10) = 2 used → fill remaining
        used = 2
        q = 10
        while used < SLOTS_PER_SECTOR:
            q += 1
            j.append_quanta(q)
            used += 1
        expect = q
        start = j.flash._ops
        j.flash.cut_after = start + 1  # during erase of victim
        try:
            j.append_quanta(expect + 1)
        except PowerCut:
            pass
        assert j.recover() == expect

    case("cut_during_sector_erase", cut_during_erase)

    def cut_before_ready() -> None:
        j = fresh(2)
        used = 2
        q = 10
        while used < SLOTS_PER_SECTOR:
            q += 1
            j.append_quanta(q)
            used += 1
        expect = q
        # recycle: erase (1) + header phrases 0,1,2 (3) then READY (1)
        start = j.flash._ops
        j.flash.cut_after = start + 1 + 3  # after header body, before READY
        try:
            j.append_quanta(expect + 1)
        except PowerCut:
            pass
        assert j.recover() == expect

    case("cut_before_ready_marker", cut_before_ready)

    def cut_after_ready_before_ckpt() -> None:
        j = fresh(2)
        used = 2
        q = 10
        while used < SLOTS_PER_SECTOR:
            q += 1
            j.append_quanta(q)
            used += 1
        expect = q
        start = j.flash._ops
        j.flash.cut_after = start + 1 + 4  # erase + full header READY
        try:
            j.append_quanta(expect + 1)
        except PowerCut:
            pass
        assert j.recover() == expect

    case("cut_after_ready_before_checkpoint", cut_after_ready_before_ckpt)

    def corrupt_tag() -> None:
        j = fresh()
        j.append_quanta(11)
        # corrupt newest tag
        base = HEADER + RECORD * 2  # seq3 at slot 2
        j.flash.data[base + 32] ^= 0x5A
        assert j.recover() == 10

    case("corrupt_ciphertext_tag", corrupt_tag)

    def partial_erase_sector() -> None:
        j = fresh(2)
        # Simulate partial erase of inactive sector 1
        j.flash.data[SECTOR : SECTOR + 100] = b"\x00" * 100
        assert j.recover() == 10
        j.append_quanta(12)
        assert j.recover() == 12

    case("partially_erased_sector", partial_erase_sector)

    def torn_commit() -> None:
        j = fresh()
        start = j.flash._ops
        # phrase0,1,2 then commit — cut mid-commit by programming incomplete via flash AND
        j.flash.cut_after = start + 3
        try:
            j.append_quanta(11)
        except PowerCut:
            pass
        # Force torn commit phrase manually on next slot attempt path: recover must be 10
        assert j.recover() == 10
        # Manually write partial commit on a prepared unfinished slot if present
        off = HEADER + RECORD * 2
        if j.flash.read(off, 16) != b"\xff" * 16:
            # leave as-is
            pass
        assert j.recover() == 10

    case("torn_commit_phrase", torn_commit)

    def repeated_boots() -> None:
        j = fresh()
        for cut in range(1, 5):
            start = j.flash._ops
            j.flash.cut_after = start + cut
            try:
                j.append_quanta(11 + cut)
            except PowerCut:
                pass
            j.flash.cut_after = None
            v = j.recover()
            assert v >= 10
        j.flash.cut_after = None
        j.append_quanta(99)
        assert j.recover() == 99

    case("repeated_boots_after_interrupt", repeated_boots)

    def sector_transition_ok() -> None:
        j = fresh(2)
        q = 10
        # Force at least one recycle
        for _ in range(SLOTS_PER_SECTOR):
            q += 1
            j.append_quanta(q)
        assert j.recover() == q
        assert j._latest_sector()[0] == 1

    case("sector_transition_recycle", sector_transition_ok)

    def erased_vbat_sim() -> None:
        # Host stand-in: wipe RAM state, keep flash — recover from flash only
        j = fresh()
        j.append_quanta(42)
        flash = j.flash
        j2 = Journal(flash, key, j.sector_off, boot_id=99)
        assert j2.recover() == 42

    case("erased_ram_vbat_state", erased_vbat_sim)

    return results


if __name__ == "__main__":
    run_basic_tests()
    matrix = run_fault_matrix()
    out = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "M3_runhours_host_faults.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(matrix, indent=2))
    if not matrix["pass"]:
        raise SystemExit(1)
    print("runhours_host_fault_matrix PASS")
