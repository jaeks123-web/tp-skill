#!/usr/bin/env python3
"""
TP 스킬 저장소 릴리스 검사 (CI용)

검사 항목은 전부 **실제로 겪은 사고**에서 나왔다. 추상적인 린트가 아니다.

  C1 무결성      각 스킬의 scripts/MANIFEST.sha256이 현재 파일과 일치하는가
                 → 내용을 고치고 매니페스트를 다시 산출하지 않은 상태를 잡는다
  C2 개정 이력    SKILL.md가 바뀌었으면 개정 이력에 행이 추가되었는가
                 → v1.6·v1.7이 이력 없이 지나가는 것을 막는다 (배포보호 메모 2층 요구)
  C3 자리표시자   「0000」·「00000」 형태의 가짜 사건번호가 없는가
                 → korea-cases.md에 11건이 실재하지 않는 번호로 들어가 있던 사고
  C4 이름 규칙    스킬·플러그인 이름이 소문자·숫자·하이픈인가
                 → 대문자·한글 이름은 플러그인 업로드에서 거부된다
  C5 frontmatter  name에 따옴표가 없는가(설치본 형태)
                 → 설치 시 정규화되어 패키지와 해시가 어긋나는 것을 막는다
  C6 필수 절      Phase 0 무결성 확인 절이 있는가

사용
    python scripts/check_release.py                 # C1·C3~C6 (로컬)
    python scripts/check_release.py --base origin/main   # C2 포함 (CI)

종료 코드  0=합격 / 1=불합격 / 2=실행 불가
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
NAME_RE = re.compile(r"^[a-z0-9-]+$")
# 한글은 단어문자라 \b가 기대대로 동작하지 않는다. 경계 대신 형태로 판별한다.
#   2021서0000호 · 2019두00000 · 2021누00000  →  연도4자리 + 한글1자 + 0이 4개 이상
PLACEHOLDER_RE = re.compile(r"\d{4}\s?[가-힣]\s?0{4,}|0{4,}호|\d{4}[두누]0{4,}")

fails, warns = [], []


def fail(code, msg):
    fails.append(f"[{code}] {msg}")


def git(*args, ok=(0,)):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode in ok else None


def hist_rows(text):
    """개정 이력 절의 표 행 수 (헤더·구분선 제외)."""
    m = re.search(r"^##+ .*개정 이력.*$", text, re.M)
    if not m:
        return 0
    tail = text[m.end():]
    rows = re.findall(r"^\|.*\|\s*$", tail, re.M)
    return max(0, len(rows) - 2)


def check_skill(name):
    d = os.path.join(SKILLS, name)
    p = os.path.join(d, "SKILL.md")

    if not NAME_RE.match(name):
        fail("C4", f"{name}: 스킬 폴더명은 소문자·숫자·하이픈만 허용")
    if not os.path.isfile(p):
        fail("C1", f"{name}: SKILL.md 없음")
        return
    text = open(p, encoding="utf-8").read()

    # C5 frontmatter
    m = re.search(r'^name:\s*(.+)$', text, re.M)
    if not m:
        fail("C5", f"{name}: frontmatter에 name 없음")
    elif m.group(1).strip().startswith(('"', "'")):
        fail("C5", f"{name}: name에 따옴표가 있다 → 설치 시 제거되어 해시가 어긋난다")
    elif m.group(1).strip() != name:
        fail("C5", f"{name}: name({m.group(1).strip()})과 폴더명이 다르다")
    if not re.search(r'^description:\s*\S', text, re.M):
        fail("C5", f"{name}: description 없음 — 스킬이 발동되지 않는다")

    # C6 Phase 0
    if "Phase 0 — 무결성 확인" not in text:
        fail("C6", f"{name}: Phase 0 무결성 확인 절이 없다")

    # C1 무결성 (스킬 자체검증 재사용)
    v = os.path.join(d, "scripts", "verify_skills.py")
    if not os.path.isfile(v):
        fail("C1", f"{name}: scripts/verify_skills.py 없음")
    elif not os.path.isfile(os.path.join(d, "scripts", "MANIFEST.sha256")):
        fail("C1", f"{name}: scripts/MANIFEST.sha256 없음")
    else:
        r = subprocess.run([sys.executable, "scripts/verify_skills.py"],
                           cwd=d, capture_output=True, text=True)
        if r.returncode != 0:
            last = (r.stdout or r.stderr).strip().splitlines()
            fail("C1", f"{name}: 무결성 불합격 — {last[-1] if last else '실행 실패'}"
                       f"  (매니페스트를 다시 산출했는지 확인)")

    # C3 자리표시자
    for dirpath, _, files in os.walk(d):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, SKILLS).replace(os.sep, "/")
            for i, line in enumerate(open(fp, encoding="utf-8"), 1):
                # 경고문에서 「이런 번호를 쓰지 말라」고 예시로 드는 경우는 허용한다.
                # 판별 기준 두 가지 — 둘 다 실제 인용에는 나타나지 않는 형태다.
                #   ① 백틱(`...`)으로 감싼 코드 표기
                #   ② 같은 줄에 금지·경고 어휘가 있는 경우
                if any(k in line for k in ("자리표시자", "가짜", "실재하지", "금지",
                                           "placeholder", "생성·출력하지")):
                    continue
                stripped = re.sub(r"`[^`]*`", "", line)   # 코드 표기 제거 후 검사
                if PLACEHOLDER_RE.search(stripped):
                    fail("C3", f"{rel}:{i} 자리표시자 사건번호로 보인다 — {line.strip()[:70]}")


def check_history(base):
    changed = git("diff", "--name-only", f"{base}...HEAD")
    if changed is None:
        warns.append(f"C2 건너뜀: '{base}' 참조를 찾을 수 없다 (얕은 클론이면 fetch-depth: 0 필요)")
        return
    for f in changed.splitlines():
        if not (f.startswith("skills/") and f.endswith("SKILL.md")):
            continue
        name = f.split("/")[1]
        old = git("show", f"{base}:{f}")
        if old is None:              # 신규 스킬
            continue
        new = open(os.path.join(ROOT, f), encoding="utf-8").read()
        if hist_rows(new) <= hist_rows(old):
            fail("C2", f"{name}: SKILL.md가 바뀌었는데 개정 이력에 행이 추가되지 않았다")


def main():
    if not os.path.isdir(SKILLS):
        print(f"[중단] skills/ 디렉터리가 없다: {SKILLS}")
        return 2

    names = sorted(d for d in os.listdir(SKILLS)
                   if os.path.isdir(os.path.join(SKILLS, d)))
    print(f"검사 대상: {len(names)}종\n")
    for n in names:
        check_skill(n)

    if "--base" in sys.argv:
        check_history(sys.argv[sys.argv.index("--base") + 1])
    else:
        warns.append("C2 건너뜀: --base 미지정 (CI에서는 --base origin/main 사용)")

    for w in warns:
        print(f"  ⚠ {w}")
    if fails:
        print(f"\n불합격 {len(fails)}건\n")
        for f in fails:
            print(f"  {f}")
        print("\n대부분의 C1 실패는 다음으로 해결된다:")
        print("  python scripts/update_manifest.py [<스킬명>]")
        print("  ※ 손으로 find|sha256sum 하지 말 것 — 경로 기준이 어긋난다")
        return 1

    print(f"\n합격 — {len(names)}종 전건 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
