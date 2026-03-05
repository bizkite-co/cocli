from bs4 import BeautifulSoup
from cocli.scrapers.google_maps_parsers.extract_rating_reviews_gm_details import extract_rating_reviews_gm_details

html_snippet = """
<div class="PPCwl cYOgid" jslog="25990;metadata:WyIwYWhVS0V3aWdvN3JoZ29lVEF4WHZPa1FJSGJpNkJjY1E4QmNJQWlnQSJd"><div class="Bd93Zb" jsaction="pane.reviewChart.moreReviews" style="cursor: pointer;"><div class="ExlQHd"><table><tbody><tr class="BHOKXe" role="img" aria-label="5 stars, 1 review"><td class="yxmtmf fontBodyMedium" role="presentation">5</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 100%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="4 stars, 0 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">4</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 0%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="3 stars, 0 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">3</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 0%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="2 stars, 0 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">2</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 0%;"></div></div></td></tr><tr class="BHOKXe" role="img" aria-label="1 stars, 0 reviews"><td class="yxmtmf fontBodyMedium" role="presentation">1</td><td class="ZVa0Ic" role="presentation"><div class="XINzN"><div class="oxIpGd" style="padding-left: 0%;"></div></div></td></tr></tbody></table></div><div class="jANrlb "><div class="fontDisplayLarge">5.0</div><div role="img" class="YTkVxc ikjxab" aria-label="5.0 stars"><div class="qxPNJf"></div><div class="qxPNJf"></div><div class="qxPNJf"></div><div class="qxPNJf"></div><div class="qxPNJf"></div></div><button class="GQjSyb fontTitleSmall rqjGif" jslog="18519; track:click;metadata:WyIwYWhVS0V3aWdvN3JoZ29lVEF4WHZPa1FJSGJpNkJjY1E2VzRJRWlnQiJd" jsaction="pane.wfvdle14.reviewChart.moreReviews"><div class="HHrUdb"><div class="OyjIsf "></div><span>1 review</span></div></button></div></div></div>
"""

print("--- Extraction Test ---")
soup = BeautifulSoup(html_snippet, "html.parser")
inner_text = soup.get_text(separator="\n", strip=True)
result = extract_rating_reviews_gm_details(soup, inner_text, debug=True)
print(f"Result: {result}")

if result["Reviews_count"] == "1":
    print("[SUCCESS] Found 1 review.")
else:
    print("[FAILURE] Failed to find 1 review.")

print("\n--- Area Code Interference Test ---")
interference_html = "<html><body><div>Bauman Wealth Management</div><div>5.0 (631) 555-1212</div></body></html>"
soup_i = BeautifulSoup(interference_html, "html.parser")
text_i = soup_i.get_text(separator="\n", strip=True)
result_i = extract_rating_reviews_gm_details(soup_i, text_i, debug=True)
print(f"Result with interference: {result_i}")

if result_i["Reviews_count"] == "631":
    print("[FAILURE] Still picking up area code as reviews!")
else:
    print("[SUCCESS] Correctly ignored area code.")
