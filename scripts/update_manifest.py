#!/usr/bin/env python3
"""
스킬 매니페스트 갱신

    python scripts/update_manifest.py              # 전체 13종
    python scripts/update_manifest.py tp-case-law  # 지정한 스킬만

스킬 내용을 고친 뒤 **반드시** 실행한다. 빠뜨리면 CI가 C1으로 막는다.

⚠️ 손으로 `find . | xargs sha256sum` 하지 말 것.
   `./SKILL.md` 형태가 되어 경로 기준(`<스킬>/SKILL.md`)이 어긋난다.
   실제로 그렇게 적은 안내문이 검사에서 걸린 적이 있다.
"""

import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
TARGET_EXT = (".md", ".py")

HEADER = """# {name} 무결성 매니페스트
# 확정일: {date}
# 경로 기준: 스킬 루트 (<루트>/{name}/...)
# 사용: 스킬 폴더에서  python3 scripts/verify_skills.py
#
# ⚠️ 매니페스트 자체는 대상에 포함되지 않는다. 함께 변조되면 검증은 통과한다.
# ⚠️ 해시는 설치본 기준. frontmatter의 name에 따옴표를 넣지 않는다(설치 시 제거됨).
# ⚠️ 이 파일은 scripts/update_manifest.py 로 생성한다. 손으로 만들지 않는다.
#
"""


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update(name, date):
    d = os.path.join(SKILLS, name)
    if not os.path.isdir(d):
        print(f"  ★ {name}: 폴더 없음")
        return False

    entries = []
    for dirpath, _, files in os.walk(d):
        for fn in sorted(files):
            if not fn.endswith(TARGET_EXT):
                continue
            full = os.path.join(dirpath, fn)
            # 경로는 반드시 '스킬 루트 기준' — <스킬>/<파일>
            rel = os.path.relpath(full, SKILLS).replace(os.sep, "/")
            entries.append((rel, sha256_of(full)))
    entries.sort()

    out = os.path.join(d, "scripts", "MANIFEST.sha256")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER.format(name=name, date=date))
        for rel, digest in entries:
            f.write(f"{digest}  {rel}\n")
    print(f"  {name:<34} {len(entries)}건")
    return True


def main():
    if not os.path.isdir(SKILLS):
        print(f"[중단] skills/ 없음: {SKILLS}")
        return 2

    import datetime
    date = datetime.date.today().isoformat()

    names = sys.argv[1:] or sorted(
        d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)))
    print(f"매니페스트 갱신 — {len(names)}종\n")
    ok = all([update(n, date) for n in names])

    print("\n다음으로 확인한다:  python scripts/check_release.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
