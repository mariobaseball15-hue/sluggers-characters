"""Batting item patches: some batters always get an item, some always get the same item.

FUN_80455598 (batting setup) gives the batter an item only when items are on (*(r13-0xB00)+0xC) and
FUN_8015c800(team, batter slot, next batter slot) == 2 (good chemistry); the item itself is a weighted
random pick in FUN_804583c4 (enabled items, weighted by score difference), not tied to the next batter.

HOOK 0x8045564C replaces `subi r0,r3,0x2`, the first use of the chemistry result (r31 = batter slot,
r28 = on-deck slot). If the result isn't already 2 and the ON-DECK character (u16 id at +0 of the runtime
record *(r13-0x2C8) + team*0x4FE + slot*0x8E, team = FUN_801319bc()+0x2A, as FUN_8015c800 reads it) is
in ALWAYS_ITEM, the result becomes 2. The on-deck chemistry icon (FUN_80333440) is left as is.

ITEM_HOOK 0x80455678 replaces `mr r30,r3` right after the roulette pick (r3 = FUN_804583c4's item,
r28 = on-deck slot still). If the on-deck character is in FIXED_ITEM, r3 becomes that item. The
result is stored at manager+0x338 per slot and becomes the active item (+0x394) that
COjyamaManager (FUN_80455394) dispatches on.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ppc import Asm  # noqa: E402

HOOK, HOOK_ORIG = 0x8045564C, 0x3803FFFE    # subi r0,r3,0x2
ITEM_HOOK, ITEM_HOOK_ORIG = 0x80455678, 0x7C7E1B78  # mr r30,r3
BATTING_TEAM = 0x801319BC                   # returns the object whose +0x2A is the team FUN_8015c800 takes
WARIO, WALUIGI = 0x0A, 0x0B
ALWAYS_ITEM = [WARIO, WALUIGI]   # Nick: not Fire Bro (he gets Fireballs only when he earns an item: FIXED_ITEM)
# Whose character decides: the ON-DECK batter (r28 = next batter slot, the one FUN_8015c800 pairs
# with the batter; set at 0x80455634 and untouched until 0x80455690), since in the game the item comes
# from the on-deck character (Nick). Was the batter (r31).
SLOT_REG = 28

# Roulette result -> item (COjyamaManager pools): 0 Shell, 1 Fireball x3, 2 Bob-omb, 3 POW, 4 Banana x5, 5 Boo
SHELL, FIREBALL, BOBOMB, POW, BANANA, BOO = range(6)
STAR_BITS = 6                                        # the cut Thunder slot (starbits_roulette / starbits_item)
GREEN_KOOPA, RED_KOOPA = 0x0C, 0x2A                 # stat-editor charList 12, 42
RED_PARATROOPA, GREEN_PARATROOPA = 0x14, 0x2B       # 20, 43
BOWSER, BOO_CHAR, KING_BOO = 0x09, 0x0E, 0x25          # 9, 14, 37
HAMMER_BRO, FIRE_BRO, BOOMERANG_BRO = 0x1B, 0x34, 0x35  # 27, 52, 53
FIXED_ITEM = {GREEN_KOOPA: SHELL, RED_KOOPA: SHELL, RED_PARATROOPA: SHELL, GREEN_PARATROOPA: SHELL,
              BOO_CHAR: BOO, KING_BOO: BOO,
              FIRE_BRO: FIREBALL, BOWSER: FIREBALL}   # Nick: Fire Bro and Bowser; not Hammer/Boomerang Bro
# Rosalina, the Lumas and Lubba (Star Bits) come from their definitions' "batting_item" (charbuild)
ICE = 7                                              # ice_item.ICE (item-variants)
NAMES = {"shell": SHELL, "fireball": FIREBALL, "bobomb": BOBOMB, "pow": POW, "banana": BANANA, "boo": BOO,
         "starbits": STAR_BITS, "ice": ICE}          # "batting_item" values; + KOOPA_NAMES (8..)
# the Koopalings' items (koopa_items.NAMES / STOCK_FIXED, which are these: here so that checking a "batting_item" or
# the defaults never loads the item engine; a lean download, the Characters Beta, doesn't have it)
KOOPA_NAMES = {8: "lemmy", 9: "bill", 10: "iggy", 11: "larry", 12: "wendy", 13: "ludwig"}   # koopa_items.LEMMY..LUDWIG
KOOPA_STOCK_FIXED = {}   # stock characters (no definition file); Larry is a definition now (0x83, "batting_item":
#                          "larry"). Part of fixed / always's defaults; a stock entry's "batting_item" key does the same


CUSTOM = {}          # new items this build makes: name (lower case) -> id (charbuild sets it from the creations)


def item_id(value):
    """A "batting_item" value (a name from NAMES / KOOPA_NAMES, a new item's name (CUSTOM), or an item id)
    -> the item id."""
    if isinstance(value, int):
        return value
    names = {**NAMES, **{name: vid for vid, name in KOOPA_NAMES.items()}}
    if value not in names and str(value).strip().lower() in CUSTOM:
        return CUSTOM[str(value).strip().lower()]
    assert value in names, f"batting_item {value!r} (one of {sorted(names) + sorted(CUSTOM)})"
    return names[value]


def fixed(entries, defaults=True):
    """{character id: item} for item_hook: the per-character key "batting_item" (patcher profiles, characters/*.json,
    stock entries; a name or an id) on top of FIXED_ITEM and KOOPA_STOCK_FIXED (defaults=False: only the
    keys). "batting_item": false / "" / "none" removes the character; None or no key leaves it."""
    out = {**FIXED_ITEM, **KOOPA_STOCK_FIXED} if defaults else {}
    for e in entries:
        v = e.get("batting_item")
        if v is None:
            continue
        cid = int(e["id"])
        if v is False or v in ("", "none"):
            out.pop(cid, None)
        else:
            out[cid] = item_id(v)
    return out


def always(entries, defaults=True):
    """The character ids for hook (an item whatever the chemistry): the per-character key "always_item": true /
    false on top of ALWAYS_ITEM and KOOPA_STOCK_FIXED's characters (defaults=False: only the keys)."""
    out = list(ALWAYS_ITEM) + [c for c in KOOPA_STOCK_FIXED if c not in ALWAYS_ITEM] if defaults else []
    for e in entries:
        if e.get("always_item") is None:
            continue
        cid = int(e["id"])
        if e["always_item"] and cid not in out:
            out.append(cid)
        elif not e["always_item"] and cid in out:
            out.remove(cid)
    return tuple(out)


def batter_char(a, save):
    """r4 = the on-deck character's id (its slot in SLOT_REG). Clobbers r3, r5, r12, ctr, lr; r3 is saved in
    `save` first and restored after."""
    a.mr(save, 3)
    a.lis(12, BATTING_TEAM >> 16).ori(12, 12, BATTING_TEAM & 0xFFFF).mtctr(12).bctrl()
    a.lbz(4, 0x2A, 3)
    a.lwz(5, -0x2C8, 13)
    a.mulli(4, 4, 0x4FE).add(5, 5, 4)
    a.mulli(4, SLOT_REG, 0x8E).add(5, 5, 4)
    a.lhz(4, 0, 5)
    a.mr(3, save)
    return a


def hook(base, chars=None):
    """chars: always(...) (default ALWAYS_ITEM)."""
    a = Asm(base)
    a.cmpwi(3, 2).beq("done")              # already good chemistry
    a.cmpwi(SLOT_REG, 0).blt("done")       # no on-deck slot
    batter_char(a, 27)                     # r27 is saved by this function and set later
    for cid in (ALWAYS_ITEM if chars is None else chars):
        a.cmplwi(4, cid).beq("good")
    a.b("done")
    a.label("good")
    a.li(3, 2)
    a.label("done")
    a.addi(0, 3, -2)                       # the replaced instruction
    return a


def item_hook(base, items=None):
    """items: fixed(...) (default FIXED_ITEM)."""
    a = Asm(base)
    a.cmpwi(SLOT_REG, 0).blt("done")       # no on-deck slot
    batter_char(a, 27)                     # r27/r28 are set again right after this
    for i, (cid, item) in enumerate((FIXED_ITEM if items is None else items).items()):
        a.cmplwi(4, cid).bne(f"next{i}")
        a.li(3, item).b("done")
        a.label(f"next{i}")
    a.label("done")
    a.mr(30, 3)                            # the replaced instruction
    return a


HOOKS = [(HOOK, HOOK_ORIG, hook), (ITEM_HOOK, ITEM_HOOK_ORIG, item_hook)]


def givers(dol):
    """A built main.dol's givers, read back from the two hooks: (always: the on-deck characters that make the batter
    get an item, fixed: {on-deck character: item}). None, None when the hooks aren't there. The ON-DECK character
    decides (SLOT_REG): a batter gets the item of whoever bats after him."""
    def target(site):
        w = dol.u32(site)
        if w >> 26 != 18:
            return None
        off = w & 0x03FFFFFC
        return (site + (off - 0x04000000 if off & 0x02000000 else off)) & 0xFFFFFFFF

    def target_at(pc, w):
        off = w & 0x03FFFFFC
        return (pc + (off - 0x04000000 if off & 0x02000000 else off)) & 0xFFFFFFFF

    def words(at, site, n=400):
        out = []
        for k in range(n):
            w = dol.u32(at + 4 * k)
            out.append(w)
            if w >> 26 == 18 and not w & 1 and target_at(at + 4 * k, w) == site + 4:   # the branch back
                break
        return out
    a, f = target(HOOK), target(ITEM_HOOK)
    if a is None or f is None:
        return None, None
    cmp = lambda w: w >> 26 == 10 and (w >> 16) & 31 == 4    # cmplwi r4,imm  # noqa: E731
    always = [w & 0xFFFF for w in words(a, HOOK) if cmp(w)]
    fw, fixed = words(f, ITEM_HOOK), {}
    for k, w in enumerate(fw[:-2]):
        li = fw[k + 2]
        if cmp(w) and li >> 26 == 14 and (li >> 21) & 31 == 3 and (li >> 16) & 31 == 0:   # li r3,item
            fixed[w & 0xFFFF] = li & 0xFFFF
    return always, fixed
