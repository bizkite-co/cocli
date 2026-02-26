import os
import sys
from bs4 import BeautifulSoup

# Ensure we can import from cocli
sys.path.append(os.getcwd())

from cocli.scrapers.google_maps_parsers.extract_rating_reviews import extract_rating_reviews

GRANITE_SNIPPET = """
<div class="Bd93Zb" jsaction="pane.reviewChart.moreReviews" style="cursor: pointer;"><div class="ExlQHd"><table><tbody><tr class="BHOKXe" role="img" aria-label="5 stars, 2 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">5</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 100%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="4 stars, 0 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">4</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 0%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="3 stars, 0 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">3</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 0%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="2 stars, 0 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">2</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 0%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="1 stars, 1 review"><td class="yxmtmf fontBodyMedium" role="presentation">1</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 50%;"></div></div></td></tr></tbody></table></div><div class="jANrlb "><div class="fontDisplayLarge">3.7</div><div role="img" class="YTkVxc ikjxab" aria-label="3.7 stars"><div class="qxPNJf"></div><div class="qxPNJf"></div><div class="qxPNJf"></div><div class="qxPNJf pCqY8"></div><div class="qxPNJf FUbCHd"></div></div><button class="GQjSyb fontTitleSmall rqjGif" jslog="18519; track:click;metadata:WyIwYWhVS0V3am1vclBlZ3ZhU0F4VVdJMFFJSFJJd0UwZ1E2VzRJRXlnQiJd" jsaction="pane.wfvdle87.reviewChart.moreReviews"><div class="HHrUdb"><div class="OyjIsf "></div><span>3 reviews</span></div></button></div></div>
"""

def test_parser() -> None:
    print("--- Testing Granite Snippet ---")
    soup = BeautifulSoup(GRANITE_SNIPPET, "html.parser")
    inner_text = soup.get_text(separator=" ", strip=True)
    result = extract_rating_reviews(soup, inner_text, debug=True)
    print("Granite Snippet Result: " + str(result))
    
    files = ["repro_granite.html", "repro_griffith.html", "debug_final.html"]
    for fname in files:
        path = ".logs/" + fname
        if os.path.exists(path):
            print("\n--- Testing File: " + path + " ---")
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            soup = BeautifulSoup(html, "html.parser")
            inner_text = soup.get_text(separator=" ", strip=True)
            result = extract_rating_reviews(soup, inner_text, debug=True)
            print("File Result: " + str(result))

if __name__ == "__main__":
    test_parser()
