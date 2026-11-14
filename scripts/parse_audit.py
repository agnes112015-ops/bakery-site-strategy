"""감사보고서 XML → 표 행 텍스트(data/interim/audit_<회사>.txt) 및 키워드 행 출력."""
import glob
import html
import os
import re
import sys

BASE = os.path.join(os.path.dirname(__file__), "..", "data")
DOCS = os.path.join(BASE, "raw", "dart_docs")
INTERIM = os.path.join(BASE, "interim")
os.makedirs(INTERIM, exist_ok=True)

TAG = re.compile(r"<[^>]+>")


def rows_of(xml):
    out = []
    for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", xml, flags=re.S | re.I):
        cells = [re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", c))).strip()
                 for c in re.findall(r"<T[DHE][^>]*>(.*?)</T[DHE]>", tr, flags=re.S | re.I)]
        if any(cells):
            out.append(" | ".join(cells))
        else:
            pass
    # 표 바깥 단락 제목(주석 번호 등)도 남김
    return out


if __name__ == "__main__":
    kw = sys.argv[1:] or ["매출액", "영업수익", "매출원가", "판매비와관리비", "영업이익", "영업손실", "급여",
                          "임차료", "사용권자산", "감가상각비", "지급수수료", "광고선전비", "매장", "점포"]
    for path in glob.glob(os.path.join(DOCS, "*", "*", "*.xml")):
        company = path.replace("\\", "/").split("/")[-3]
        rcept = path.replace("\\", "/").split("/")[-2]
        raw = open(path, "rb").read()
        try:
            xml = raw.decode("utf-8")
        except UnicodeDecodeError:
            xml = raw.decode("cp949", errors="replace")
        rows = rows_of(xml)
        name = f"audit_{company}_{rcept}.txt"
        with open(os.path.join(INTERIM, name), "w", encoding="utf-8") as f:
            f.write("\n".join(rows))
        print("==", name, len(rows), "rows")
