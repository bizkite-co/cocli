from bs4 import BeautifulSoup

def dump_semantic(name: str) -> None:
    print("Semantic Classes for " + name)
    path = ".logs/repro_" + name + ".html"
    try:
        with open(path, "r") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        
        classes = ["F7nice", "jANrlb", "dmRWX", "PPCwl"]
        for cls in classes:
            found = soup.find_all(class_=cls)
            for el in found:
                print("CLASS " + cls + ": [" + el.get_text(separator="|", strip=True) + "]")
    except FileNotFoundError:
        print("File not found: " + path)

if __name__ == "__main__":
    dump_semantic("granite")
