#!/usr/bin/env python3
"""
TP 스킬 플러그인 생성기

원본 스킬 트리(`src/skills/`)에서 플러그인 패키지를 만든다.
**묶는 방식만 인자로 바꾸면 되므로, 나중에 1묶음 ↔ 3묶음 전환이 자유롭다.**

사용법
    python build_plugins.py single     # 1묶음  : tp-skills (13종)
    python build_plugins.py split      # 3묶음  : tp-common(3) / tp-outbound(5) / tp-inbound(5)

분류 규칙 (사용자 확정, 2026-08-11)
    - 이름이 `-inbound`로 끝나면            → Inbound 전용
    - `-inbound` 짝이 존재하는 기본 이름     → Outbound 전용
    - 짝이 없는 것                          → Inbound·Outbound 공통

⚠️ 전환 시 주의
    1묶음에서 3묶음으로 바꾸면 **기존 플러그인을 먼저 제거**해야 한다.
    제거하지 않으면 같은 이름의 스킬이 중복 설치된다.

⚠️ 3묶음 사용 시
    `tp-common`을 반드시 함께 설치해야 한다. 플러그인 간 의존 선언 장치가 없으므로,
    누락되면 tp-case-law를 참조하는 스킬들의 조문 검증 지시가 조용히 실행되지 않는다.
    (각 스킬 Phase 0가 `[미설치] tp-case-law`로 보고하도록 되어 있다)
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "skills")
OUT = os.path.join(HERE, "dist")
# ⚠️ 플러그인 이름은 **소문자·숫자·하이픈만** 허용된다(대문자·한글·공백 불가).
#    설명(description)에는 한글을 써도 된다.
VERSION = "1.0.0"
AUTHOR = "Lim TP Technology"


def classify(names):
    common, outbound, inbound = [], [], []
    for n in sorted(names):
        if n.endswith("-inbound"):
            inbound.append(n)
        elif f"{n}-inbound" in names:
            outbound.append(n)
        else:
            common.append(n)
    return common, outbound, inbound


PLANS = {
    "single": lambda c, o, i: [
        ("tp-skills", "이전가격(TP) 업무 스킬 전체 묶음 — 산업분석·특성분류·비교가능회사 검색·"
                    "워크북 검증·보고서 작성·수익성 분석·법령판례. Outbound(내국법인)와 "
                    "Inbound(외국계법인) 체계를 모두 포함한다.", c + o + i),
    ],
    "split": lambda c, o, i: [
        ("tp-common", "이전가격(TP) 공통 스킬 — 법령·판례 조회, 비교가능회사 검색전략 수립, "
                    "수익성 분석. **tp-outbound·tp-inbound보다 먼저 설치해야 한다.**", c),
        ("tp-outbound", "이전가격(TP) 내국법인(Outbound) 체계 — 산업분석·특성분류·비교가능회사 "
                        "검색 검토·워크북 검증·보고서 작성. **tp-common이 함께 설치되어 있어야 한다.**", o),
        ("tp-inbound", "이전가격(TP) 외국계법인(Inbound) 체계 — 산업분석·특성결정·비교가능회사 "
                       "검색 검토·워크북 검증·보고서 작성. **tp-common이 함께 설치되어 있어야 한다.**", i),
    ],
}


def build(name, description, skills):
    root = os.path.join(OUT, name)
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(os.path.join(root, ".claude-plugin"))
    os.makedirs(os.path.join(root, "skills"))

    with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w",
              encoding="utf-8") as f:
        json.dump({"name": name, "version": VERSION,
                   "description": description, "author": {"name": AUTHOR}},
                  f, ensure_ascii=False, indent=2)

    for s in skills:
        shutil.copytree(os.path.join(SRC, s), os.path.join(root, "skills", s))

    # 압축은 /tmp에서 수행한다 (마운트 폴더에서 zip 제자리 갱신이 막히는 환경 대응)
    tmp = os.path.join("/tmp", "_plugbuild", name)
    shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    shutil.copytree(root, tmp)
    pkg = shutil.make_archive(os.path.join("/tmp", "_plugbuild", name),
                              "zip", os.path.dirname(tmp), name)
    dest = os.path.join(OUT, f"{name}.plugin")
    shutil.copyfile(pkg, dest)
    return dest, skills


def verify_all(skills):
    """각 스킬의 자체검증을 원본 트리에서 미리 돌려 본다."""
    bad = []
    for s in skills:
        r = subprocess.run([sys.executable, "scripts/verify_skills.py"],
                           cwd=os.path.join(SRC, s),
                           capture_output=True, text=True)
        if r.returncode != 0:
            bad.append((s, r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr))
    return bad


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    if mode not in PLANS:
        print(f"모드는 {' 또는 '.join(PLANS)} 입니다."); return 2

    names = set(os.listdir(SRC))
    c, o, i = classify(names)
    print(f"분류 — 공통 {len(c)} · Outbound {len(o)} · Inbound {len(i)}  (합계 {len(names)})")

    bad = verify_all(sorted(names))
    if bad:
        print("\n[중단] 원본 트리 자체검증 실패:")
        for s, msg in bad:
            print(f"  {s}: {msg}")
        return 1
    print("원본 트리 자체검증: 전건 합격\n")

    os.makedirs(OUT, exist_ok=True)
    for name, desc, skills in PLANS[mode](c, o, i):
        if not skills:
            continue
        dest, ss = build(name, desc, skills)
        size = os.path.getsize(dest)
        print(f"{name}.plugin  ({len(ss)}종, {size:,} bytes)")
        for s in ss:
            print(f"    - {s}")
    print(f"\n산출 위치: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
