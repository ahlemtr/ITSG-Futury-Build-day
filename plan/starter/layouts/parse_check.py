"""Minimal reader for DTA EEL fixed-width records, driven by the YAML layouts.
Usage: python parse_check.py <TEEL0 file>"""
import sys, yaml, pathlib
HERE = pathlib.Path(__file__).parent
LAYOUT = {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in HERE.glob("*.yaml")}

def cut(line, f, base=0):
    return line[base + f["start"] - 1: base + f["end"]]

def read_block(line, pos, name):
    lay = LAYOUT[name]
    out = {f["name"]: cut(line, f, pos) for f in lay["fields"]}
    length = lay["fixed_length"]
    rg = lay.get("repeating_group")
    if rg:
        groups = []
        for k in range(int(out[rg["count_field"]])):
            base = pos + rg["starts_at"] - 1 + k * rg["group_length"]
            groups.append({f["name"].replace("{nn}", str(k + 1)):
                           line[base + f["offset_in_group"] - 1: base + f["offset_in_group"] - 1 + f["length"]]
                           for f in rg["fields"]})
        out["groups"] = groups
        length += int(out[rg["count_field"]]) * rg["group_length"]
    return out, length

def read_dslw(line):
    head = {f["name"]: cut(line, f) for f in LAYOUT["DSLW"]["fields"]}
    pos, blocks, problems = 224, {}, []
    for blk, flag in zip(LAYOUT["DSLW"]["block_order"], [f["name"] for f in LAYOUT["DSLW"]["fields"] if f["name"].startswith("MM-")]):
        if head[flag] != "J":
            continue
        if line[pos:pos + 4] != blk:
            problems.append(f"{flag}=J but found {line[pos:pos+4]!r} at {pos+1}")
            break
        blocks[blk], length = read_block(line, pos, blk)
        pos += length
    if pos != len(line):
        problems.append(f"record length {len(line)}, layouts account for {pos}")
    return head, blocks, problems

if __name__ == "__main__":
    for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        if line.startswith("DSLW"):
            head, blocks, problems = read_dslw(line)
            print({k: v.strip() for k, v in head.items() if v.strip()})
            for b, v in blocks.items():
                print(b, {k: (x.strip() if isinstance(x, str) else x) for k, x in v.items()})
            print("PROBLEMS:", problems or "none")
