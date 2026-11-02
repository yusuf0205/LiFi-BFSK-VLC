"""PC tool helpers: log parsing and the file-transfer layer."""
import os

from lifi_link import BertEvent, FileReceiver, FrameEvent, StatEvent, file_to_chunks, parse_line


def test_parse_esp32_frame_line():
    ev = parse_line("#FRAME,1,0,5,48.2,13.9,0.912,0,3,1,68656c6c6f")
    assert isinstance(ev, FrameEvent) and ev.ok and ev.payload == b"hello" and ev.snr_db == 13.9


def test_parse_uno_frame_line():
    ev = parse_line("#FRAME,1,1,2,4,4869")
    assert isinstance(ev, FrameEvent) and ev.fec and ev.payload == b"Hi" and ev.corrected == 4


def test_parse_bert_and_stat():
    b = parse_line("#BERT,10,2560,3,1.172e-03,0")
    assert isinstance(b, BertEvent) and b.errors == 3 and abs(b.ber - 1.172e-3) < 1e-9
    s = parse_line("#STAT,123,47994,10,9,1,9,2304,0,0.000e+00,47.1")
    assert isinstance(s, StatEvent) and s.fs_meas == 47994 and s.crc_fail == 1
    assert parse_line("RX ok \"x\"") is None and parse_line("#FRAME,garbage") is None


def test_file_chunks_roundtrip_out_of_order_and_duplicates():
    data = os.urandom(1234)
    chunks = file_to_chunks("pic.bin", data, file_id=7)
    assert all(len(c) <= 255 for c in chunks)
    rx = FileReceiver()
    for c in reversed(chunks + chunks[2:4]):
        fa = rx.feed(c)
    assert fa.verified() and fa.name == "pic.bin" and fa.data() == data


def test_file_missing_chunk_detected():
    chunks = file_to_chunks("a.txt", b"x" * 900)
    rx = FileReceiver()
    for c in chunks[:2] + chunks[3:]:
        fa = rx.feed(c)
    assert not fa.complete() and fa.missing() == [2]
