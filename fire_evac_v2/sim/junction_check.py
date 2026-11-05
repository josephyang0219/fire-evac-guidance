"""Check the per-junction output (1F, 9 ceiling OLEDs) over several fire / smoke / obstacle layouts.

python junction_check.py            -> table per scenario + PASS/FAIL, exit code 1 if any check fails

Checks for every 1F junction:
  - arrow N/S/E/W points into a corridor that exists (no wall) and is passable (no gate, rate < BLOCK_RATE)
  - arrow does not point into the fire segment (the segment nearest the estimated origin), unless no route avoids it
  - following the arrows ends at an exit or a stair (UP) without looping
  - "X" only when there really is no passable route to any exit
"""
import sys, math
import evac as E, states as ST

STEP = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}
NAMES = {(-1, 1): "西北", (0, 1): "北", (1, 1): "東北", (-1, 0): "西", (0, 0): "中央", (1, 0): "東",
         (-1, -1): "西南", (0, -1): "南", (1, -1): "東南"}


def blank():
    return E.fuse({})


def seg(st, fl, a, b):
    k = E.seg_name(fl, (a, b))
    return st[k] if k in st else st[E.seg_name(fl, (b, a))]


def smoke(st, fl, a, b, v):
    seg(st, fl, a, b)["smoke"] = v


def obstacle(st, fl, a, b, r, name="cabinet"):
    s = seg(st, fl, a, b); s["rate"] = max(s["rate"], r); s["items"].append((name, r))


def gate(st, fl, a, b):
    s = seg(st, fl, a, b); s.update(gate=True, rate=1.0); s["items"].append(("gate", 1.0))


def sc_normal():
    return blank(), "平常狀態，全部暢通"


def sc_east_fire():
    st = blank()
    smoke(st, 1, (0, 0), (1, 0), 0.9); smoke(st, 1, (1, 0), (1, 1), 0.4); smoke(st, 1, (0, 0), (0, 1), 0.3)
    return st, "一樓東側（中央—東）起火冒煙"


def sc_east_fire_cabinet():
    st, _ = sc_east_fire()
    obstacle(st, 1, (1, 0), (1, 1), 0.8)
    smoke(st, 1, (0, -1), (0, 0), 0.3); smoke(st, 1, (1, -1), (1, 0), 0.5)
    return st, "東側起火＋東出口北段櫃子倒下"


def sc_centre_fire():
    st = blank()
    for b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        smoke(st, 1, (0, 0), b, 0.9)
    return st, "中央十字路口起火（四支走廊臂都有濃煙）"


def sc_nw_fire():
    st = blank()
    smoke(st, 1, (-1, 1), (0, 1), 0.9); smoke(st, 1, (-1, 1), (-1, 0), 0.8); smoke(st, 1, (-1, 0), (-1, -1), 0.3)
    return st, "西北角（W 樓梯口）起火，煙往西出口方向擴散"


def sc_west_exit_blocked():
    st = blank()
    gate(st, 1, (-1, 0), (-1, -1))
    smoke(st, 1, (0, -1), (1, -1), 0.6); smoke(st, 1, (1, -1), (1, 0), 0.3)
    return st, "西出口閘門關閉＋東南側冒煙"


def sc_south_gate_obstacles():
    st, _ = sc_east_fire_cabinet()
    gate(st, 1, (-1, -1), (0, -1))
    obstacle(st, 1, (-1, 1), (0, 1), 0.6, "boxes")
    return st, "東側起火＋櫃子＋南側閘門＋北側箱子"


def sc_both_exits_blocked():
    st = blank()
    gate(st, 1, (-1, 0), (-1, -1)); gate(st, 1, (1, 0), (1, 1))
    smoke(st, 1, (0, 0), (0, 1), 0.5)
    return st, "兩個出口都被封住（預期全部 X）"


SCENARIOS = [sc_normal, sc_east_fire, sc_east_fire_cabinet, sc_centre_fire, sc_nw_fire,
             sc_west_exit_blocked, sc_south_gate_obstacles, sc_both_exits_blocked]


def passable(s):
    return not s["gate"] and s["rate"] < E.BLOCK_RATE


def fire_segment(st, fire):
    """all smoky 1F segments nearest the estimated origin (several when the fire sits on a junction)"""
    if not fire or fire["floor"] != 1:
        return set()
    cand = []
    for s in st.values():
        if s["floor"] != 1 or s["smoke"] <= 0.05:
            continue
        x, y = ST.seg_mid(1, s["seg"]); cand.append((math.hypot(x - fire["x"], y - fire["y"]), frozenset(s["seg"])))
    if not cand:
        return set()
    d0 = min(d for d, _ in cand)
    return {sg for d, sg in cand if d <= d0 + 1.0}


def reachable_exit(st, start, avoid=(), stairs=("W", "E")):
    """plain BFS over passable segments (both floors, via stairs): can `start` (floor, i, j) reach an exit?"""
    seen, todo = {start}, [start]
    while todo:
        fl, i, j = todo.pop()
        for s in st.values():
            if s["floor"] != fl or (i, j) not in s["seg"] or not passable(s) or fl == 1 and frozenset(s["seg"]) in avoid:
                continue
            if fl == 1 and any(set(sg) == set(s["seg"]) for sg in E.EXITS.values()):
                return True
            o = s["seg"][1] if s["seg"][0] == (i, j) else s["seg"][0]
            n = (fl, *o)
            if n not in seen:
                seen.add(n); todo.append(n)
        for t, ij in E.STAIRS.items():
            if t in stairs and (i, j) == ij:
                n = (3 - fl, i, j)
                if n not in seen:
                    seen.add(n); todo.append(n)
    return False


def check(st, leds, fire):
    fseg = fire_segment(st, fire)
    errs = []
    for ij in E.JUNCTION_ORDER:
        d = leds[(1,) + ij][0]
        tag = f"{E.junction_id(ij)}{NAMES[ij]}"
        if d == "X":
            if reachable_exit(st, (1,) + ij):
                errs.append(f"{tag}: 顯示 X，但其實有路可走")
            continue
        if d in ("UP", "DOWN"):
            if ij not in E.STAIRS.values():
                errs.append(f"{tag}: {d} 但這裡沒有樓梯")
            continue
        # follow the arrows
        cur, seen = ij, set()
        while True:
            if cur in seen:
                errs.append(f"{tag}: 箭頭繞圈"); break
            seen.add(cur)
            dd = leds[(1,) + cur][0]
            if dd in ("UP", "DOWN"):
                break
            if dd == "X":
                errs.append(f"{tag}: 跟著箭頭走到 {E.junction_id(cur)} 變成 X（死路）"); break
            nx = (cur[0] + STEP[dd][0], cur[1] + STEP[dd][1])
            if abs(nx[0]) > 1 or abs(nx[1]) > 1:
                errs.append(f"{tag}: {E.junction_id(cur)} 指向牆外"); break
            s = seg(st, 1, cur, nx)
            if not passable(s):
                errs.append(f"{tag}: {E.junction_id(cur)} 指向被封住的走廊"); break
            if frozenset((cur, nx)) in fseg and reachable_exit(st, (1,) + cur, avoid=fseg):
                errs.append(f"{tag}: {E.junction_id(cur)} 指向起火走廊，但有別條路"); break
            if any(set(sg) == {cur, nx} for sg in E.EXITS.values()):
                break                      # walked into an exit segment
            cur = nx
    return errs


def grid(leds):
    rows = []
    for j in (1, 0, -1):
        rows.append(" ".join(f"{leds[(1, i, j)][0]:>4}" for i in (-1, 0, 1)))
    return rows


def main():
    fails = 0
    for k, f in enumerate(SCENARIOS, 1):
        st, title = f()
        fire = ST.fire_estimate(st)
        leds, _ = E.plan(st, fire=fire)
        errs = check(st, leds, fire)
        fails += bool(errs)
        print(f"## 情境 {k}：{title}")
        where = "無" if not fire else "F%d (%s, %s)" % (fire["floor"], fire["x"], fire["y"])
        print(f"推估起火點：{where}")
        print()
        print("| 路口 | 方向 |\n|---|---|")
        for o in E.junctions(leds):
            ij = tuple(int(v) for v in o["id"][2:-1].split(","))
            print(f"| {o['id']} {NAMES[ij]} | {o['dir']} |")
        print()
        print("```\n      x=-1 x=0  x=1")
        for j, r in zip((1, 0, -1), grid(leds)):
            print(f"y={j:>2}  {r}")
        print("```")
        print("檢查：" + ("通過" if not errs else "失敗\n" + "\n".join("- " + e for e in errs)))
        print()
    print(f"共 {len(SCENARIOS)} 個情境，失敗 {fails} 個")
    return fails


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
