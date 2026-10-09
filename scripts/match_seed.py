"""Match seed (Nick, 2026-09-27: "sometimes in CPU I get the exact same game", then "we want to be able to pick a seed
to replay"): the seed of the game's match RNG, picked. Feature "match-seed" (Testing, with CPU vs CPU); off by default.
Option "seed": a number 0..0xFFFFFFFF replays: every match seeds with it, so CPU vs CPU with the same teams and
stadium plays out the same game again. None (blank): every match seeds from the console clock, so games differ.
Either way the match's seed is saved (SAVE, in the item section; the build log names it) for a RAM dump to read.
The RNG itself: docs/rng.md.

The match RNG (*(r13-0x1578), rand(n) = FUN_80165C14) is made at match start (0x8012DB9C -> FUN_801659B8) and freed at
match end (0x8012DD14). The creator builds a Mersenne Twister (FUN_8050A134, 0x9C4 bytes: 624 words) with the seed
`li r4,-1` at 0x80165A14, takes two draws from it (FUN_8050A310) and mixes them with the match object *(r13-0x165C)
+0 / +4 into the RNG's two 15-bit words. Nothing on the way reads a clock, so with no human input (CPU vs CPU: the
same calls on the same play frames) every match with the same teams and stadium plays out the same: stock is seed
0xFFFFFFFF. A human's timing moves which frame each roll lands on, so a seed replays CPU vs CPU games only.

SEED 0x80165A14 (`li r4,-1`) -> b stub: r4 = the seed (lis / ori), or the time base (mftb r4, the lower word: the
console and Dolphin start it from the real-time clock, 60.75 MHz), stored to SAVE, then back to the twister init's
`bl`. r12 is free (the heap call before it). Seed 0 takes FUN_8050A134's r4 == 0 path, its built-in table: a
twister too, and the same every time.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm, branch  # noqa: E402

SEED = 0x80165A14
SEED_ORIG = 0x3880FFFF                                  # li r4,-1
MFTB_R4 = 0x7C8C42E6                                    # mftb r4 (mfspr r4, TBL = 268)
LAYOUT = {}                                             # "save", "stub": their addresses (tests)


def parse(value):
    """A seed from the patcher (an int, "1234", "0x5EED" or blank) -> int 0..0xFFFFFFFF, or None (the clock).
    ValueError with a message for anything else."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        n = value if isinstance(value, int) and not isinstance(value, bool) else int(str(value).strip(), 0)
    except ValueError:
        raise ValueError(f"Seed {value!r} isn't a number: type one like 1234, or leave it blank for a new game "
                         f"every match.") from None
    if not 0 <= n <= 0xFFFFFFFF:
        raise ValueError(f"Seed {n} is out of range: 0 to 4294967295.")
    return n


def stub(base, seed, save):
    a = Asm(base)
    if seed is None:
        a.word(MFTB_R4)
    else:
        a.lis(4, seed >> 16).ori(4, 4, seed & 0xFFFF)
    a.load_addr(12, save).stw(4, 0, 12)
    a.b(SEED + 4)                                       # bl FUN_8050A134
    return a


def apply(dol, code, seed=None):
    """Seed every match's RNG with `seed` (None: the time base); the stub and SAVE go in `code` (the item section)."""
    seed = parse(seed)
    got = dol.u32(SEED)
    assert got == SEED_ORIG, f"0x{SEED:08X}: 0x{got:08X}, expected 0x{SEED_ORIG:08X}"
    save = LAYOUT["save"] = code.put(bytes(4), align=4)
    at = LAYOUT["stub"] = code.here + (-code.here % 4)
    assert code.put(stub(at, seed, save).assemble(), align=4) == at
    dol.w32(SEED, branch(SEED, at))
    how = "the console clock (a new game every match)" if seed is None else f"{seed} (0x{seed:08X}: replays)"
    return [f"match seed: every match's RNG seeded with {how}; the seed is saved at 0x{save:08X} "
            f"(0x{SEED:08X} -> 0x{at:08X})"]
