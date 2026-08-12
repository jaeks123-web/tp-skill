#!/usr/bin/env python3
"""
TP 스킬 무결성 검증 (MANIFEST.sha256 대조)

사용법
    python verify_skills.py                       # 스킬 폴더 안에서 인자 없이
    python verify_skills.py <스킬루트경로>
    python verify_skills.py <스킬루트경로> --only tp-case-law,workbook-validator
    python verify_skills.py <스킬루트경로> --manifest <매니페스트경로>

동작
    매니페스트에 기록된 파일의 SHA-256을 현재 파일과 대조한다.
    결과를 네 가지로 구분해 보고한다 — 이 구분이 핵심이다.

      일치      : 정본과 동일
      변조      : 파일은 있으나 해시가 다르다            → 문제
      누락      : 스킬은 설치되어 있는데 파일이 빠졌다    → 문제
      미설치    : 스킬 폴더 자체가 없다                   → 문제 아닐 수 있음

    ※ 스킬을 일부만 설치해 쓰는 경우가 많으므로 「미설치」를 「누락」과
      섞지 않는다. 섞으면 정상 상태에서도 경고가 쏟아져 경보가 무뎌진다.

종료 코드
    0 = 설치된 범위에서 전건 일치 (합격)
    1 = 변조 또는 누락 있음
    2 = 실행 불가 (경로·매니페스트 없음)

주의
    - 이 스크립트는 변조를 「막지」 못한다. 「드러나게」 할 뿐이다.
    - SKILL.md는 모델이 평문으로 읽어야 작동하므로 암호화·난독화는 성립하지 않는다.
    - 매니페스트가 조용히 바뀌면 검증 자체가 무의미하다. 변경 이력이 남는 곳
      (Git 등)에 보관하고 본 스크립트와 함께 배포한다.
"""

import hashlib
import os
import sys

# 출력 인코딩 고정 — 비UTF-8 로케일(한국어 Windows cp949 등)에서 파이프로 출력할 때
# 크래시하지 않게 한다. 실제 사고(2026-08-12): 「판정: 합격 — 전건 일치」의 em dash(U+2014)가
# cp949에 없어 UnicodeEncodeError로 종료 코드 1이 되었고, check_release.py가 이를 무결성
# 실패로 해석해 **13종 전부를 C1 불합격으로 오탐**했다. 콘솔 직접 출력은 UTF-16 경로라
# 문제가 없어 재현이 늦었다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # Python 3.6 이하 등
    pass

MANIFEST_DEFAULT = "MANIFEST.sha256"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path):
    """sha256sum 형식 파싱. '#' 주석행과 공백행은 건너뛴다."""
    entries = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            digest, rel = parts[0], parts[1].strip()
            if rel.startswith("*"):          # sha256sum 바이너리 모드 표기
                rel = rel[1:]
            entries[rel.replace("\\", "/")] = digest
    return entries


def parse_args(argv):
    root, manifest, only = None, None, None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--only" and i + 1 < len(argv):
            only = {s.strip() for s in argv[i + 1].split(",") if s.strip()}
            i += 2
        elif a == "--manifest" and i + 1 < len(argv):
            manifest = argv[i + 1]
            i += 2
        elif root is None:
            root = a
            i += 1
        else:
            i += 1
    here = os.path.dirname(os.path.abspath(__file__))     # <root>/<skill>/scripts
    skill_dir = os.path.dirname(here)                      # <root>/<skill>
    if manifest is None:
        manifest = os.path.join(here, MANIFEST_DEFAULT)
    # 스킬 안에서 인자 없이 실행한 경우: 루트와 대상 스킬을 스스로 판별한다
    if root is None and os.path.isfile(manifest):
        root = os.path.dirname(skill_dir)
        if only is None:
            only = {os.path.basename(skill_dir)}
    return root, manifest, only


def main():
    root, manifest, only = parse_args(sys.argv)

    if not root or not os.path.isdir(root):
        print("[중단] 스킬 루트 경로를 지정하십시오.")
        print("       예: python verify_skills.py <스킬루트경로>")
        return 2
    if not os.path.isfile(manifest):
        print(f"[중단] 매니페스트를 찾을 수 없습니다: {manifest}")
        return 2

    entries = load_manifest(manifest)
    if not entries:
        print(f"[중단] 매니페스트에 유효한 항목이 없습니다: {manifest}")
        return 2

    all_skills = sorted({r.split("/")[0] for r in entries})
    if only:
        unknown = only - set(all_skills)
        if unknown:
            print(f"[중단] 매니페스트에 없는 스킬명: {', '.join(sorted(unknown))}")
            print(f"       등재된 스킬: {', '.join(all_skills)}")
            return 2
        entries = {r: d for r, d in entries.items() if r.split("/")[0] in only}
        all_skills = sorted(only)

    ok, changed, missing, uninstalled = [], [], [], []

    for skill in all_skills:
        sdir = os.path.join(root, skill)
        skill_entries = {r: d for r, d in entries.items()
                         if r.split("/")[0] == skill}
        if not os.path.isdir(sdir):
            uninstalled.append((skill, len(skill_entries)))
            continue
        for rel, expected in sorted(skill_entries.items()):
            full = os.path.join(root, rel.replace("/", os.sep))
            if not os.path.isfile(full):
                missing.append(rel)
                continue
            actual = sha256_of(full)
            (ok if actual == expected else changed).append((rel, expected, actual))

    # 설치된 스킬 안의 매니페스트 미등재 파일 (신규 추가분)
    extra = []
    for skill in all_skills:
        sdir = os.path.join(root, skill)
        if not os.path.isdir(sdir):
            continue
        for dirpath, _, files in os.walk(sdir):
            for fn in files:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                # 매니페스트 자신은 대상이 아니다 (자기 해시를 담을 수 없다)
                if os.path.abspath(full) == os.path.abspath(manifest):
                    continue
                if rel not in entries:
                    extra.append(rel)

    scope = f"{len(all_skills)}종" + (f" (--only 지정)" if only else " (전체)")
    print("=" * 68)
    print("TP 스킬 무결성 검증")
    print(f"  스킬 루트  : {root}")
    print(f"  매니페스트 : {manifest}")
    print(f"  검증 범위  : {scope} / 등재 {len(entries)}건")
    print("=" * 68)
    print(f"  일치   : {len(ok)}건")
    print(f"  변조   : {len(changed)}건")
    print(f"  누락   : {len(missing)}건")
    print(f"  미설치 : {len(uninstalled)}개 스킬")
    print(f"  미등재 : {len(extra)}건")
    print("-" * 68)

    for rel, exp, act in changed:
        print(f"[변조] {rel}")
        print(f"       기대 {exp}")
        print(f"       실제 {act}")
    for rel in missing:
        print(f"[누락] {rel}  — 스킬은 설치되어 있으나 파일이 없습니다")
    for skill, n in uninstalled:
        print(f"[미설치] {skill}  (등재 {n}건)  — 설치하지 않았다면 정상입니다")
    for rel in sorted(extra):
        print(f"[미등재] {rel}")

    print("-" * 68)
    if changed or missing:
        print("판정: 불합격 — 정본과 다릅니다.")
        print("      이 상태로 사용하면 검증 규율이 빠진 채 동작할 수 있습니다.")
        print("      관리자에게 알리고 정본을 다시 받으십시오.")
        return 1

    if uninstalled:
        names = ", ".join(s for s, _ in uninstalled)
        print(f"판정: 합격(부분) — 설치된 범위는 전건 일치. 미설치: {names}")
        print("      ※ 미설치 스킬을 다른 스킬이 참조하고 있으면 그 지시는 실행되지 않습니다.")
        print("        특히 tp-case-law는 다수 스킬이 조문 검증 수단으로 지목합니다.")
        return 0

    if extra:
        print("판정: 조건부 합격 — 등재분은 전건 일치하나 매니페스트에 없는 파일이 있습니다.")
        return 0

    print("판정: 합격 — 전건 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
