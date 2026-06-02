#!/usr/bin/env python3
"""
Rocksmith 2014 CDLC App ID Patcher

Unpacks a .psarc file, replaces the App ID in manifests and appid file,
then repacks it. Copies the result to the Rocksmith dlc folder.

Usage:
    python patcher.py <input.psarc> [--appid 258350] [--no-copy]
    python patcher.py ~/Downloads/*.psarc
"""

import struct
import zlib
import os
import sys
import shutil
import json
import logging
import re
import argparse
import tempfile
import hashlib
from pathlib import Path
from glob import glob

log = logging.getLogger("slopsmith.lib.patcher")

from Crypto.Cipher import AES

from safepath import safe_join

# PSARC constants
MAGIC = b"PSAR"
BLOCK_SIZE = 65536
ENTRY_SIZE = 30

# Rocksmith PSARC encryption key (for TOC only)
ARC_KEY = bytes.fromhex('C53DB23870A1A2F71CAE64061FDD0E1157309DC85204D4C5BFDF25090DF2572C')
ARC_IV = bytes.fromhex('E915AA018FEF71FC508132E4BB4CEB42')

# Default paths
DLC_DIR = Path.home() / ".local/share/Steam/steamapps/common/Rocksmith2014/dlc"
DEFAULT_APP_ID = "258350"  # Iron Maiden - Aces High

# Common CDLC App IDs that need replacing
CDLC_APP_IDS = ["248750", "248751"]  # Cherub Rock variants


def decrypt_toc(data):
    aes = AES.new(ARC_KEY, AES.MODE_CFB, iv=ARC_IV, segment_size=128)
    return aes.decrypt(data)


def encrypt_toc(data):
    aes = AES.new(ARC_KEY, AES.MODE_CFB, iv=ARC_IV, segment_size=128)
    return aes.encrypt(data)


def extract_entry(f, entry, block_sizes, block_size):
    f.seek(entry['offset'])
    if entry['length'] == 0:
        return b''

    num_blocks = (entry['length'] + block_size - 1) // block_size
    result = b''

    for i in range(num_blocks):
        bi = entry['z_index'] + i
        if bi < len(block_sizes):
            compressed_size = block_sizes[bi]
        else:
            compressed_size = 0

        if compressed_size == 0:
            remaining = entry['length'] - len(result)
            to_read = min(block_size, remaining)
            result += f.read(to_read)
        else:
            block_data = f.read(compressed_size)
            try:
                result += zlib.decompress(block_data)
            except:
                result += block_data

    return result[:entry['length']]


def unpack_psarc(filepath, output_dir):
    """Unpack a PSARC archive. Skips SNG decryption (not needed for patching)."""
    with open(filepath, 'rb') as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError("Not a PSARC file")

        version = struct.unpack('>I', f.read(4))[0]
        compression = f.read(4)
        toc_length = struct.unpack('>I', f.read(4))[0]
        toc_entry_size = struct.unpack('>I', f.read(4))[0]
        toc_entries = struct.unpack('>I', f.read(4))[0]
        block_size = struct.unpack('>I', f.read(4))[0]
        archive_flags = struct.unpack('>I', f.read(4))[0]

        # Read and decrypt entire TOC region (entries + block table) together
        toc_region_size = toc_length - 32
        toc_region_raw = f.read(toc_region_size)

        if archive_flags == 4:
            toc_region = decrypt_toc(toc_region_raw)
        else:
            toc_region = toc_region_raw

        toc_data_size = toc_entry_size * toc_entries
        toc_data = toc_region[:toc_data_size]
        bt_data = toc_region[toc_data_size:]

        entries = []
        for i in range(toc_entries):
            off = i * toc_entry_size
            ed = toc_data[off:off + toc_entry_size]
            z_index = struct.unpack('>I', ed[16:20])[0]
            length = int.from_bytes(ed[20:25], 'big')
            offset = int.from_bytes(ed[25:30], 'big')
            entries.append({'z_index': z_index, 'length': length, 'offset': offset})

        block_sizes = []
        for i in range(len(bt_data) // 2):
            block_sizes.append(int.from_bytes(bt_data[i * 2:i * 2 + 2], 'big'))

        file_list_data = extract_entry(f, entries[0], block_sizes, block_size)
        filenames = file_list_data.decode('utf-8', errors='ignore').strip().split('\n')

        output_dir = Path(output_dir).resolve()
        for entry, filename in zip(entries[1:], filenames):
            filename = filename.strip()
            if not filename:
                continue
            outpath = safe_join(output_dir, filename)
            if outpath is None:
                log.warning("patcher: rejected unsafe entry path %r", filename)
                continue
            if outpath == output_dir:
                log.warning("patcher: rejected entry resolving to output root %r", filename)
                continue
            try:
                # mkdir inside the try: a benign "subdir" data entry followed
                # by "subdir/file.txt" raises FileExistsError otherwise and
                # aborts the whole patch unpack.
                outpath.parent.mkdir(parents=True, exist_ok=True)
                data = extract_entry(f, entry, block_sizes, block_size)
                outpath.write_bytes(data)
            except Exception as e:
                # Preserve historical patcher fallback: leave an empty
                # placeholder so the surrounding patch flow can still replace
                # it. Suppress secondary errors (e.g. mkdir failed → no parent
                # dir for the placeholder) so one bad entry can't abort.
                log.warning("patcher: failed to extract %r: %s", filename, e)
                try:
                    outpath.write_bytes(b'')
                except OSError:
                    pass


def pack_psarc(input_dir, output_path):
    """Pack a directory into a PSARC archive."""
    input_dir = Path(input_dir)
    block_size = BLOCK_SIZE

    files = []
    for f in sorted(input_dir.rglob('*')):
        if f.is_file():
            rel = str(f.relative_to(input_dir))
            files.append((rel, f.read_bytes()))

    file_list = '\n'.join(name for name, _ in files) + '\n'
    file_list_bytes = file_list.encode('utf-8')

    all_data = [file_list_bytes] + [data for _, data in files]
    toc_entries = len(all_data)

    compressed_blocks = []
    block_sizes = []
    entry_info = []

    for entry_data in all_data:
        z_index = len(compressed_blocks)
        entry_blocks = []
        offset = 0

        while offset < len(entry_data):
            chunk = entry_data[offset:offset + block_size]
            compressed = zlib.compress(chunk)
            if len(compressed) < len(chunk):
                entry_blocks.append(compressed)
                block_sizes.append(len(compressed))
            else:
                entry_blocks.append(chunk)
                block_sizes.append(0)
            offset += block_size

        if not entry_blocks:
            entry_blocks.append(b'')
            block_sizes.append(0)

        compressed_blocks.extend(entry_blocks)
        entry_info.append({
            'z_index': z_index,
            'length': len(entry_data),
            'blocks': entry_blocks,
        })

    block_table = b''
    for bs in block_sizes:
        block_table += struct.pack('>H', bs)

    header_size = 32
    toc_data_size = ENTRY_SIZE * toc_entries
    toc_length = header_size + toc_data_size + len(block_table)

    current_offset = toc_length
    for info in entry_info:
        info['offset'] = current_offset
        for block in info['blocks']:
            current_offset += len(block)

    toc_data = b''
    for i, info in enumerate(entry_info):
        raw_data = all_data[i]
        md5 = hashlib.md5(raw_data).digest()
        z_index = struct.pack('>I', info['z_index'])
        length = info['length'].to_bytes(5, 'big')
        offset = info['offset'].to_bytes(5, 'big')
        toc_data += md5 + z_index + length + offset

    # Encrypt TOC entries + block table together (they form one encrypted region)
    toc_region = toc_data + block_table
    encrypted_region = encrypt_toc(toc_region)

    with open(output_path, 'wb') as out:
        out.write(MAGIC)
        out.write(struct.pack('>I', 65540))
        out.write(b'zlib')
        out.write(struct.pack('>I', toc_length))
        out.write(struct.pack('>I', ENTRY_SIZE))
        out.write(struct.pack('>I', toc_entries))
        out.write(struct.pack('>I', block_size))
        out.write(struct.pack('>I', 4))
        out.write(encrypted_region)
        for info in entry_info:
            for block in info['blocks']:
                out.write(block)


def patch_psarc(input_path, new_app_id, output_dir=None, copy_to_dlc=True):
    """Unpack a PSARC, patch App IDs, repack, and optionally copy to dlc folder."""
    input_path = Path(input_path)
    if not input_path.exists():
        log.warning("File not found: %s", input_path)
        return False

    log.info("Processing: %s", input_path.name)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        extract_dir = tmpdir / input_path.stem

        try:
            unpack_psarc(input_path, extract_dir)
        except Exception as e:
            log.warning("Failed to unpack %s: %s", input_path.name, e)
            return False

        patched_count = 0

        for appid_file in extract_dir.rglob("*.appid"):
            content = appid_file.read_text().strip()
            if content in CDLC_APP_IDS:
                appid_file.write_text(new_app_id)
                patched_count += 1
                log.debug("Patched appid: %s -> %s", content, new_app_id)

        for json_file in extract_dir.rglob("*.json"):
            content = json_file.read_text()
            new_content = content
            for old_id in CDLC_APP_IDS:
                new_content = new_content.replace(old_id, new_app_id)
            if new_content != content:
                json_file.write_text(new_content)
                patched_count += 1
                log.debug("Patched manifest: %s", json_file.name)

        for hsan_file in extract_dir.rglob("*.hsan"):
            content = hsan_file.read_text()
            new_content = content
            for old_id in CDLC_APP_IDS:
                new_content = new_content.replace(old_id, new_app_id)
            if new_content != content:
                hsan_file.write_text(new_content)
                patched_count += 1
                log.debug("Patched hsan: %s", hsan_file.name)

        if patched_count == 0:
            log.info("No App ID references found in %s (may already be patched)", input_path.name)
            if copy_to_dlc:
                dest = DLC_DIR / input_path.name
                shutil.copy2(input_path, dest)
                log.info("Copied as-is to: %s", dest)
            return True

        try:
            output_path = tmpdir / input_path.name
            pack_psarc(extract_dir, output_path)

            if copy_to_dlc:
                dest = DLC_DIR / input_path.name
                shutil.copy2(output_path, dest)
                log.info("Patched and copied to: %s", dest)
            elif output_dir:
                dest = Path(output_dir) / input_path.name
                shutil.copy2(output_path, dest)
                log.info("Patched and saved to: %s", dest)

            log.info("Done! (%d files patched)", patched_count)
            return True
        except Exception as e:
            log.warning("Failed to repack %s: %s", input_path.name, e)
            return False


def main():
    parser = argparse.ArgumentParser(description='Rocksmith 2014 CDLC App ID Patcher')
    parser.add_argument('files', nargs='+', help='Input .psarc files (supports globs)')
    parser.add_argument('--appid', default=DEFAULT_APP_ID,
                        help=f'Target App ID (default: {DEFAULT_APP_ID} = Iron Maiden - Aces High)')
    parser.add_argument('--no-copy', action='store_true',
                        help='Do not copy to Rocksmith dlc folder')
    parser.add_argument('--output', '-o', help='Output directory (instead of dlc folder)')

    args = parser.parse_args()

    success = 0
    failed = 0

    for pattern in args.files:
        for f in glob(pattern):
            if f.endswith('.psarc'):
                if patch_psarc(f, args.appid, output_dir=args.output,
                               copy_to_dlc=not args.no_copy and not args.output):
                    success += 1
                else:
                    failed += 1
            else:
                log.warning("Skipping (not a .psarc file): %s", f)

    log.info("Done: %d patched, %d failed", success, failed)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    main()
