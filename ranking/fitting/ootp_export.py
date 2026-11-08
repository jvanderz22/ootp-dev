"""Read an OOTP "Player List" HTML export (saved from the game's report pages)
into a DataFrame. A repeated header gets a suffix: the pitching CON is "CON.1"
after the batting CON."""
from collections import Counter
from html.parser import HTMLParser

import pandas as pd


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(self._cell.strip())
            self._cell = None
        elif tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data


def read(path) -> pd.DataFrame:
    parser = _Rows()
    with open(path, encoding="utf-8") as f:
        parser.feed(f.read())
    # the player table is the wide one; its header repeats down the page
    rows = [r for r in parser.rows if len(r) > 20]
    header, seen, columns = rows[0], Counter(), []
    for name in header:
        seen[name] += 1
        columns.append(name if seen[name] == 1 else f"{name}.{seen[name] - 1}")
    return pd.DataFrame([r for r in rows[1:] if r != header], columns=columns)
